#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "te_config.h"

/* ---------------- states and events ---------------- */
typedef enum { ST_SLEEP, ST_LISTEN, ST_PROMPT, ST_STOPPING } te_state_t;
const char *te_state_name(te_state_t s);
extern volatile te_state_t g_state;

typedef enum {
    EV_SB_SHORT, EV_SB_LONG, EV_PR_DOWN, EV_PR_UP,
    EV_CMD_LISTEN, EV_CMD_STOP, EV_CMD_SAVE, EV_CMD_STATS,
    EV_REPLY, EV_BLE_UP, EV_BLE_DOWN, EV_CLIP_SAVED,
} te_ev_type_t;

typedef struct {
    te_ev_type_t type;
    int arg;
    int arg2;
    char text[48];
    void *data;   /* EV_REPLY: PCM, freed by the receiver */
    size_t len;
} te_ev_t;
void te_post(const te_ev_t *ev);

/* ---------------- voice lines ---------------- */
typedef enum {
    VL_LISTEN_ON = 1, VL_LISTEN_OFF, VL_CLIP_SAVED, VL_OFFLINE, VL_ONLINE, VL_PROMPT_ERROR,
    VL_TOO_HOT, VL_COOLED, VL_LOW_BATTERY, VL_BATTERY_CRITICAL, VL_STORAGE_FULL, VL_ASK_APPROVAL,
    VL_CARD_ERROR,
} te_voice_t;
void te_voice(te_voice_t v);

/* ---------------- capture (camera + mics) ---------------- */
void capture_init(void);
void capture_start(void);          /* recording: camera + mics into the buffers */
void capture_stop(void);
bool capture_is_recording(void);
void capture_mic_on(bool on);      /* mic without recording, for prompts from Sleep */
void capture_set_fps_cap(int src, int fps);  /* src: 0 thermal, 1 battery, 2 back-pressure */
int capture_fps(void);
void capture_stream_enable(bool on);
void capture_prompt_begin(void);
/* Returns ADPCM bytes (PSRAM, caller frees) of the prompt voice. */
uint8_t *capture_prompt_end(size_t *len, uint32_t *samples);
/* Copies the next camera frame. Starts the camera briefly if it is off. */
size_t capture_grab_frame(uint8_t *dst, size_t max, uint32_t timeout_ms);
uint64_t audio_now(void);          /* absolute sample index of the newest sample */
uint64_t audio_first(void);        /* oldest sample index still in the ring */
bool audio_read(uint64_t from, int16_t *dst, size_t frames);  /* stereo, false if overwritten */

typedef struct {
    uint32_t frames_in, frames_to_wbuf, drop_wbuf, stream_pkts, stream_drops, mic_overruns;
} capture_stats_t;
void capture_get_stats(capture_stats_t *s);

/* ---------------- storage (SD writer, rolling buffer, clips) ---------------- */
esp_err_t storage_init(void);
bool wbuf_push(const uint8_t *jpeg, size_t len, uint32_t seq, int64_t ts_us);
int wbuf_fill_pct(void);
void storage_start(void);
void storage_stop(void);           /* close chunk, delete rolling files */
void storage_request_save(const char *trigger, const char *phrase);
typedef struct {
    uint32_t wbuf_used, wbuf_hwm, wbuf_size;
    uint32_t frames_written, chunks_created, chunks_deleted, chunk_count;
    uint32_t clips_saved, saves_merged, saves_refused, audio_overwritten;
    uint32_t max_write_stall_ms;
} storage_stats_t;
void storage_get_stats(storage_stats_t *s);
void clip_delete(uint32_t id);
bool storage_card_ok(void);
#define TE_CLIP_DIR_FMT "/sd/clips/c%04lu"

/* ---------------- phone link over BLE ---------------- */
enum {
    MSG_HELLO = 0x01, MSG_STATUS = 0x02, MSG_AUDIO = 0x03, MSG_EVENT = 0x04,
    MSG_PROMPT_BEGIN = 0x05, MSG_PROMPT_AUDIO = 0x06, MSG_PROMPT_FRAME = 0x07, MSG_PROMPT_END = 0x08,
    MSG_CLIP_QUEUED = 0x09, MSG_CLIP_DELETED = 0x0A, MSG_APPROVAL = 0x0B, MSG_STATS = 0x0C,
    /* Wi-Fi channel, earpiece -> phone */
    MSG_CLIP_BEGIN = 0x41, MSG_FILE_HDR = 0x42, MSG_DATA = 0x43, MSG_CLIP_END = 0x44,
    /* phone -> earpiece */
    MSG_PING = 0x81, MSG_CMD = 0x82, MSG_REPLY = 0x83, MSG_ACK = 0x84,
};
void link_init(void);
bool link_send(uint8_t type, const void *data, size_t len);
bool link_sendf(uint8_t type, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
bool link_connected(void);
bool link_tx_idle(void);
typedef struct { uint32_t reconnect_attempts, disconnects, tx_dropped, tx_bytes, rx_bytes; } link_stats_t;
void link_get_stats(link_stats_t *s);

/* ---------------- clip transfer over Wi-Fi, offline queue ---------------- */
void xfer_init(void);
void xfer_enqueue(uint32_t clip_id);
void xfer_kick(void);
int xfer_pending(void);
bool xfer_busy(void);
void xfer_block(bool blocked);     /* hot or flat battery: no Wi-Fi */
typedef struct { uint32_t sent, failed, nacked, attempts; uint64_t bytes; } xfer_stats_t;
void xfer_get_stats(xfer_stats_t *s);

/* ---------------- control and metrics ---------------- */
void ctrl_init(void);
void metrics_report(void);
void metrics_tasks_report(void);
void metrics_set_period(int s);

/* ---------------- helpers ---------------- */
bool json_str(const char *js, const char *key, char *out, size_t max);
bool json_int(const char *js, const char *key, long *out);
void frame_hdr(uint8_t *h, uint8_t type, uint32_t len);
