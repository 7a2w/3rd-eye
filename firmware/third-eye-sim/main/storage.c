/* SD writer task (core 1): PSRAM write buffer -> 2 s chunk files on the card,
 * the 30 s rolling buffer, and clip saving. */
#include <string.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include "te_app.h"
#include "te_hal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/ringbuf.h"

static const char *TAG = "storage";

#define ROLL_DIR  HAL_SD_MOUNT "/roll"
#define CLIP_DIR  HAL_SD_MOUNT "/clips"
#define REC_MAGIC 0x31464554u   /* "TEF1" */

typedef struct { uint32_t magic, seq, ts_ms, len; } rec_hdr_t;
typedef struct { uint32_t seq, frames, t0_ms, t1_ms; } chunk_t;

typedef enum { REQ_START, REQ_STOP, REQ_SAVE } req_type_t;
typedef struct { req_type_t type; char trigger[12]; char phrase[40]; } req_t;

static RingbufHandle_t s_rb;
static StaticRingbuffer_t s_rb_struct;
static volatile uint32_t s_used;
static QueueHandle_t s_req;
static uint8_t *s_stage, *s_astage;
static size_t s_stage_n;
static int s_fd = -1;
static chunk_t s_cur;
static chunk_t s_done[TE_CHUNKS_KEPT + 1];
static int s_ndone;
static uint32_t s_chunk_seq, s_next_clip = 1;
static int64_t s_last_save_us = -10000000;
static bool s_active, s_card_ok;
static storage_stats_t s_st;

/* ---------------- write buffer ---------------- */
static inline uint32_t item_cost(size_t n) { return ((n + 3) & ~3u) + 8; }  /* ring item header */

bool wbuf_push(const uint8_t *jpeg, size_t len, uint32_t seq, int64_t ts_us)
{
    size_t need = sizeof(rec_hdr_t) + len;
    void *p = NULL;
    if (xRingbufferSendAcquire(s_rb, &p, need, 0) != pdTRUE) return false;
    rec_hdr_t h = {REC_MAGIC, seq, (uint32_t)(ts_us / 1000), (uint32_t)len};
    memcpy(p, &h, sizeof h);
    memcpy((uint8_t *)p + sizeof h, jpeg, len);
    xRingbufferSendComplete(s_rb, p);
    uint32_t u = __atomic_add_fetch(&s_used, item_cost(need), __ATOMIC_RELAXED);
    if (u > s_st.wbuf_hwm) s_st.wbuf_hwm = u;
    return true;
}

int wbuf_fill_pct(void) { return (int)((uint64_t)s_used * 100 / TE_WBUF_BYTES); }

/* ---------------- card writes ---------------- */
static void timed_write(int fd, const void *b, size_t n)
{
    int64_t t0 = esp_timer_get_time();
    int r = hal_sd_write(fd, b, n);
    uint32_t ms = (esp_timer_get_time() - t0) / 1000;
    if (ms > s_st.max_write_stall_ms) s_st.max_write_stall_ms = ms;
    if (r != (int)n) ESP_LOGE(TAG, "SD write failed (%d of %u)", r, (unsigned)n);
}

static void stage_flush(void)
{
    if (s_stage_n && s_fd >= 0) timed_write(s_fd, s_stage, s_stage_n);
    s_stage_n = 0;
}

static void close_chunk(void)
{
    if (s_fd < 0) return;
    stage_flush();
    close(s_fd);
    hal_sd_meta_op();
    s_fd = -1;
    if (s_cur.frames == 0) return;
    s_done[s_ndone++] = s_cur;
    if (s_ndone > TE_CHUNKS_KEPT) {
        char p[48];
        snprintf(p, sizeof p, ROLL_DIR "/r%06lu.mjp", (unsigned long)s_done[0].seq);
        unlink(p);
        hal_sd_meta_op();
        s_st.chunks_deleted++;
        memmove(s_done, s_done + 1, (s_ndone - 1) * sizeof(chunk_t));
        s_ndone--;
    }
}

static void open_chunk(uint32_t ts_ms)
{
    char p[48];
    s_cur = (chunk_t){.seq = s_chunk_seq++, .frames = 0, .t0_ms = ts_ms, .t1_ms = ts_ms};
    snprintf(p, sizeof p, ROLL_DIR "/r%06lu.mjp", (unsigned long)s_cur.seq);
    s_fd = open(p, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    hal_sd_meta_op();
    if (s_fd < 0) ESP_LOGE(TAG, "open %s failed", p);
    s_st.chunks_created++;
}

static void write_item(const uint8_t *item, size_t sz)
{
    const rec_hdr_t *h = (const rec_hdr_t *)item;
    if (s_fd >= 0 && h->ts_ms - s_cur.t0_ms >= TE_CHUNK_MS) close_chunk();
    if (s_fd < 0) open_chunk(h->ts_ms);
    size_t o = 0;
    while (o < sz) {
        size_t k = sz - o;
        if (k > TE_STAGING_BYTES - s_stage_n) k = TE_STAGING_BYTES - s_stage_n;
        memcpy(s_stage + s_stage_n, item + o, k);
        s_stage_n += k;
        o += k;
        if (s_stage_n == TE_STAGING_BYTES) stage_flush();
    }
    s_cur.frames++;
    s_cur.t1_ms = h->ts_ms;
    s_st.frames_written++;
}

/* Takes one frame from the write buffer and writes it. Returns false if empty. */
static bool drain_one(TickType_t wait)
{
    size_t sz;
    uint8_t *item = xRingbufferReceive(s_rb, &sz, wait);
    if (!item) return false;
    if (s_active && s_card_ok) write_item(item, sz);
    vRingbufferReturnItem(s_rb, item);
    __atomic_sub_fetch(&s_used, item_cost(sz), __ATOMIC_RELAXED);
    return true;
}

/* ---------------- clips ---------------- */
static void wav_header(uint8_t *h, uint32_t frames)
{
    uint32_t data = frames * 4, riff = 36 + data, rate = TE_AUDIO_RATE, br = TE_AUDIO_RATE * 4, fmt = 16;
    uint16_t pcm = 1, ch = 2, align = 4, bits = 16;
    memcpy(h, "RIFF", 4); memcpy(h + 4, &riff, 4); memcpy(h + 8, "WAVEfmt ", 8);
    memcpy(h + 16, &fmt, 4); memcpy(h + 20, &pcm, 2); memcpy(h + 22, &ch, 2); memcpy(h + 24, &rate, 4);
    memcpy(h + 28, &br, 4); memcpy(h + 32, &align, 2); memcpy(h + 34, &bits, 2);
    memcpy(h + 36, "data", 4); memcpy(h + 40, &data, 4);
}

static void do_save(const req_t *r)
{
    int64_t now = esp_timer_get_time();
    te_ev_t ev = {.type = EV_CLIP_SAVED};
    if (!s_card_ok) {
        s_st.saves_refused++;
        hal_report("EV save_refused reason=no_card");
        ev.arg = -2;
        te_post(&ev);
        return;
    }
    if (now - s_last_save_us < TE_SAVE_MERGE_MS * 1000LL) {
        s_st.saves_merged++;
        hal_report("EV save_merged trigger=%s", r->trigger);
        return;
    }
    uint64_t total = 0, freeb = 0;
    hal_sd_space(&total, &freeb);
    if (freeb < TE_MIN_FREE_BYTES) {
        s_st.saves_refused++;
        hal_report("EV save_refused free=%llu", freeb);
        ev.arg = -1;
        te_post(&ev);
        return;
    }
    s_last_save_us = now;
    close_chunk();
    uint32_t id = s_next_clip++;
    char dir[40], p[64], q[64];
    snprintf(dir, sizeof dir, CLIP_DIR "/c%04lu", (unsigned long)id);
    mkdir(dir, 0755);
    hal_sd_meta_op();
    uint32_t frames = 0, t0 = 0, t1 = 0;
    for (int i = 0; i < s_ndone; i++) {
        snprintf(p, sizeof p, ROLL_DIR "/r%06lu.mjp", (unsigned long)s_done[i].seq);
        snprintf(q, sizeof q, "%s/v%02d.mjp", dir, i);
        if (rename(p, q) != 0) ESP_LOGE(TAG, "rename %s failed", p);
        hal_sd_meta_op();
        if (i == 0) t0 = s_done[i].t0_ms;
        t1 = s_done[i].t1_ms;
        frames += s_done[i].frames;
    }
    int nvid = s_ndone;
    s_ndone = 0;

    /* audio: last 30 s from the PSRAM ring. Written ahead of queued frames,
     * which wait in the write buffer unless it gets close to full. */
    uint64_t end = audio_now(), first = audio_first();
    uint64_t start = end > (uint64_t)TE_AUDIO_CLIP_S * TE_AUDIO_RATE ? end - (uint64_t)TE_AUDIO_CLIP_S * TE_AUDIO_RATE : 0;
    if (start < first) start = first;
    uint32_t aframes = (uint32_t)(end - start);
    bool audio_ok = true;
    snprintf(p, sizeof p, "%s/a.wav", dir);
    int fd = open(p, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    hal_sd_meta_op();
    uint8_t hdr[44];
    wav_header(hdr, aframes);
    timed_write(fd, hdr, sizeof hdr);
    const size_t piece = TE_STAGING_BYTES / 2 / 4;   /* stereo frames per 16 KB */
    for (uint64_t pos = start; pos < end; pos += piece) {
        size_t k = end - pos < piece ? end - pos : piece;
        if (!audio_read(pos, (int16_t *)s_astage, k)) audio_ok = false;
        timed_write(fd, s_astage, k * 4);
        while (wbuf_fill_pct() > 80 && drain_one(0)) {}
    }
    close(fd);
    hal_sd_meta_op();
    if (!audio_ok) s_st.audio_overwritten++;

    snprintf(p, sizeof p, "%s/meta.txt", dir);
    FILE *f = fopen(p, "w");
    if (f) {
        fprintf(f, "id=%lu\ntrigger=%s\nphrase=%s\nvideo_files=%d\nframes=%lu\nvideo_ms=%lu\n"
                   "audio_frames=%lu\naudio_ok=%d\nsaved_ms=%lld\n",
                (unsigned long)id, r->trigger, r->phrase, nvid, (unsigned long)frames,
                (unsigned long)(t1 - t0), (unsigned long)aframes, audio_ok, now / 1000);
        fclose(f);
    }
    hal_sd_meta_op();
    s_st.clips_saved++;
    hal_report("EV clip_saved id=%lu trigger=%s frames=%lu video_ms=%lu audio_frames=%lu audio_ok=%d save_ms=%lld",
               (unsigned long)id, r->trigger, (unsigned long)frames, (unsigned long)(t1 - t0),
               (unsigned long)aframes, audio_ok, (esp_timer_get_time() - now) / 1000);
    link_sendf(MSG_CLIP_QUEUED, "{\"id\":%lu,\"trigger\":\"%s\",\"frames\":%lu}", (unsigned long)id,
               r->trigger, (unsigned long)frames);
    xfer_enqueue(id);
    ev.arg = id;
    te_post(&ev);
}

void clip_delete(uint32_t id)
{
    char dir[40], p[300];
    snprintf(dir, sizeof dir, CLIP_DIR "/c%04lu", (unsigned long)id);
    DIR *d = opendir(dir);
    if (d) {
        struct dirent *e;
        while ((e = readdir(d))) {
            snprintf(p, sizeof p, "%s/%s", dir, e->d_name);
            unlink(p);
            hal_sd_meta_op();
        }
        closedir(d);
    }
    rmdir(dir);
    hal_sd_meta_op();
}

static void delete_rolling(void)
{
    DIR *d = opendir(ROLL_DIR);
    if (!d) return;
    struct dirent *e;
    char p[300];
    while ((e = readdir(d))) {
        snprintf(p, sizeof p, ROLL_DIR "/%s", e->d_name);
        unlink(p);
        hal_sd_meta_op();
    }
    closedir(d);
    s_ndone = 0;
}

/* ---------------- back-pressure: lower fps if the card falls behind ---------------- */
static void backpressure(void)
{
    static int64_t high_since, low_since;
    static int cap = TE_FPS_FULL;
    int64_t now = esp_timer_get_time();
    int pct = wbuf_fill_pct();
    if (pct > TE_BP_HIGH_PCT) {
        if (!high_since) high_since = now;
        if (now - high_since > TE_BP_HIGH_MS * 1000LL && cap > TE_FPS_LOW) {
            cap = cap == TE_FPS_FULL ? TE_FPS_REDUCED : TE_FPS_LOW;
            capture_set_fps_cap(2, cap);
            hal_report("EV backpressure fps_cap=%d wbuf_pct=%d", cap, pct);
            high_since = 0;
        }
    } else high_since = 0;
    if (pct < TE_BP_LOW_PCT) {
        if (!low_since) low_since = now;
        if (now - low_since > TE_BP_LOW_MS * 1000LL && cap < TE_FPS_FULL) {
            cap = cap == TE_FPS_LOW ? TE_FPS_REDUCED : TE_FPS_FULL;
            capture_set_fps_cap(2, cap);
            hal_report("EV backpressure fps_cap=%d wbuf_pct=%d", cap, pct);
            low_since = 0;
        }
    } else low_since = 0;
}

static void sd_task(void *arg)
{
    for (;;) {
        req_t r;
        while (xQueueReceive(s_req, &r, 0) == pdTRUE) {
            if (r.type == REQ_START) { s_active = true; }
            else if (r.type == REQ_STOP) {
                while (drain_one(0)) {}
                close_chunk();
                s_active = false;
                delete_rolling();
                hal_report("EV storage_stopped");
            } else if (r.type == REQ_SAVE) {
                if (s_active) do_save(&r);
                else hal_report("EV save_ignored reason=not_listening");
            }
        }
        drain_one(pdMS_TO_TICKS(50));
        backpressure();
    }
}

void storage_start(void) { req_t r = {.type = REQ_START}; xQueueSend(s_req, &r, portMAX_DELAY); }
void storage_stop(void) { req_t r = {.type = REQ_STOP}; xQueueSend(s_req, &r, portMAX_DELAY); }
void storage_request_save(const char *trigger, const char *phrase)
{
    req_t r = {.type = REQ_SAVE};
    strlcpy(r.trigger, trigger, sizeof r.trigger);
    strlcpy(r.phrase, phrase ? phrase : "", sizeof r.phrase);
    if (xQueueSend(s_req, &r, 0) != pdTRUE) hal_report("EV save_dropped reason=queue_full");
}

void storage_get_stats(storage_stats_t *s)
{
    *s = s_st;
    s->wbuf_used = s_used;
    s->wbuf_size = TE_WBUF_BYTES;
    s->chunk_count = s_ndone + (s_fd >= 0);
}

bool storage_card_ok(void) { return s_card_ok; }

static void card_setup(void)
{
    mkdir(ROLL_DIR, 0755);
    mkdir(CLIP_DIR, 0755);
    delete_rolling();
    /* clips that were saved but not yet confirmed by the phone survive a reboot */
    DIR *d = opendir(CLIP_DIR);
    if (d) {
        struct dirent *ent;
        char p[300];
        while ((ent = readdir(d))) {
            unsigned long id;
            if (sscanf(ent->d_name, "c%lu", &id) != 1 && sscanf(ent->d_name, "C%lu", &id) != 1) continue;
            snprintf(p, sizeof p, CLIP_DIR "/%s/meta.txt", ent->d_name);
            struct stat st;
            if (stat(p, &st) == 0) {
                xfer_enqueue(id);
                hal_report("EV clip_recovered id=%lu", id);
            } else {
                clip_delete(id);
                hal_report("EV clip_incomplete_removed id=%lu", id);
            }
            if (id >= s_next_clip) s_next_clip = id + 1;
        }
        closedir(d);
    }
}

/* Without a working card the earpiece still streams audio and answers
 * prompts; frames are discarded and clip saves are refused. */
esp_err_t storage_init(void)
{
    esp_err_t e = hal_sd_mount();
    s_card_ok = e == ESP_OK;
    if (s_card_ok) card_setup();
    uint8_t *mem = heap_caps_malloc(TE_WBUF_BYTES, MALLOC_CAP_SPIRAM);
    s_stage = heap_caps_malloc(TE_STAGING_BYTES, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    s_astage = heap_caps_malloc(TE_STAGING_BYTES / 2, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!mem || !s_stage || !s_astage) return ESP_ERR_NO_MEM;
    s_rb = xRingbufferCreateStatic(TE_WBUF_BYTES, RINGBUF_TYPE_NOSPLIT, mem, &s_rb_struct);
    s_req = xQueueCreate(6, sizeof(req_t));
    xTaskCreatePinnedToCore(sd_task, "sd_writer", 4096, NULL, 5, NULL, 1);
    return e;
}
