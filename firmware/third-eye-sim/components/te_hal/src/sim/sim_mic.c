/* Simulated pair of SPH0645 mics on one I2S bus (front = left, rear = right).
 * Produces a 440 Hz "voice" tone with a slow loudness wobble plus noise, at
 * the real sample rate. The rear mic hears it one sample later (18 mm apart).
 * The SPH0645 puts 18 valid bits at the top of a 32-bit slot. */
#include <math.h>
#include "te_hal.h"
#include "sim_internal.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bool s_on;
static int64_t s_t0;
static uint64_t s_pos;
static int32_t s_prev;
static int16_t s_sin[64];

esp_err_t hal_mic_start(void)
{
    for (int i = 0; i < 64; i++) s_sin[i] = (int16_t)(32767 * sinf(2 * (float)M_PI * i / 64));
    s_on = true;
    s_t0 = esp_timer_get_time();
    s_pos = 0;
    hal_power_hint(HAL_PWR_MIC, true);
    return ESP_OK;
}

void hal_mic_stop(void) { s_on = false; hal_power_hint(HAL_PWR_MIC, false); }

size_t hal_mic_read(int32_t *lr, size_t frames, uint32_t timeout_ms)
{
    if (!s_on) { vTaskDelay(pdMS_TO_TICKS(timeout_ms)); return 0; }
    /* wait until these samples would have been captured in real time */
    int64_t due = s_t0 + (int64_t)(s_pos + frames) * 1000000 / HAL_MIC_RATE_HZ;
    int64_t now = esp_timer_get_time();
    if (due > now) vTaskDelay(pdMS_TO_TICKS((due - now) / 1000 + 1));
    else if (now - due > 200000) {   /* reader fell behind: an I2S DMA overrun drops old samples */
        s_pos = (uint64_t)(now - s_t0) * HAL_MIC_RATE_HZ / 1000000 - frames;
    }
    for (size_t i = 0; i < frames; i++, s_pos++) {
        /* phase step for 440 Hz with a 64-entry table: 440*64/16000 = 1.76 entries per sample */
        uint32_t ph = (uint32_t)((s_pos * 1760ULL / 1000ULL) & 63);
        int env = 6 + (int)((s_pos / 4000) % 5);             /* loudness wobble, like syllables */
        int32_t v = (int32_t)s_sin[ph] * env / 64;           /* about -20 dBFS after the +24 dB gain */
        int32_t noise = (int32_t)(sim_rand() & 0x7f) - 64;
        int32_t front = (v + noise) << 12;                   /* 16-bit value placed so >>12 recovers it */
        lr[2 * i] = front & ~0x3FFF;                         /* keep 18 valid bits */
        lr[2 * i + 1] = s_prev & ~0x3FFF;
        s_prev = front;
    }
    return frames;
}
