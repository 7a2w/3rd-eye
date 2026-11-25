/* microSD on the XIAO Sense board, SDMMC host in 1-bit mode. */
#include <unistd.h>
#include "te_hal.h"
#include "xiao_pins.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"
#include "driver/sdmmc_host.h"
#include "driver/gpio.h"

static sdmmc_card_t *s_card;

esp_err_t hal_sd_mount(void)
{
    gpio_set_direction(PIN_SD_CS_D3, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_SD_CS_D3, 1);
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.flags = SDMMC_HOST_FLAG_1BIT;
    host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;
    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = 1;
    slot.clk = PIN_SD_CLK; slot.cmd = PIN_SD_CMD; slot.d0 = PIN_SD_D0;
    slot.flags |= SDMMC_SLOT_FLAG_INTERNAL_PULLUP;
    esp_vfs_fat_sdmmc_mount_config_t mc = {
        .format_if_mount_failed = false, .max_files = 8, .allocation_unit_size = 32 * 1024,
    };
    esp_err_t e = esp_vfs_fat_sdmmc_mount(HAL_SD_MOUNT, &host, &slot, &mc, &s_card);
    if (e == ESP_OK) sdmmc_card_print_info(stdout, s_card);
    return e;
}

int hal_sd_write(int fd, const void *buf, size_t n) { return write(fd, buf, n); }
int hal_sd_read(int fd, void *buf, size_t n) { return read(fd, buf, n); }
void hal_sd_meta_op(void) {}
esp_err_t hal_sd_space(uint64_t *total, uint64_t *free_b) { return esp_vfs_fat_info(HAL_SD_MOUNT, total, free_b); }
