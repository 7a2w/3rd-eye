/* Control task (core 0): buttons, the Sleep / Listen / Prompt state machine,
 * temperature and battery handling, voice lines, periodic metrics. */
#include <string.h>
#include "te_app.h"
#include "te_hal.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

volatile te_state_t g_state = ST_SLEEP;
static QueueHandle_t s_evq;

const char *te_state_name(te_state_t s)
{
    static const char *n[] = {"sleep", "listen", "prompt", "stopping"};
    return n[s];
}

void te_post(const te_ev_t *ev)
{
    if (!s_evq || xQueueSend(s_evq, ev, 0) != pdTRUE) {
        hal_report("EV event_queue_full type=%d", ev->type);
        if (ev->data) free(ev->data);
    }
}

void te_voice(te_voice_t v)
{
    static const char *names[] = {"", "listening", "stopped_listening", "clip_saved", "phone_disconnected",
                                  "phone_connected", "sorry_couldnt_answer", "too_hot", "cooled_down",
                                  "low_battery", "battery_critical", "storage_full", "approve_change",
                                  "memory_card_problem"};
    hal_spk_voice(v, names[v]);
}

static void set_state(te_state_t s)
{
    g_state = s;
    hal_report("STATE %s", te_state_name(s));
}

/* ---------------- Listen ---------------- */
static bool s_batt_crit, s_batt_low, s_block_heat, s_was_lost;
static int64_t s_stop_deadline;

static void enter_listen(void)
{
    if (g_state != ST_SLEEP) return;
    if (s_batt_crit) { te_voice(VL_BATTERY_CRITICAL); return; }
    storage_start();
    capture_start();
    capture_stream_enable(true);
    set_state(ST_LISTEN);
    te_voice(VL_LISTEN_ON);
    if (!storage_card_ok()) te_voice(VL_CARD_ERROR);
}

static void stop_capture(void)
{
    capture_stream_enable(false);
    capture_stop();
    storage_stop();
}

static void begin_stop(void)
{
    if (g_state != ST_LISTEN) return;
    te_voice(VL_LISTEN_OFF);
    stop_capture();
    s_stop_deadline = esp_timer_get_time() / 1000 + TE_STOP_DRAIN_MS;
    set_state(ST_STOPPING);
    hal_report("EV waiting_for_queue pending=%d", xfer_pending());
}

static void save_clip(const char *trigger, const char *phrase)
{
    bool listening = g_state == ST_LISTEN || (g_state == ST_PROMPT && capture_is_recording());
    if (!listening) { hal_report("EV save_ignored reason=not_listening trigger=%s", trigger); return; }
    storage_request_save(trigger, phrase);
}

/* ---------------- Prompt ---------------- */
enum { P_NONE, P_RECORDING, P_WAIT_REPLY, P_WAIT_APPROVAL };
static int s_psub;
static te_state_t s_prev;
static int64_t s_pdeadline;
static uint32_t s_pid;
static uint8_t *s_frame;
#define FRAME_MAX (128 * 1024)

static void prompt_finish(const char *why)
{
    if (s_psub == P_RECORDING) {
        size_t n; uint32_t smp;
        free(capture_prompt_end(&n, &smp));
    }
    for (int i = 0; i < 500 && link_connected() && !link_tx_idle(); i++) vTaskDelay(pdMS_TO_TICKS(10));
    s_psub = P_NONE;
    set_state(s_prev);
    hal_report("EV prompt_end id=%lu why=%s back_to=%s", (unsigned long)s_pid, why, te_state_name(s_prev));
}

static void prompt_begin(void)
{
    if (g_state != ST_SLEEP && g_state != ST_LISTEN) return;
    if (!link_connected()) {
        te_voice(VL_OFFLINE);
        hal_report("EV prompt_offline state=%s", te_state_name(g_state));
        return;
    }
    s_prev = g_state;
    s_pid++;
    capture_prompt_begin();
    s_psub = P_RECORDING;
    s_pdeadline = esp_timer_get_time() / 1000 + TE_PROMPT_MAX_S * 1000;
    set_state(ST_PROMPT);
}

static void prompt_send(void)
{
    size_t alen = 0;
    uint32_t samples = 0;
    uint8_t *ad = capture_prompt_end(&alen, &samples);
    s_psub = P_NONE;
    size_t flen = capture_grab_frame(s_frame, FRAME_MAX, 1500);
    bool ok = link_sendf(MSG_PROMPT_BEGIN, "{\"id\":%lu,\"samples\":%lu,\"frame_bytes\":%u}", (unsigned long)s_pid,
                         (unsigned long)samples, (unsigned)flen);
    ok = ok && link_send(MSG_PROMPT_AUDIO, ad, alen);
    ok = ok && (!flen || link_send(MSG_PROMPT_FRAME, s_frame, flen));
    ok = ok && link_sendf(MSG_PROMPT_END, "{\"id\":%lu}", (unsigned long)s_pid);
    free(ad);
    hal_report("EV prompt_sent id=%lu samples=%lu adpcm=%u frame=%u ok=%d", (unsigned long)s_pid,
               (unsigned long)samples, (unsigned)alen, (unsigned)flen, ok);
    if (!ok) { te_voice(VL_OFFLINE); prompt_finish("offline"); return; }
    s_psub = P_WAIT_REPLY;
    s_pdeadline = esp_timer_get_time() / 1000 + TE_REPLY_TIMEOUT_MS;
}

static void prompt_reply(te_ev_t *ev)
{
    if (s_psub != P_WAIT_REPLY) { free(ev->data); return; }
    if (!ev->arg) {
        te_voice(VL_PROMPT_ERROR);
        free(ev->data);
        prompt_finish("llm_failed");
        return;
    }
    if (ev->data) hal_spk_pcm(ev->data, ev->len / 2);   /* "LLM reads out" */
    free(ev->data);
    if (ev->arg2) {
        te_voice(VL_ASK_APPROVAL);
        s_psub = P_WAIT_APPROVAL;
        s_pdeadline = esp_timer_get_time() / 1000 + TE_APPROVAL_TIMEOUT_MS;
        return;
    }
    prompt_finish("answered");
}

static void send_approval(bool yes, const char *how)
{
    link_sendf(MSG_APPROVAL, "{\"id\":%lu,\"approved\":%s,\"how\":\"%s\"}", (unsigned long)s_pid, yes ? "true" : "false", how);
    hal_report("EV approval id=%lu approved=%d how=%s", (unsigned long)s_pid, yes, how);
    prompt_finish("approval");
}

/* ---------------- sensors ---------------- */
static void apply_block(void) { xfer_block(s_block_heat || s_batt_crit); }

static void check_temp(void)
{
    static int lvl;
    static const float up[] = {TE_TEMP_WARM_C, TE_TEMP_HOT_C, TE_TEMP_CRIT_C};
    static const int caps[] = {TE_FPS_FULL, TE_FPS_REDUCED, TE_FPS_LOW, 0};
    float t = hal_temp_c();
    int n = lvl;
    while (n < 3 && t >= up[n]) n++;
    while (n > 0 && t < up[n - 1] - TE_TEMP_HYST_C) n--;
    if (n == lvl) return;
    hal_report("EV thermal level=%d temp=%.1f fps_cap=%d", n, t, caps[n]);
    if (n >= 2 && lvl < 2) te_voice(VL_TOO_HOT);
    if (n < 2 && lvl >= 2) te_voice(VL_COOLED);
    lvl = n;
    capture_set_fps_cap(0, caps[n]);
    s_block_heat = n >= 2;
    apply_block();
}

static void check_battery(void)
{
    int pct = hal_battery_pct();
    if (!s_batt_low && pct <= TE_BATT_LOW_PCT) {
        s_batt_low = true;
        te_voice(VL_LOW_BATTERY);
        capture_set_fps_cap(1, TE_FPS_REDUCED);
        hal_report("EV battery_low pct=%d", pct);
    } else if (s_batt_low && pct > TE_BATT_LOW_PCT + 5) {
        s_batt_low = false;
        capture_set_fps_cap(1, TE_FPS_FULL);
        hal_report("EV battery_ok pct=%d", pct);
    }
    if (!s_batt_crit && pct <= TE_BATT_CRIT_PCT) {
        s_batt_crit = true;
        te_voice(VL_BATTERY_CRITICAL);
        hal_report("EV battery_critical pct=%d state=%s", pct, te_state_name(g_state));
        if (g_state == ST_PROMPT) prompt_finish("battery");
        if (g_state == ST_LISTEN || g_state == ST_STOPPING) {
            stop_capture();
            set_state(ST_SLEEP);
        }
        apply_block();
    } else if (s_batt_crit && pct > TE_BATT_CRIT_PCT + 3) {
        s_batt_crit = false;
        apply_block();
    }
}

/* ---------------- buttons ---------------- */
typedef struct { bool down; int64_t t0; bool long_fired; } btn_t;

static void poll_buttons(void)
{
    static btn_t sb, pr;
    int64_t now = esp_timer_get_time() / 1000;
    bool l = hal_btn_level(HAL_BTN_SECOND_BRAIN);
    if (l && !sb.down) { sb = (btn_t){true, now, false}; }
    else if (l && sb.down && !sb.long_fired && now - sb.t0 >= TE_LONG_PRESS_MS) {
        sb.long_fired = true;
        te_post(&(te_ev_t){.type = EV_SB_LONG});
    } else if (!l && sb.down) {
        sb.down = false;
        if (!sb.long_fired && now - sb.t0 >= TE_DEBOUNCE_MS) te_post(&(te_ev_t){.type = EV_SB_SHORT});
    }
    l = hal_btn_level(HAL_BTN_PROMPT);
    if (l && !pr.down) {
        pr = (btn_t){true, now, false};
        te_post(&(te_ev_t){.type = EV_PR_DOWN});
    } else if (!l && pr.down) {
        pr.down = false;
        te_post(&(te_ev_t){.type = EV_PR_UP, .arg = (int)(now - pr.t0)});
    }
}

static void handle(te_ev_t *ev)
{
    switch (ev->type) {
    case EV_SB_SHORT:
        hal_report("EV button sb=short state=%s", te_state_name(g_state));
        if (g_state == ST_SLEEP) enter_listen();
        else if (g_state == ST_LISTEN) save_clip("button", "");
        break;
    case EV_SB_LONG:
        hal_report("EV button sb=long state=%s", te_state_name(g_state));
        if (g_state == ST_LISTEN) begin_stop();
        break;
    case EV_PR_DOWN:
        hal_report("EV button pr=down state=%s", te_state_name(g_state));
        if (g_state == ST_SLEEP || g_state == ST_LISTEN) prompt_begin();
        break;
    case EV_PR_UP:
        hal_report("EV button pr=up ms=%d", ev->arg);
        if (s_psub == P_RECORDING) prompt_send();
        else if (s_psub == P_WAIT_APPROVAL) send_approval(ev->arg < TE_LONG_PRESS_MS, ev->arg < TE_LONG_PRESS_MS ? "short" : "long");
        break;
    case EV_CMD_LISTEN: hal_report("EV cmd listen"); enter_listen(); break;
    case EV_CMD_STOP: hal_report("EV cmd stop"); begin_stop(); break;
    case EV_CMD_SAVE:
        hal_report("EV cmd save phrase=\"%s\"", ev->text);
        save_clip("phone", ev->text);
        break;
    case EV_CMD_STATS: metrics_set_period(ev->arg); metrics_report(); break;
    case EV_REPLY: prompt_reply(ev); break;
    case EV_CLIP_SAVED:
        if (ev->arg > 0) te_voice(VL_CLIP_SAVED);
        else te_voice(ev->arg == -2 ? VL_CARD_ERROR : VL_STORAGE_FULL);
        break;
    case EV_BLE_DOWN:
        hal_report("EV phone_disconnected state=%s", te_state_name(g_state));
        s_was_lost = true;
        if (g_state == ST_LISTEN) te_voice(VL_OFFLINE);
        if (g_state == ST_PROMPT) { te_voice(VL_OFFLINE); prompt_finish("phone_lost"); }
        break;
    case EV_BLE_UP:
        if (s_was_lost && g_state != ST_SLEEP) te_voice(VL_ONLINE);
        s_was_lost = false;
        xfer_kick();
        break;
    }
}

static void ctrl_task(void *arg)
{
    int64_t next_sensor = 0, next_stats = 0;
    extern int g_metrics_period_s;
    for (;;) {
        te_ev_t ev;
        if (xQueueReceive(s_evq, &ev, pdMS_TO_TICKS(10)) == pdTRUE) handle(&ev);
        poll_buttons();
        int64_t now = esp_timer_get_time() / 1000;
        if (s_psub == P_RECORDING && now > s_pdeadline) prompt_send();
        else if (s_psub == P_WAIT_REPLY && now > s_pdeadline) {
            hal_report("EV prompt_timeout id=%lu", (unsigned long)s_pid);
            te_voice(VL_PROMPT_ERROR);
            prompt_finish("timeout");
        } else if (s_psub == P_WAIT_APPROVAL && now > s_pdeadline) send_approval(false, "timeout");
        if (g_state == ST_STOPPING && (!xfer_pending() || !link_connected() || now > s_stop_deadline)) {
            hal_report("EV stop_done pending=%d", xfer_pending());
            set_state(ST_SLEEP);
        }
        if (now >= next_sensor) {
            next_sensor = now + 1000;
            check_temp();
            check_battery();
        }
        if (g_metrics_period_s > 0 && now >= next_stats) {
            next_stats = now + g_metrics_period_s * 1000LL;
            metrics_report();
        }
    }
}

void ctrl_init(void)
{
    s_evq = xQueueCreate(24, sizeof(te_ev_t));
    s_frame = heap_caps_malloc(FRAME_MAX, MALLOC_CAP_SPIRAM);
    set_state(ST_SLEEP);
    xTaskCreatePinnedToCore(ctrl_task, "control", 4096, NULL, 6, NULL, 0);
}
