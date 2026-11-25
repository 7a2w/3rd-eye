/* Clip transfer over Wi-Fi and the offline queue (core 0).
 * Wi-Fi is switched on only while queued clips are being sent. A clip is
 * deleted from the card only after the phone confirms it arrived intact.
 * Failed transfers stay queued and are retried every 5 s. */
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include "te_app.h"
#include "te_hal.h"
#include "esp_rom_crc.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#define QMAX 64
static uint32_t s_q[QMAX];
static volatile int s_n;
static SemaphoreHandle_t s_mtx;
static TaskHandle_t s_task;
static volatile bool s_busy, s_blocked;
static xfer_stats_t s_st;
static uint8_t *s_buf;

void xfer_enqueue(uint32_t id)
{
    xSemaphoreTake(s_mtx, portMAX_DELAY);
    bool dup = false;
    for (int i = 0; i < s_n; i++) dup |= s_q[i] == id;
    if (!dup && s_n < QMAX) s_q[s_n++] = id;
    xSemaphoreGive(s_mtx);
    xfer_kick();
}

static void pop_front(void)
{
    xSemaphoreTake(s_mtx, portMAX_DELAY);
    memmove(s_q, s_q + 1, (s_n - 1) * sizeof s_q[0]);
    s_n--;
    xSemaphoreGive(s_mtx);
}

void xfer_kick(void) { if (s_task) xTaskNotifyGive(s_task); }
int xfer_pending(void) { return s_n; }
bool xfer_busy(void) { return s_busy; }
void xfer_block(bool b) { s_blocked = b; if (!b) xfer_kick(); }
void xfer_get_stats(xfer_stats_t *s) { *s = s_st; }

static int wsend(uint8_t type, const void *d, size_t n)
{
    uint8_t h[4];
    frame_hdr(h, type, n);
    if (hal_wifi_send(h, 4, 5000) != 4) return -1;
    if (n && hal_wifi_send(d, n, 10000) != (int)n) return -1;
    s_st.bytes += 4 + n;
    return 0;
}

static int wsendf(uint8_t type, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static int wsendf(uint8_t type, const char *fmt, ...)
{
    char b[200];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(b, sizeof b, fmt, ap);
    va_end(ap);
    return wsend(type, b, n);
}

/* 0 = confirmed, 1 = phone reported a bad copy, -1 = link failure */
static int wait_ack(uint32_t id)
{
    uint8_t b[256];
    size_t have = 0;
    int64_t until = esp_timer_get_time() + TE_ACK_TIMEOUT_MS * 1000LL;
    while (esp_timer_get_time() < until) {
        int r = hal_wifi_recv(b + have, sizeof b - 1 - have, 500);
        if (r < 0) return -1;
        have += r;
        if (have >= 4) {
            uint32_t len = b[1] | (b[2] << 8) | (b[3] << 16);
            if (len > sizeof b - 5) return -1;
            if (have >= 4 + len) {
                b[4 + len] = 0;
                long aid = -1, ok = 0;
                json_int((char *)b + 4, "id", &aid);
                json_int((char *)b + 4, "ok", &ok);
                if (b[0] != MSG_ACK || aid != (long)id) return -1;
                return ok ? 0 : 1;
            }
        }
        if (!link_connected()) return -1;
    }
    return -1;
}

static int send_clip(uint32_t id)
{
    char dir[40], p[300];
    snprintf(dir, sizeof dir, TE_CLIP_DIR_FMT, (unsigned long)id);
    char names[20][16];
    int nf = 0;
    uint64_t total = 0;
    DIR *d = opendir(dir);
    if (!d) return 2;   /* clip vanished: drop it from the queue */
    struct dirent *e;
    while ((e = readdir(d)) && nf < 20) {
        strlcpy(names[nf], e->d_name, sizeof names[nf]);
        snprintf(p, sizeof p, "%s/%s", dir, names[nf]);
        struct stat st;
        if (stat(p, &st) == 0) total += st.st_size;
        nf++;
    }
    closedir(d);
    int64_t t0 = esp_timer_get_time();
    hal_report("EV xfer_start id=%lu files=%d bytes=%llu", (unsigned long)id, nf, total);
    if (wsendf(MSG_CLIP_BEGIN, "{\"id\":%lu,\"files\":%d,\"bytes\":%llu}", (unsigned long)id, nf, total)) return -1;
    uint32_t crc = 0;
    for (int i = 0; i < nf; i++) {
        snprintf(p, sizeof p, "%s/%s", dir, names[i]);
        struct stat st;
        stat(p, &st);
        if (wsendf(MSG_FILE_HDR, "{\"name\":\"%s\",\"size\":%ld}", names[i], (long)st.st_size)) return -1;
        int fd = open(p, O_RDONLY);
        hal_sd_meta_op();
        if (fd < 0) return -1;
        for (;;) {
            /* recording has priority on the card: back off while the write buffer is filling */
            while (wbuf_fill_pct() > TE_XFER_YIELD_PCT) vTaskDelay(pdMS_TO_TICKS(20));
            int r = hal_sd_read(fd, s_buf, TE_XFER_CHUNK);
            if (r <= 0) break;
            crc = esp_rom_crc32_le(crc, s_buf, r);
            if (wsend(MSG_DATA, s_buf, r) || !link_connected()) { close(fd); return -1; }
        }
        close(fd);
    }
    if (wsendf(MSG_CLIP_END, "{\"id\":%lu,\"crc\":%lu}", (unsigned long)id, (unsigned long)crc)) return -1;
    int a = wait_ack(id);
    int64_t ms = (esp_timer_get_time() - t0) / 1000;
    hal_report("EV xfer_done id=%lu result=%s ms=%lld kBps=%lld", (unsigned long)id,
               a == 0 ? "confirmed" : (a == 1 ? "nack" : "fail"), ms, ms ? (long long)(total / ms) : 0);
    return a;
}

static void xfer_task(void *arg)
{
    int64_t next_ok = 0;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(TE_RETRY_MS));
        int64_t now = esp_timer_get_time() / 1000;
        if (now < next_ok) {
            ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(next_ok - now));
        }
        if (!s_n || s_blocked) continue;
        if (!link_connected()) {
            hal_report("EV xfer_wait reason=phone_not_connected pending=%d", s_n);
            continue;
        }
        s_busy = true;
        s_st.attempts++;
        bool failed = false;
        if (hal_wifi_on(5000) != ESP_OK) {
            s_st.failed++;
            hal_report("EV xfer_fail reason=wifi_connect pending=%d", s_n);
            failed = true;
        }
        while (!failed && s_n && link_connected() && !s_blocked) {
            uint32_t id = s_q[0];
            int r = send_clip(id);
            if (r == 0 || r == 2) {
                if (r == 0) {
                    clip_delete(id);
                    s_st.sent++;
                    link_sendf(MSG_CLIP_DELETED, "{\"id\":%lu}", (unsigned long)id);
                    hal_report("EV clip_deleted id=%lu", (unsigned long)id);
                }
                pop_front();
            } else {
                if (r == 1) s_st.nacked++; else s_st.failed++;
                hal_report("EV xfer_fail reason=%s id=%lu pending=%d", r == 1 ? "nack" : "link", (unsigned long)id, s_n);
                failed = true;
            }
        }
        hal_wifi_off();
        s_busy = false;
        next_ok = failed ? esp_timer_get_time() / 1000 + TE_RETRY_MS : 0;
    }
}

void xfer_init(void)
{
    s_mtx = xSemaphoreCreateMutex();
    s_buf = heap_caps_malloc(TE_XFER_CHUNK, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    xTaskCreatePinnedToCore(xfer_task, "wifi_xfer", 4096, NULL, 4, &s_task, 0);
}
