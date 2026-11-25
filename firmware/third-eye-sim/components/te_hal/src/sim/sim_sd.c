/* microSD in QEMU: the real ESP-IDF SDMMC host driver in 1-bit mode on
 * QEMU's emulated card, plus a speed model. QEMU's card is much faster than
 * a real one, so every read and write is held until the modelled card
 * would have finished. Reads and writes share one bus (one mutex). */
#include <unistd.h>
#include "te_hal.h"
#include "sim_internal.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"
#include "driver/sdmmc_host.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "sim_sd";
static SemaphoreHandle_t s_bus;
static sim_pacer_t s_pacer;
static uint64_t s_since_pause, s_since_long;
static uint32_t s_next_pause, s_next_long;
static sdmmc_card_t *s_card;

static void card_pause(uint32_t ms)
{
    g_sim_sd_pauses++;
    g_sim_sd_pause_ms += ms;
    int64_t now = esp_timer_get_time();
    if (s_pacer.next_free_us < now) s_pacer.next_free_us = now;
    s_pacer.next_free_us += (int64_t)ms * 1000;
}

esp_err_t hal_sd_mount(void)
{
    s_bus = xSemaphoreCreateMutex();
    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    host.flags = SDMMC_HOST_FLAG_1BIT;               /* the Sense card slot only wires D0 */
    host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;
    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.width = 1;
    slot.clk = GPIO_NUM_7; slot.cmd = GPIO_NUM_9; slot.d0 = GPIO_NUM_8;
    esp_vfs_fat_sdmmc_mount_config_t mc = {
        .format_if_mount_failed = true, .max_files = 8, .allocation_unit_size = 32 * 1024,
    };
    esp_err_t e = esp_vfs_fat_sdmmc_mount(HAL_SD_MOUNT, &host, &slot, &mc, &s_card);
    if (e == ESP_OK) sdmmc_card_print_info(stdout, s_card);
    s_next_pause = sim_rand_range(g_sim.sd_pause_every_kb / 2, g_sim.sd_pause_every_kb * 3 / 2) * 1024ULL;
    s_next_long = sim_rand_range(g_sim.sd_long_every_mb / 2, g_sim.sd_long_every_mb * 3 / 2) * 1000000ULL;
    ESP_LOGI(TAG, "card model: write %lu B/s, read %lu B/s", (unsigned long)g_sim.sd_write_Bps,
             (unsigned long)g_sim.sd_read_Bps);
    return e;
}

int hal_sd_write(int fd, const void *buf, size_t n)
{
    xSemaphoreTake(s_bus, portMAX_DELAY);
    int r = write(fd, buf, n);
    if (r > 0) {
        g_sim_sd_written += r;
        s_since_pause += r;
        s_since_long += r;
        if (g_sim.sd_pause_every_kb && s_since_pause >= s_next_pause) {
            s_since_pause = 0;
            s_next_pause = sim_rand_range(g_sim.sd_pause_every_kb / 2, g_sim.sd_pause_every_kb * 3 / 2) * 1024ULL;
            card_pause(sim_rand_range(g_sim.sd_pause_min_ms, g_sim.sd_pause_max_ms));
        }
        if (g_sim.sd_long_every_mb && s_since_long >= s_next_long) {
            s_since_long = 0;
            s_next_long = sim_rand_range(g_sim.sd_long_every_mb / 2, g_sim.sd_long_every_mb * 3 / 2) * 1000000ULL;
            card_pause(sim_rand_range(g_sim.sd_long_min_ms, g_sim.sd_long_max_ms));
        }
        if (g_sim_force_stall_ms) { card_pause(g_sim_force_stall_ms); g_sim_force_stall_ms = 0; }
        sim_pace(&s_pacer, r, g_sim.sd_write_Bps);
    }
    xSemaphoreGive(s_bus);
    return r;
}

int hal_sd_read(int fd, void *buf, size_t n)
{
    xSemaphoreTake(s_bus, portMAX_DELAY);
    int r = read(fd, buf, n);
    if (r > 0) {
        g_sim_sd_read += r;
        sim_pace(&s_pacer, r, g_sim.sd_read_Bps);
    }
    xSemaphoreGive(s_bus);
    return r;
}

void hal_sd_meta_op(void)
{
    xSemaphoreTake(s_bus, portMAX_DELAY);
    sim_pace(&s_pacer, g_sim.sd_meta_ms * 1000, 1000000);
    xSemaphoreGive(s_bus);
}

esp_err_t hal_sd_space(uint64_t *total, uint64_t *free_b)
{
    return esp_vfs_fat_info(HAL_SD_MOUNT, total, free_b);
}
