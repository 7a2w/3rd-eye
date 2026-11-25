/* BLE and Wi-Fi replaced by two TCP connections to the mock phone, with a
 * throughput model. While Wi-Fi is on, both radios share one antenna by
 * time slicing, so each gets only part of its normal speed. */
#include <string.h>
#include "te_hal.h"
#include "sim_internal.h"
#include "lwip/sockets.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

static volatile int s_ble = -1, s_wifi = -1;
static volatile bool s_wifi_on;
static sim_pacer_t s_ble_pace, s_wifi_pace;
static SemaphoreHandle_t s_mtx;

/* The real BLE and Wi-Fi stacks take internal RAM that this build does not
 * have. These placeholder allocations stand in for their run-time heap
 * (est.: NimBLE about 40 KB always, Wi-Fi about 60 KB while it is on), so the
 * memory high-water marks include them. */
#define BLE_HEAP_EST  (40 * 1024)
#define WIFI_HEAP_EST (60 * 1024)
static void *s_ble_ballast, *s_wifi_ballast;

static void lazy_init(void)
{
    if (!s_mtx) s_mtx = xSemaphoreCreateMutex();
    if (!s_ble_ballast) s_ble_ballast = heap_caps_malloc(BLE_HEAP_EST, MALLOC_CAP_INTERNAL);
}

static int wait_readable(int fd, uint32_t timeout_ms)
{
    fd_set rf;
    FD_ZERO(&rf);
    FD_SET(fd, &rf);
    struct timeval tv = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    return select(fd + 1, &rf, NULL, NULL, &tv);
}

static int send_all(int fd, const uint8_t *p, size_t n)
{
    size_t done = 0;
    while (done < n) {
        int r = send(fd, p + done, n - done, 0);
        if (r <= 0) return -1;
        done += r;
    }
    return (int)done;
}

/* ---------------- BLE ---------------- */
bool hal_ble_connected(void) { return s_ble >= 0; }

esp_err_t hal_ble_try_connect(void)
{
    lazy_init();
    if (s_ble >= 0) return ESP_OK;
    int s = sim_tcp_connect(g_sim.ble_port, 1000);
    if (s < 0) return ESP_FAIL;
    s_ble = s;
    return ESP_OK;
}

void hal_ble_disconnect(void)
{
    lazy_init();
    xSemaphoreTake(s_mtx, portMAX_DELAY);
    if (s_ble >= 0) { shutdown(s_ble, SHUT_RDWR); close(s_ble); s_ble = -1; }
    xSemaphoreGive(s_mtx);
}

int hal_ble_send(const void *buf, size_t n, uint32_t timeout_ms)
{
    int fd = s_ble;
    if (fd < 0) return -1;
    uint32_t rate = g_sim.ble_Bps;
    if (s_wifi_on) rate = rate * g_sim.coex_ble_pct / 100;
    /* send in 244-byte pieces, the usual BLE notification payload with a 247-byte MTU */
    const uint8_t *p = buf;
    for (size_t o = 0; o < n; o += 244) {
        size_t k = n - o < 244 ? n - o : 244;
        sim_pace_buffered(&s_ble_pace, k, rate, 16 * 244);   /* about 16 queued notifications */
        if (send_all(fd, p + o, k) < 0) { hal_ble_disconnect(); return -1; }
    }
    return (int)n;
}

int hal_ble_recv(void *buf, size_t n, uint32_t timeout_ms)
{
    int fd = s_ble;
    if (fd < 0) { vTaskDelay(pdMS_TO_TICKS(timeout_ms)); return -1; }
    int w = wait_readable(fd, timeout_ms);
    if (w == 0) return 0;
    if (w < 0) { hal_ble_disconnect(); return -1; }
    int r = recv(fd, buf, n, 0);
    if (r <= 0) { hal_ble_disconnect(); return -1; }
    return r;
}

/* ---------------- Wi-Fi ---------------- */
bool hal_wifi_is_on(void) { return s_wifi_on; }

esp_err_t hal_wifi_on(uint32_t timeout_ms)
{
    lazy_init();
    if (s_wifi >= 0) return ESP_OK;
    s_wifi_on = true;
    if (!s_wifi_ballast) s_wifi_ballast = heap_caps_malloc(WIFI_HEAP_EST, MALLOC_CAP_INTERNAL);
    if (!s_wifi_ballast) hal_report("EV wifi_heap_alloc_failed");
    hal_power_hint(HAL_PWR_WIFI, true);
    hal_report("WIFI on");
    vTaskDelay(pdMS_TO_TICKS(g_sim.wifi_assoc_ms));    /* radio start + association, est. */
    int s = sim_tcp_connect(g_sim.wifi_port, timeout_ms);
    if (s < 0) { hal_wifi_off(); return ESP_FAIL; }
    s_wifi = s;
    return ESP_OK;
}

void hal_wifi_off(void)
{
    lazy_init();
    xSemaphoreTake(s_mtx, portMAX_DELAY);
    if (s_wifi >= 0) { shutdown(s_wifi, SHUT_RDWR); close(s_wifi); s_wifi = -1; }
    bool was = s_wifi_on;
    s_wifi_on = false;
    free(s_wifi_ballast);
    s_wifi_ballast = NULL;
    xSemaphoreGive(s_mtx);
    hal_power_hint(HAL_PWR_WIFI, false);
    if (was) hal_report("WIFI off");
}

int hal_wifi_send(const void *buf, size_t n, uint32_t timeout_ms)
{
    int fd = s_wifi;
    if (fd < 0) return -1;
    uint32_t rate = g_sim.wifi_Bps;
    if (s_ble >= 0) rate = rate * g_sim.coex_wifi_pct / 100;
    sim_pace_buffered(&s_wifi_pace, n, rate, 32768);       /* lwIP send buffer */
    struct timeval tv = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    return send_all(fd, buf, n);
}

int hal_wifi_recv(void *buf, size_t n, uint32_t timeout_ms)
{
    int fd = s_wifi;
    if (fd < 0) return -1;
    int w = wait_readable(fd, timeout_ms);
    if (w == 0) return 0;
    if (w < 0) return -1;
    int r = recv(fd, buf, n, 0);
    return r <= 0 ? -1 : r;
}
