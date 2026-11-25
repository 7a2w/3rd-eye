/*
 * Third Eye hardware abstraction layer (HAL).
 *
 * Everything the application needs from the board goes through this header.
 * Two implementations exist:
 *   src/sim/   - QEMU build: synthetic camera/mics, test-bench buttons and
 *                sensors, TCP sockets instead of BLE and Wi-Fi, and a speed
 *                model for the microSD card and the radio.
 *   src/xiao/  - Real Seeed XIAO ESP32S3 Sense drivers (esp32-camera, I2S,
 *                SDMMC 1-bit, GPIO, ADC, temperature sensor, NimBLE, Wi-Fi).
 * Select with menuconfig: "Third Eye HAL" -> platform.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t te_hal_init(void);
const char *hal_platform_name(void);

/* ---------- camera (JPEG frames made by the sensor) ---------- */
typedef struct {
    const uint8_t *buf;
    size_t len;
    int64_t ts_us;     /* capture time */
    uint32_t sensor_seq; /* counts every frame the sensor produced, including ones the driver dropped */
    void *priv;
} hal_frame_t;

esp_err_t hal_cam_start(int fps);
void hal_cam_stop(void);
void hal_cam_set_fps(int fps);
bool hal_cam_get(hal_frame_t *f, uint32_t timeout_ms);
void hal_cam_release(hal_frame_t *f);

/* ---------- microphones: 2 x SPH0645, I2S stereo, 32-bit slots ---------- */
#define HAL_MIC_RATE_HZ 16000
esp_err_t hal_mic_start(void);
void hal_mic_stop(void);
/* Reads up to `frames` stereo frames (L,R interleaved int32). Blocks. Returns frames read. */
size_t hal_mic_read(int32_t *lr, size_t frames, uint32_t timeout_ms);

/* ---------- buttons (true = pressed) ---------- */
typedef enum { HAL_BTN_SECOND_BRAIN = 0, HAL_BTN_PROMPT = 1 } hal_btn_t;
bool hal_btn_level(hal_btn_t b);

/* ---------- sensors ---------- */
float hal_temp_c(void);      /* chip temperature */
int hal_battery_pct(void);   /* 0..100 */
int hal_battery_mv(void);

/* ---------- microSD (1-bit SDMMC), mounted at HAL_SD_MOUNT ---------- */
#define HAL_SD_MOUNT "/sd"
esp_err_t hal_sd_mount(void);
/* Raw file I/O helpers. The sim versions add the card speed model. */
int hal_sd_write(int fd, const void *buf, size_t n);
int hal_sd_read(int fd, void *buf, size_t n);
void hal_sd_meta_op(void);   /* call after rename/unlink/mkdir/open (models FAT metadata cost) */
esp_err_t hal_sd_space(uint64_t *total, uint64_t *free_b);

/* ---------- speaker ---------- */
void hal_spk_voice(int id, const char *name);
void hal_spk_pcm(const int16_t *pcm, size_t samples);

/* ---------- BLE link to the phone (byte stream) ---------- */
bool hal_ble_connected(void);
/* Start or retry a connection (sim: TCP connect; real: (re)start advertising). */
esp_err_t hal_ble_try_connect(void);
void hal_ble_disconnect(void);
/* Blocking send, rate limited by the link. Returns bytes sent or -1. */
int hal_ble_send(const void *buf, size_t n, uint32_t timeout_ms);
/* Returns bytes read, 0 on timeout, -1 on disconnect. */
int hal_ble_recv(void *buf, size_t n, uint32_t timeout_ms);

/* ---------- Wi-Fi link to the phone (only on during clip transfers) ---------- */
esp_err_t hal_wifi_on(uint32_t timeout_ms);
void hal_wifi_off(void);
bool hal_wifi_is_on(void);
int hal_wifi_send(const void *buf, size_t n, uint32_t timeout_ms);
int hal_wifi_recv(void *buf, size_t n, uint32_t timeout_ms);

/* ---------- test-bench reporting (sim: sent to the bench socket; real: logged) ---------- */
void hal_report(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* ---------- power hints (used by the sim battery/thermal model; no-op on real HW) ---------- */
typedef enum { HAL_PWR_CAM, HAL_PWR_MIC, HAL_PWR_WIFI, HAL_PWR_SPK, HAL_PWR__N } hal_pwr_t;
void hal_power_hint(hal_pwr_t what, bool on);

/* ---------- sim-only statistics (zeros on real HW) ---------- */
typedef struct {
    uint64_t sd_bytes_written;
    uint64_t sd_bytes_read;
    uint32_t sd_pauses;
    uint32_t sd_pause_ms_total;
    uint32_t cam_driver_drops;   /* frames the camera driver dropped because both buffers were busy */
    float battery_mah_used;
    float model_current_ma;
} hal_stats_t;
void hal_get_stats(hal_stats_t *s);

#ifdef __cplusplus
}
#endif
