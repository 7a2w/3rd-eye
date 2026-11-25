#include "te_app.h"
#include "te_hal.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "third_eye";

void app_main(void)
{
    ESP_ERROR_CHECK(te_hal_init());
    esp_chip_info_t ci;
    esp_chip_info(&ci);
    uint32_t flash = 0;
    esp_flash_get_size(NULL, &flash);
    hal_report("BOOT platform=%s cores=%d flash=%lu psram_total=%u int_total=%u int_free=%u",
               hal_platform_name(), ci.cores, (unsigned long)flash,
               (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
               (unsigned)heap_caps_get_total_size(MALLOC_CAP_INTERNAL),
               (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    xfer_init();
    esp_err_t e = storage_init();
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "storage init failed: %s", esp_err_to_name(e));
        hal_report("EV storage_failed err=%s", esp_err_to_name(e));
    }
    capture_init();
    ctrl_init();   /* before link_init: the BLE task posts events to the control queue */
    link_init();
    hal_report("READY int_free=%u ps_free=%u", (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
               (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
}
