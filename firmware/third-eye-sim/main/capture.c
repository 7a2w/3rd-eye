/* Camera task and audio task (both on core 1). */
#include <string.h>
#include "te_app.h"
#include "te_hal.h"
#include "adpcm.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

static const char *TAG = "capture";

#define RING_FRAMES ((uint64_t)TE_AUDIO_RING_S * TE_AUDIO_RATE)
static int16_t *s_ring;                 /* stereo int16, PSRAM */
static volatile uint64_t s_abs;         /* total stereo frames written */
static volatile uint64_t s_first;       /* first frame of the current recording */

static volatile bool s_recording, s_mic_on, s_cam_on, s_stream_on;
static volatile int s_caps[3] = {TE_FPS_FULL, TE_FPS_FULL, TE_FPS_FULL};
static volatile int s_fps;
static SemaphoreHandle_t s_cam_mtx;

static volatile bool s_prompt_on;
static int16_t *s_prompt;               /* mono, PSRAM */
static volatile size_t s_prompt_n;

static volatile uint8_t *s_grab_dst;
static volatile size_t s_grab_max, s_grab_len;
static SemaphoreHandle_t s_grab_done;

static capture_stats_t s_st;

static inline int16_t sat16(int32_t v) { return v > 32767 ? 32767 : (v < -32768 ? -32768 : v); }

/* ---------------- audio ---------------- */
static void audio_task(void *arg)
{
    static int32_t raw[TE_AUDIO_BLOCK * 2];
    static int16_t lr[TE_AUDIO_BLOCK * 2];
    static int16_t mono[TE_STREAM_BLOCK];
    static uint8_t pkt[4 + 4 + TE_STREAM_BLOCK / 2];
    size_t mono_n = 0;
    uint32_t seq = 0;
    adpcm_state_t ad = {0};
    int32_t x1[2] = {0}, y1[2] = {0};
    const int32_t a = 31507;   /* first-order high-pass at about 100 Hz: exp(-2*pi*100/16000) in Q15 */

    for (;;) {
        if (!s_mic_on) { vTaskDelay(pdMS_TO_TICKS(20)); mono_n = 0; continue; }
        size_t n = hal_mic_read(raw, TE_AUDIO_BLOCK, 200);
        if (!n) continue;
        for (size_t i = 0; i < n * 2; i++) {
            int c = i & 1;
            int32_t x = raw[i] >> 12;          /* 18-bit sample to 16-bit with +24 dB gain */
            int32_t y = x - x1[c] + ((a * y1[c]) >> 15);
            x1[c] = x;
            y1[c] = y;
            lr[i] = sat16(y);
        }
        if (s_recording) {
            uint64_t abs = s_abs;
            for (size_t i = 0; i < n; i++) {
                size_t r = (size_t)((abs + i) % RING_FRAMES);
                s_ring[2 * r] = lr[2 * i];
                s_ring[2 * r + 1] = lr[2 * i + 1];
            }
            s_abs = abs + n;
        }
        for (size_t i = 0; i < n; i++) {
            int16_t m = (int16_t)(((int32_t)lr[2 * i] + lr[2 * i + 1]) / 2);
            if (s_prompt_on && s_prompt_n < (size_t)TE_PROMPT_MAX_S * TE_AUDIO_RATE) s_prompt[s_prompt_n++] = m;
            mono[mono_n++] = m;
            if (mono_n == TE_STREAM_BLOCK) {
                mono_n = 0;
                if (s_stream_on && s_recording && !s_prompt_on && link_connected()) {
                    memcpy(pkt, &seq, 4);
                    size_t k = adpcm_encode_block(&ad, mono, TE_STREAM_BLOCK, pkt + 4);
                    seq++;
                    if (link_send(MSG_AUDIO, pkt, 4 + k)) s_st.stream_pkts++;
                    else s_st.stream_drops++;
                }
            }
        }
    }
}

uint64_t audio_now(void) { return s_abs; }
uint64_t audio_first(void)
{
    uint64_t now = s_abs;
    uint64_t lo = now > RING_FRAMES ? now - RING_FRAMES : 0;
    return lo > s_first ? lo : s_first;
}

bool audio_read(uint64_t from, int16_t *dst, size_t frames)
{
    for (size_t i = 0; i < frames; i++) {
        size_t r = (size_t)((from + i) % RING_FRAMES);
        dst[2 * i] = s_ring[2 * r];
        dst[2 * i + 1] = s_ring[2 * r + 1];
    }
    /* valid only if the writer has not lapped the region while we copied */
    return s_abs <= from + RING_FRAMES;
}

/* ---------------- camera ---------------- */
static void cam_task(void *arg)
{
    for (;;) {
        if (!s_cam_on) { vTaskDelay(pdMS_TO_TICKS(20)); continue; }
        hal_frame_t f;
        if (!hal_cam_get(&f, 200)) continue;
        s_st.frames_in++;
        if (s_recording) {
            if (wbuf_push(f.buf, f.len, f.sensor_seq, f.ts_us)) s_st.frames_to_wbuf++;
            else s_st.drop_wbuf++;
        }
        if (s_grab_dst) {
            size_t k = f.len < s_grab_max ? f.len : s_grab_max;
            memcpy((void *)s_grab_dst, f.buf, k);
            s_grab_len = k;
            s_grab_dst = NULL;
            xSemaphoreGive(s_grab_done);
        }
        hal_cam_release(&f);
    }
}

static int fps_target(void)
{
    int f = TE_FPS_FULL;
    for (int i = 0; i < 3; i++) if (s_caps[i] < f) f = s_caps[i];
    return f;
}

static void cam_apply(void)
{
    xSemaphoreTake(s_cam_mtx, portMAX_DELAY);
    int f = s_recording ? fps_target() : 0;
    if (f != s_fps) {
        if (f == 0) { s_cam_on = false; hal_cam_stop(); }
        else if (s_fps == 0) { hal_cam_start(f); s_cam_on = true; }
        else hal_cam_set_fps(f);
        hal_report("EV fps=%d", f);
        s_fps = f;
    }
    xSemaphoreGive(s_cam_mtx);
}

void capture_set_fps_cap(int src, int fps)
{
    if (s_caps[src] == fps) return;
    s_caps[src] = fps;
    cam_apply();
}

int capture_fps(void) { return s_fps; }

void capture_start(void)
{
    s_first = s_abs;
    s_recording = true;
    capture_mic_on(true);
    cam_apply();
}

void capture_stop(void)
{
    s_recording = false;
    cam_apply();
    if (!s_prompt_on) capture_mic_on(false);
}

bool capture_is_recording(void) { return s_recording; }

void capture_mic_on(bool on)
{
    if (on == s_mic_on) return;
    if (on) { hal_mic_start(); s_mic_on = true; }
    else { s_mic_on = false; hal_mic_stop(); }
}

void capture_stream_enable(bool on) { s_stream_on = on; }

void capture_prompt_begin(void)
{
    s_prompt_n = 0;
    capture_mic_on(true);
    s_prompt_on = true;
}

uint8_t *capture_prompt_end(size_t *len, uint32_t *samples)
{
    s_prompt_on = false;
    if (!s_recording) capture_mic_on(false);
    size_t n = s_prompt_n & ~1u;
    uint8_t *out = heap_caps_malloc(n / 2 + 8, MALLOC_CAP_SPIRAM);
    if (!out) { *len = 0; return NULL; }
    adpcm_state_t ad = {0};
    *len = adpcm_encode_block(&ad, s_prompt, n, out);
    *samples = n;
    return out;
}

size_t capture_grab_frame(uint8_t *dst, size_t max, uint32_t timeout_ms)
{
    bool temp = false;
    xSemaphoreTake(s_cam_mtx, portMAX_DELAY);
    if (!s_cam_on) { hal_cam_start(TE_FPS_FULL); s_cam_on = true; temp = true; }
    xSemaphoreGive(s_cam_mtx);
    s_grab_len = 0;
    s_grab_max = max;
    xSemaphoreTake(s_grab_done, 0);
    s_grab_dst = dst;
    bool ok = xSemaphoreTake(s_grab_done, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
    s_grab_dst = NULL;
    if (temp) {
        xSemaphoreTake(s_cam_mtx, portMAX_DELAY);
        if (s_fps == 0) { s_cam_on = false; hal_cam_stop(); }
        xSemaphoreGive(s_cam_mtx);
    }
    return ok ? s_grab_len : 0;
}

void capture_get_stats(capture_stats_t *s) { *s = s_st; }

void capture_init(void)
{
    s_ring = heap_caps_calloc(RING_FRAMES * 2, sizeof(int16_t), MALLOC_CAP_SPIRAM);
    s_prompt = heap_caps_malloc((size_t)TE_PROMPT_MAX_S * TE_AUDIO_RATE * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    s_cam_mtx = xSemaphoreCreateMutex();
    s_grab_done = xSemaphoreCreateBinary();
    if (!s_ring || !s_prompt) ESP_LOGE(TAG, "PSRAM allocation failed");
    xTaskCreatePinnedToCore(audio_task, "audio", 4096, NULL, 7, NULL, 1);
    xTaskCreatePinnedToCore(cam_task, "camera", 3072, NULL, 6, NULL, 1);
}
