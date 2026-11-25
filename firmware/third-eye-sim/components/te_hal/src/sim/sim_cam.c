/* Simulated OV5640: synthetic 1280x720 JPEG frames, about 60 KB each.
 * Behaves like esp32-camera with fb_count = 2 in PSRAM: if the app still
 * holds both buffers when a new frame is ready, the frame is dropped. */
#include <string.h>
#include "te_hal.h"
#include "sim_internal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define FB_COUNT 2
#define FB_SIZE (100 * 1024)
#define POOL_SIZE (96 * 1024)
#define FRAME_MEAN 60000

typedef struct { uint8_t *buf; size_t len; int64_t ts; uint32_t seq; volatile bool busy; } fb_t;
static fb_t s_fb[FB_COUNT];
static uint8_t *s_pool;
static QueueHandle_t s_ready;
static TaskHandle_t s_task;
static volatile bool s_run;
static volatile int s_fps;
static uint32_t s_seq;

static size_t make_frame(uint8_t *dst, uint32_t seq, int64_t ts)
{
    size_t len = FRAME_MEAN * (90 + sim_rand() % 21) / 100;   /* 54 to 66 KB */
    if (sim_rand() % 150 == 0) len = len * 13 / 10;           /* occasional busy scene / slide change */
    static const uint8_t hdr[] = {0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 'J', 'F', 'I', 'F', 0, 1, 1, 0, 0, 1, 0, 1, 0, 0};
    memcpy(dst, hdr, sizeof hdr);
    size_t o = sizeof hdr;
    dst[o++] = 0xFF; dst[o++] = 0xFE;   /* COM marker carrying the frame number */
    char com[40];
    int cl = snprintf(com, sizeof com, "TE seq=%lu ts=%lld w=1280 h=720", (unsigned long)seq, ts);
    dst[o++] = 0; dst[o++] = cl + 2;
    memcpy(dst + o, com, cl); o += cl;
    dst[o++] = 0xFF; dst[o++] = 0xDA;
    size_t body = len - o - 2;
    size_t off = (seq * 7919u) % (POOL_SIZE / 2);
    memcpy(dst + o, s_pool + off, body);   /* stands in for the camera DMA writing the frame */
    o += body;
    dst[o++] = 0xFF; dst[o++] = 0xD9;
    return o;
}

static void cam_task(void *arg)
{
    int64_t next = esp_timer_get_time();
    while (s_run) {
        int fps = s_fps;
        next += 1000000 / fps;
        int64_t now = esp_timer_get_time();
        if (next > now) vTaskDelay(pdMS_TO_TICKS((next - now) / 1000));
        else next = now;
        uint32_t seq = s_seq++;
        fb_t *fb = NULL;
        for (int i = 0; i < FB_COUNT; i++) if (!s_fb[i].busy) { fb = &s_fb[i]; break; }
        if (!fb) { g_sim_cam_drops++; continue; }
        fb->busy = true;
        fb->ts = esp_timer_get_time();
        fb->seq = seq;
        fb->len = make_frame(fb->buf, seq, fb->ts);
        if (xQueueSend(s_ready, &fb, 0) != pdTRUE) { fb->busy = false; g_sim_cam_drops++; }
    }
    s_task = NULL;
    vTaskDelete(NULL);
}

esp_err_t hal_cam_start(int fps)
{
    if (!s_pool) {
        s_pool = heap_caps_malloc(POOL_SIZE, MALLOC_CAP_SPIRAM);
        for (int i = 0; i < POOL_SIZE; i++) s_pool[i] = (uint8_t)(sim_rand() >> 7);
        for (int i = 0; i < FB_COUNT; i++) s_fb[i].buf = heap_caps_malloc(FB_SIZE, MALLOC_CAP_SPIRAM);
        s_ready = xQueueCreate(FB_COUNT, sizeof(fb_t *));
        if (!s_pool || !s_fb[0].buf || !s_fb[1].buf) return ESP_ERR_NO_MEM;
    }
    if (s_run) { hal_cam_set_fps(fps); return ESP_OK; }
    s_fps = fps;
    g_sim_cam_fps = fps;
    s_run = true;
    xTaskCreatePinnedToCore(cam_task, "sim_cam", 3072, NULL, 10, &s_task, 1);
    return ESP_OK;
}

void hal_cam_stop(void)
{
    s_run = false;
    while (s_task) vTaskDelay(pdMS_TO_TICKS(10));
    fb_t *fb;
    while (xQueueReceive(s_ready, &fb, 0) == pdTRUE) fb->busy = false;
    g_sim_cam_fps = 0;
}

void hal_cam_set_fps(int fps) { s_fps = fps; if (s_run) g_sim_cam_fps = fps; }

bool hal_cam_get(hal_frame_t *f, uint32_t timeout_ms)
{
    fb_t *fb;
    if (!s_ready || xQueueReceive(s_ready, &fb, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) return false;
    f->buf = fb->buf; f->len = fb->len; f->ts_us = fb->ts; f->sensor_seq = fb->seq; f->priv = fb;
    return true;
}

void hal_cam_release(hal_frame_t *f) { ((fb_t *)f->priv)->busy = false; }
