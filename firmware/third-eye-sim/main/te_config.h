/* Tunable numbers for the Third Eye earpiece. Values marked (est.) are
 * starting guesses that must be tuned on the real board. */
#pragma once

/* video */
#define TE_FPS_FULL            15
#define TE_FPS_REDUCED         10
#define TE_FPS_LOW             5
#define TE_CHUNK_MS            2000      /* one rolling-buffer file per 2 s */
#define TE_CHUNKS_KEPT         15        /* 15 x 2 s = 30 s */
#define TE_WBUF_BYTES          (3 * 1024 * 1024)  /* PSRAM write buffer for SD pauses */
#define TE_STAGING_BYTES       (32 * 1024)        /* internal DMA buffer for SD writes */

/* audio */
#define TE_AUDIO_RATE          16000
#define TE_AUDIO_CLIP_S        30
#define TE_AUDIO_RING_S        34        /* 30 s clip + 4 s margin while the clip is written */
#define TE_AUDIO_BLOCK         320       /* 20 ms I2S reads */
#define TE_STREAM_BLOCK        800       /* 50 ms per ADPCM packet = 400 bytes + 4 header */
#define TE_PROMPT_MAX_S        10

/* buttons */
#define TE_LONG_PRESS_MS       1000
#define TE_DEBOUNCE_MS         30

/* phone link */
#define TE_RETRY_MS            5000      /* BLE reconnect and offline-queue retry period */
#define TE_LINK_TIMEOUT_MS     4000      /* phone silent this long = phone lost */
#define TE_STATUS_MS           5000
#define TE_REPLY_TIMEOUT_MS    15000     /* LLM answer timeout (est.) */
#define TE_APPROVAL_TIMEOUT_MS 10000
#define TE_ACK_TIMEOUT_MS      15000
#define TE_STOP_DRAIN_MS       60000     /* max wait for queued clips when Listen stops */
#define TE_XFER_CHUNK          16384

/* write-buffer back-pressure: lower the frame rate if the card cannot keep up */
#define TE_BP_HIGH_PCT         60
#define TE_BP_HIGH_MS          2000
#define TE_BP_LOW_PCT          15
#define TE_BP_LOW_MS           20000
#define TE_XFER_YIELD_PCT      25        /* clip reads pause while the write buffer is above this,
                                            so recording keeps the whole buffer for card pauses */

/* temperature (chip sensor, est.) */
#define TE_TEMP_WARM_C         65.0f     /* 10 fps */
#define TE_TEMP_HOT_C          75.0f     /* 5 fps, voice line, no Wi-Fi transfers */
#define TE_TEMP_CRIT_C         85.0f     /* camera off, audio only */
#define TE_TEMP_HYST_C         5.0f

/* battery (est.) */
#define TE_BATT_LOW_PCT        15        /* voice line, 10 fps */
#define TE_BATT_CRIT_PCT       5         /* stop recording, go to Sleep, no Wi-Fi */

/* storage */
#define TE_MIN_FREE_BYTES      (80ULL * 1024 * 1024)   /* refuse new clips below this */
#define TE_SAVE_MERGE_MS       3000      /* a second save within 3 s is merged into the first */
