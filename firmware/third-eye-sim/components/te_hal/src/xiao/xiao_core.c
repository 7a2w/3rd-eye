/* XIAO ESP32S3 Sense: buttons, temperature, battery, speaker, reporting. */
#include <math.h>
#include <stdarg.h>
#include <string.h>
#include "te_hal.h"
#include "xiao_pins.h"
#include "driver/gpio.h"
#include "driver/temperature_sensor.h"
#include "driver/i2s_std.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "xiao";
static temperature_sensor_handle_t s_tsens;
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;
extern i2s_chan_handle_t g_i2s_tx;           /* created with the mic channel in xiao_mic.c */
esp_err_t xiao_i2s_init(void);
esp_err_t xiao_ble_init(void);

const char *hal_platform_name(void) { return "xiao-esp32s3-sense"; }

void hal_report(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    ESP_LOGI("report", "%s", buf);
}

esp_err_t te_hal_init(void)
{
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        e = nvs_flash_init();
    }
    ESP_ERROR_CHECK(e);
    gpio_config_t btn = {
        .pin_bit_mask = (1ULL << PIN_BTN_SECOND_BRAIN) | (1ULL << PIN_BTN_PROMPT),
        .mode = GPIO_MODE_INPUT, .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&btn);
    gpio_config_t amp = {.pin_bit_mask = 1ULL << PIN_AMP_SD, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&amp);
    gpio_set_level(PIN_AMP_SD, 0);

    temperature_sensor_config_t tc = TEMPERATURE_SENSOR_CONFIG_DEFAULT(20, 100);
    ESP_ERROR_CHECK(temperature_sensor_install(&tc, &s_tsens));
    temperature_sensor_enable(s_tsens);

    adc_oneshot_unit_init_cfg_t uc = {.unit_id = ADC_UNIT_1};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&uc, &s_adc));
    adc_oneshot_chan_cfg_t cc = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_oneshot_config_channel(s_adc, ADC_CHANNEL_0, &cc);
    adc_cali_curve_fitting_config_t cf = {.unit_id = ADC_UNIT_1, .chan = ADC_CHANNEL_0,
                                          .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    if (adc_cali_create_scheme_curve_fitting(&cf, &s_cali) != ESP_OK) s_cali = NULL;

    ESP_ERROR_CHECK(xiao_i2s_init());
    ESP_ERROR_CHECK(xiao_ble_init());
    ESP_LOGI(TAG, "XIAO HAL ready");
    return ESP_OK;
}

bool hal_btn_level(hal_btn_t b)
{
    return gpio_get_level(b == HAL_BTN_PROMPT ? PIN_BTN_PROMPT : PIN_BTN_SECOND_BRAIN) == 0;
}

float hal_temp_c(void)
{
    float c = NAN;
    temperature_sensor_get_celsius(s_tsens, &c);
    return c;
}

int hal_battery_mv(void)
{
    int raw = 0, mv = 0;
    adc_oneshot_read(s_adc, ADC_CHANNEL_0, &raw);
    if (s_cali) adc_cali_raw_to_voltage(s_cali, raw, &mv);
    else mv = raw * 3100 / 4095;
    return mv * BATT_DIVIDER;
}

int hal_battery_pct(void)
{
    /* rough LiPo resting-voltage curve (est.); replace with a measured curve */
    static const int mv[] = {3300, 3600, 3700, 3750, 3800, 3870, 3950, 4050, 4200};
    static const int pc[] = {0, 5, 15, 25, 40, 55, 70, 85, 100};
    int v = hal_battery_mv();
    if (v <= mv[0]) return 0;
    for (int i = 1; i < 9; i++)
        if (v < mv[i]) return pc[i - 1] + (pc[i] - pc[i - 1]) * (v - mv[i - 1]) / (mv[i] - mv[i - 1]);
    return 100;
}

void hal_spk_pcm(const int16_t *pcm, size_t samples)
{
    gpio_set_level(PIN_AMP_SD, 1);
    int32_t buf[256];
    for (size_t o = 0; o < samples; o += 128) {
        size_t k = samples - o < 128 ? samples - o : 128;
        for (size_t i = 0; i < k; i++) buf[2 * i] = buf[2 * i + 1] = (int32_t)pcm[o + i] << 16;
        size_t w;
        i2s_channel_write(g_i2s_tx, buf, k * 8, &w, portMAX_DELAY);
    }
    gpio_set_level(PIN_AMP_SD, 0);
}

void hal_spk_voice(int id, const char *name)
{
    /* Placeholder until recorded voice lines are stored in flash: `id` short beeps. */
    static int16_t tone[1600];
    for (int i = 0; i < 1600; i++) tone[i] = (int16_t)(6000 * sinf(2 * (float)M_PI * 880 * i / 16000));
    ESP_LOGI(TAG, "voice line %d (%s)", id, name);
    for (int n = 0; n < id && n < 6; n++) {
        hal_spk_pcm(tone, 1600);
        vTaskDelay(pdMS_TO_TICKS(80));
    }
}

void hal_power_hint(hal_pwr_t what, bool on) {}

void hal_get_stats(hal_stats_t *s) { memset(s, 0, sizeof *s); }
