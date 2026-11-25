/* Phone link over BLE (core 0): framed messages, reconnect every 5 s,
 * phone-lost detection, and command dispatch.
 * Frame: 1 byte type, 3 bytes little-endian length, payload. */
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include "te_app.h"
#include "te_hal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

#define RX_CAP (160 * 1024)

typedef struct { uint8_t type; uint32_t len; uint8_t data[]; } msg_t;
static QueueHandle_t s_txq;
static volatile bool s_tx_busy;
static link_stats_t s_st;

void frame_hdr(uint8_t *h, uint8_t type, uint32_t len)
{
    h[0] = type; h[1] = len & 0xff; h[2] = (len >> 8) & 0xff; h[3] = (len >> 16) & 0xff;
}

bool link_connected(void) { return hal_ble_connected(); }
bool link_tx_idle(void) { return uxQueueMessagesWaiting(s_txq) == 0 && !s_tx_busy; }

bool link_send(uint8_t type, const void *data, size_t len)
{
    if (!hal_ble_connected()) { s_st.tx_dropped++; return false; }
    uint32_t caps = len > 1024 ? MALLOC_CAP_SPIRAM : MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    msg_t *m = heap_caps_malloc(sizeof(msg_t) + len, caps);
    if (!m) { s_st.tx_dropped++; return false; }
    m->type = type;
    m->len = len;
    if (len) memcpy(m->data, data, len);
    if (xQueueSend(s_txq, &m, 0) != pdTRUE) { free(m); s_st.tx_dropped++; return false; }
    return true;
}

bool link_sendf(uint8_t type, const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    return link_send(type, buf, n < (int)sizeof buf ? n : sizeof buf - 1);
}

static void tx_task(void *arg)
{
    for (;;) {
        msg_t *m;
        xQueueReceive(s_txq, &m, portMAX_DELAY);
        s_tx_busy = true;
        if (hal_ble_connected()) {
            uint8_t h[4];
            frame_hdr(h, m->type, m->len);
            if (hal_ble_send(h, 4, 2000) == 4 && (!m->len || hal_ble_send(m->data, m->len, 10000) == (int)m->len))
                s_st.tx_bytes += 4 + m->len;
        }
        free(m);
        s_tx_busy = false;
    }
}

static void post_cmd(te_ev_type_t t, const char *text, int arg)
{
    te_ev_t ev = {.type = t, .arg = arg};
    if (text) strlcpy(ev.text, text, sizeof ev.text);
    te_post(&ev);
}

static void dispatch(uint8_t type, uint8_t *d, uint32_t len)
{
    if (type == MSG_PING) return;
    if (type == MSG_CMD) {
        char js[256];
        size_t n = len < sizeof js - 1 ? len : sizeof js - 1;
        memcpy(js, d, n);
        js[n] = 0;
        char cmd[16] = {0}, phrase[40] = {0};
        long v = 0;
        json_str(js, "cmd", cmd, sizeof cmd);
        if (!strcmp(cmd, "listen")) post_cmd(EV_CMD_LISTEN, NULL, 0);
        else if (!strcmp(cmd, "stop")) post_cmd(EV_CMD_STOP, NULL, 0);
        else if (!strcmp(cmd, "save")) { json_str(js, "phrase", phrase, sizeof phrase); post_cmd(EV_CMD_SAVE, phrase, 0); }
        else if (!strcmp(cmd, "stats")) { json_int(js, "period", &v); post_cmd(EV_CMD_STATS, NULL, (int)v); }
        else if (!strcmp(cmd, "tasks")) metrics_tasks_report();
        else hal_report("EV unknown_cmd %s", cmd);
        return;
    }
    if (type == MSG_REPLY) {
        /* JSON header line, then optional 16-bit PCM for the speaker */
        uint8_t *nl = memchr(d, '\n', len);
        size_t hl = nl ? (size_t)(nl - d) : len;
        char js[200];
        size_t n = hl < sizeof js - 1 ? hl : sizeof js - 1;
        memcpy(js, d, n);
        js[n] = 0;
        long ok = 0, approval = 0;
        json_int(js, "ok", &ok);
        json_int(js, "approval", &approval);
        te_ev_t ev = {.type = EV_REPLY, .arg = (int)ok, .arg2 = (int)approval};
        size_t pl = nl ? len - hl - 1 : 0;
        if (pl) {
            ev.data = heap_caps_malloc(pl, MALLOC_CAP_SPIRAM);
            if (ev.data) { memcpy(ev.data, nl + 1, pl); ev.len = pl; }
        }
        te_post(&ev);
        return;
    }
    hal_report("EV unknown_msg type=0x%02x len=%lu", type, (unsigned long)len);
}

static void rx_task(void *arg)
{
    uint8_t *buf = heap_caps_malloc(RX_CAP, MALLOC_CAP_SPIRAM);
    size_t have = 0;
    bool was_up = false;
    int64_t next_try = 0, last_rx = 0, next_status = 0;
    for (;;) {
        int64_t now = esp_timer_get_time() / 1000;
        if (!hal_ble_connected()) {
            if (was_up) {
                was_up = false;
                s_st.disconnects++;
                have = 0;
                post_cmd(EV_BLE_DOWN, NULL, 0);
                next_try = now + TE_RETRY_MS;
            }
            if (now >= next_try) {
                s_st.reconnect_attempts++;
                if (hal_ble_try_connect() == ESP_OK) {
                    was_up = true;
                    last_rx = now;
                    have = 0;
                    hal_report("EV ble_connected attempts=%lu", (unsigned long)s_st.reconnect_attempts);
                    link_sendf(MSG_HELLO, "{\"fw\":\"third-eye 0.1\",\"platform\":\"%s\",\"state\":\"%s\"}",
                               hal_platform_name(), te_state_name(g_state));
                    post_cmd(EV_BLE_UP, NULL, 0);
                } else {
                    hal_report("EV ble_retry n=%lu", (unsigned long)s_st.reconnect_attempts);
                }
                next_try = now + TE_RETRY_MS;
            }
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        int r = hal_ble_recv(buf + have, RX_CAP - have, 200);
        now = esp_timer_get_time() / 1000;
        if (r < 0) continue;
        if (r > 0) {
            last_rx = now;
            s_st.rx_bytes += r;
            have += r;
            while (have >= 4) {
                uint32_t len = buf[1] | (buf[2] << 8) | (buf[3] << 16);
                if (len > RX_CAP - 4) { hal_ble_disconnect(); have = 0; break; }
                if (have < 4 + len) break;
                dispatch(buf[0], buf + 4, len);
                memmove(buf, buf + 4 + len, have - 4 - len);
                have -= 4 + len;
            }
        }
        if (now - last_rx > TE_LINK_TIMEOUT_MS) {
            hal_report("EV phone_lost reason=timeout");
            hal_ble_disconnect();
            continue;
        }
        if (now >= next_status) {
            next_status = now + TE_STATUS_MS;
            link_sendf(MSG_STATUS, "{\"state\":\"%s\",\"fps\":%d,\"batt\":%d,\"temp\":%.1f,\"pending\":%d,\"wbuf_pct\":%d}",
                       te_state_name(g_state), capture_fps(), hal_battery_pct(), hal_temp_c(), xfer_pending(),
                       wbuf_fill_pct());
        }
    }
}

void link_get_stats(link_stats_t *s) { *s = s_st; }

void link_init(void)
{
    s_txq = xQueueCreate(48, sizeof(msg_t *));
    xTaskCreatePinnedToCore(tx_task, "ble_tx", 3072, NULL, 5, NULL, 0);
    xTaskCreatePinnedToCore(rx_task, "ble_rx", 4096, NULL, 5, NULL, 0);
}
