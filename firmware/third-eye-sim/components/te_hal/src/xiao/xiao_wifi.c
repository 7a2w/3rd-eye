/* Wi-Fi for clip transfers only. Joins the phone's hotspot (SSID and password
 * in NVS namespace "wifi", keys "ssid"/"pass", sent once by the phone app)
 * and opens a TCP connection to the phone at the hotspot gateway, port 5562.
 * The whole Wi-Fi stack is torn down afterwards to free RAM and power.
 * Team decision still open: earpiece soft-AP instead of the phone hotspot. */
#include <string.h>
#include "te_hal.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#define PHONE_PORT 5562
static const char *TAG = "xiao_wifi";
static EventGroupHandle_t s_eg;
static esp_netif_t *s_netif;
static int s_sock = -1;
static bool s_on, s_base_init;
#define GOT_IP BIT0

static void on_event(void *a, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(s_eg, GOT_IP);
}

esp_err_t hal_wifi_on(uint32_t timeout_ms)
{
    if (s_sock >= 0) return ESP_OK;
    if (!s_base_init) {
        esp_netif_init();
        esp_event_loop_create_default();
        s_eg = xEventGroupCreate();
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL);
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL);
        s_base_init = true;
    }
    wifi_config_t wc = {0};
    nvs_handle_t h;
    size_t n;
    if (nvs_open("wifi", NVS_READONLY, &h) != ESP_OK) return ESP_ERR_NOT_FOUND;
    n = sizeof wc.sta.ssid;
    nvs_get_str(h, "ssid", (char *)wc.sta.ssid, &n);
    n = sizeof wc.sta.password;
    nvs_get_str(h, "pass", (char *)wc.sta.password, &n);
    nvs_close(h);

    s_netif = esp_netif_create_default_wifi_sta();
    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wc);
    xEventGroupClearBits(s_eg, GOT_IP);
    esp_wifi_start();
    s_on = true;
    hal_report("WIFI on");
    if (!(xEventGroupWaitBits(s_eg, GOT_IP, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms)) & GOT_IP)) {
        hal_wifi_off();
        return ESP_ERR_TIMEOUT;
    }
    esp_netif_ip_info_t ip;
    esp_netif_get_ip_info(s_netif, &ip);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(PHONE_PORT)};
    a.sin_addr.s_addr = ip.gw.addr;   /* the phone is the hotspot gateway */
    s_sock = socket(AF_INET, SOCK_STREAM, 0);
    if (s_sock < 0 || connect(s_sock, (struct sockaddr *)&a, sizeof a) != 0) {
        ESP_LOGW(TAG, "phone not reachable");
        hal_wifi_off();
        return ESP_FAIL;
    }
    return ESP_OK;
}

void hal_wifi_off(void)
{
    if (s_sock >= 0) { close(s_sock); s_sock = -1; }
    if (!s_on) return;
    esp_wifi_stop();
    esp_wifi_deinit();
    esp_netif_destroy_default_wifi(s_netif);
    s_netif = NULL;
    s_on = false;
    hal_report("WIFI off");
}

bool hal_wifi_is_on(void) { return s_on; }

int hal_wifi_send(const void *buf, size_t n, uint32_t timeout_ms)
{
    struct timeval tv = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    setsockopt(s_sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    size_t d = 0;
    while (d < n) {
        int r = send(s_sock, (const uint8_t *)buf + d, n - d, 0);
        if (r <= 0) return -1;
        d += r;
    }
    return (int)n;
}

int hal_wifi_recv(void *buf, size_t n, uint32_t timeout_ms)
{
    if (s_sock < 0) return -1;
    fd_set rf;
    FD_ZERO(&rf);
    FD_SET(s_sock, &rf);
    struct timeval tv = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    int w = select(s_sock + 1, &rf, NULL, NULL, &tv);
    if (w <= 0) return w;
    int r = recv(s_sock, buf, n, 0);
    return r <= 0 ? -1 : r;
}
