/* Periodic resource report: heap (internal SRAM and PSRAM), write-buffer
 * high-water mark, dropped frames, card usage, battery model, CPU load. */
#include <string.h>
#include "te_app.h"
#include "te_hal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

int g_metrics_period_s = 10;
void metrics_set_period(int s) { if (s > 0) g_metrics_period_s = s; }

#define MAX_TASKS 32
static TaskStatus_t s_tasks[MAX_TASKS];
static configRUN_TIME_COUNTER_TYPE s_prev_idle[2], s_prev_total;

/* CPU load per core = 1 - (idle task run time / elapsed time) since the last call. */
static void cpu_load(float *c0, float *c1)
{
    configRUN_TIME_COUNTER_TYPE total;
    UBaseType_t n = uxTaskGetSystemState(s_tasks, MAX_TASKS, &total);
    configRUN_TIME_COUNTER_TYPE idle[2] = {0};
    for (UBaseType_t i = 0; i < n; i++) {
        if (!strcmp(s_tasks[i].pcTaskName, "IDLE0")) idle[0] = s_tasks[i].ulRunTimeCounter;
        if (!strcmp(s_tasks[i].pcTaskName, "IDLE1")) idle[1] = s_tasks[i].ulRunTimeCounter;
    }
    configRUN_TIME_COUNTER_TYPE dt = total - s_prev_total;
    *c0 = dt ? 100.0f * (1.0f - (float)(idle[0] - s_prev_idle[0]) / dt) : 0;
    *c1 = dt ? 100.0f * (1.0f - (float)(idle[1] - s_prev_idle[1]) / dt) : 0;
    s_prev_idle[0] = idle[0];
    s_prev_idle[1] = idle[1];
    s_prev_total = total;
}

void metrics_report(void)
{
    capture_stats_t c; storage_stats_t s; link_stats_t l; xfer_stats_t x; hal_stats_t h;
    capture_get_stats(&c); storage_get_stats(&s); link_get_stats(&l); xfer_get_stats(&x); hal_get_stats(&h);
    uint64_t sd_total = 0, sd_free = 0;
    hal_sd_space(&sd_total, &sd_free);
    float c0, c1;
    cpu_load(&c0, &c1);
    hal_report("STATS {\"state\":\"%s\",\"fps\":%d,"
               "\"int_free\":%u,\"int_min\":%u,\"int_largest\":%u,"
               "\"ps_free\":%u,\"ps_min\":%u,\"ps_largest\":%u,"
               "\"wbuf_used\":%lu,\"wbuf_hwm\":%lu,\"wbuf_size\":%lu,"
               "\"frames_in\":%lu,\"frames_written\":%lu,\"drop_wbuf\":%lu,\"drop_cam\":%lu,"
               "\"stream_pkts\":%lu,\"stream_drops\":%lu,"
               "\"sd_written\":%llu,\"sd_read\":%llu,\"sd_pauses\":%lu,\"sd_pause_ms\":%lu,\"max_write_ms\":%lu,"
               "\"sd_used\":%llu,\"sd_total\":%llu,\"chunks\":%lu,"
               "\"clips_saved\":%lu,\"clips_sent\":%lu,\"pending\":%d,\"xfer_fail\":%lu,\"audio_overwritten\":%lu,"
               "\"ble\":%d,\"ble_retries\":%lu,\"wifi\":%d,"
               "\"batt_pct\":%d,\"mah_used\":%.1f,\"current_ma\":%.1f,\"temp\":%.1f,"
               "\"cpu0\":%.1f,\"cpu1\":%.1f}",
               te_state_name(g_state), capture_fps(),
               (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
               (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
               (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
               (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
               (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM),
               (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM),
               (unsigned long)s.wbuf_used, (unsigned long)s.wbuf_hwm, (unsigned long)s.wbuf_size,
               (unsigned long)c.frames_in, (unsigned long)s.frames_written, (unsigned long)c.drop_wbuf,
               (unsigned long)h.cam_driver_drops, (unsigned long)c.stream_pkts, (unsigned long)c.stream_drops,
               h.sd_bytes_written, h.sd_bytes_read, (unsigned long)h.sd_pauses, (unsigned long)h.sd_pause_ms_total,
               (unsigned long)s.max_write_stall_ms, sd_total - sd_free, sd_total, (unsigned long)s.chunk_count,
               (unsigned long)s.clips_saved, (unsigned long)x.sent, xfer_pending(), (unsigned long)x.failed,
               (unsigned long)s.audio_overwritten,
               link_connected(), (unsigned long)l.reconnect_attempts, hal_wifi_is_on(),
               hal_battery_pct(), h.battery_mah_used, h.model_current_ma, hal_temp_c(), c0, c1);
}

void metrics_tasks_report(void)
{
    configRUN_TIME_COUNTER_TYPE total;
    UBaseType_t n = uxTaskGetSystemState(s_tasks, MAX_TASKS, &total);
    char buf[700];
    int o = snprintf(buf, sizeof buf, "TASKS {");
    for (UBaseType_t i = 0; i < n && o < (int)sizeof buf - 40; i++)
        o += snprintf(buf + o, sizeof buf - o, "%s\"%s\":%u", i ? "," : "", s_tasks[i].pcTaskName,
                      (unsigned)(s_tasks[i].usStackHighWaterMark));
    snprintf(buf + o, sizeof buf - o, "}");
    hal_report("%s", buf);
}
