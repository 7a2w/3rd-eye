/* Sim platform core: config, network, test-bench socket, buttons, sensors,
 * speaker, and the battery/thermal model. */
#include <string.h>
#include <stdarg.h>
#include <stdlib.h>
#include <math.h>
#include "te_hal.h"
#include "sim_internal.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_partition.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_eth.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

static const char *TAG = "sim";

sim_cfg_t g_sim = {
    .host_ip = "10.0.2.2",
    .bench_port = 5560, .ble_port = 5561, .wifi_port = 5562,
    .sd_write_Bps = 1600000, .sd_read_Bps = 2000000,
    .sd_pause_every_kb = 2048, .sd_pause_min_ms = 40, .sd_pause_max_ms = 250,
    .sd_long_every_mb = 200, .sd_long_min_ms = 400, .sd_long_max_ms = 800,
    .sd_meta_ms = 4,
    .ble_Bps = 60000, .wifi_Bps = 1500000,
    .coex_ble_pct = 40, .coex_wifi_pct = 70, .wifi_assoc_ms = 1500,
    .batt_mah = 1200, .batt_start_pct = 100, .temp_model = true, .ambient_c = 25,
    .seed = 12345,
};

volatile int g_sim_cam_fps;
volatile bool g_sim_pwr[HAL_PWR__N];
volatile uint64_t g_sim_sd_written, g_sim_sd_read;
volatile uint32_t g_sim_sd_pauses, g_sim_sd_pause_ms;
volatile uint32_t g_sim_cam_drops;
volatile int g_sim_force_stall_ms;

static uint32_t s_rng;
static SemaphoreHandle_t s_rng_mtx;
uint32_t sim_rand(void)
{
    xSemaphoreTake(s_rng_mtx, portMAX_DELAY);
    s_rng ^= s_rng << 13; s_rng ^= s_rng >> 17; s_rng ^= s_rng << 5;
    uint32_t r = s_rng;
    xSemaphoreGive(s_rng_mtx);
    return r;
}
uint32_t sim_rand_range(uint32_t lo, uint32_t hi) { return hi <= lo ? lo : lo + sim_rand() % (hi - lo + 1); }

void sim_pace(sim_pacer_t *p, uint32_t bytes, uint32_t rate_Bps) { sim_pace_buffered(p, bytes, rate_Bps, 0); }

void sim_pace_buffered(sim_pacer_t *p, uint32_t bytes, uint32_t rate_Bps, uint32_t buffer_bytes)
{
    if (!rate_Bps) return;
    int64_t now = esp_timer_get_time();
    if (p->next_free_us < now) p->next_free_us = now;
    p->next_free_us += (int64_t)bytes * 1000000 / rate_Bps;
    int64_t wait = p->next_free_us - now - (int64_t)buffer_bytes * 1000000 / rate_Bps;
    if (wait > 1000) vTaskDelay(pdMS_TO_TICKS(wait / 1000));
}

/* ---------------- config from the simcfg partition ---------------- */
static void cfg_set(const char *k, const char *v)
{
#define U(name) if (!strcmp(k, #name)) { g_sim.name = strtoul(v, NULL, 10); return; }
#define F(name) if (!strcmp(k, #name)) { g_sim.name = strtof(v, NULL); return; }
    if (!strcmp(k, "host_ip")) { strlcpy(g_sim.host_ip, v, sizeof g_sim.host_ip); return; }
    U(bench_port) U(ble_port) U(wifi_port) U(sd_write_Bps) U(sd_read_Bps) U(sd_pause_every_kb)
    U(sd_pause_min_ms) U(sd_pause_max_ms) U(sd_long_every_mb) U(sd_long_min_ms) U(sd_long_max_ms)
    U(sd_meta_ms) U(ble_Bps) U(wifi_Bps) U(coex_ble_pct) U(coex_wifi_pct) U(wifi_assoc_ms) U(seed)
    F(batt_mah) F(batt_start_pct) F(ambient_c)
    if (!strcmp(k, "temp_model")) { g_sim.temp_model = atoi(v); return; }
    ESP_LOGW(TAG, "unknown simcfg key %s", k);
#undef U
#undef F
}

static void cfg_load(void)
{
    const esp_partition_t *p = esp_partition_find_first(0x40, 0x00, "simcfg");
    if (!p) { ESP_LOGW(TAG, "no simcfg partition, using defaults"); return; }
    static char buf[1024];
    if (esp_partition_read(p, 0, buf, sizeof buf - 1) != ESP_OK) return;
    buf[sizeof buf - 1] = 0;
    char *save = NULL;
    for (char *line = strtok_r(buf, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        if ((uint8_t)line[0] == 0xff || line[0] == 0) break;
        char *eq = strchr(line, '=');
        if (!eq) continue;
        *eq = 0;
        cfg_set(line, eq + 1);
    }
}

/* ---------------- network (QEMU OpenCores Ethernet + user-mode NAT) ---------------- */
static esp_netif_t *s_netif;
void sim_net_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_config_t cfg = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&cfg);
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.autonego_timeout_ms = 100;
    esp_eth_mac_t *mac = esp_eth_mac_new_openeth(&mac_config);
    esp_eth_phy_t *phy = esp_eth_phy_new_dp83848(&phy_config);
    esp_eth_config_t ec = ETH_DEFAULT_CONFIG(mac, phy);
    esp_eth_handle_t h;
    ESP_ERROR_CHECK(esp_eth_driver_install(&ec, &h));
    ESP_ERROR_CHECK(esp_netif_attach(s_netif, esp_eth_new_netif_glue(h)));
    ESP_ERROR_CHECK(esp_eth_start(h));
    esp_netif_ip_info_t ip = {0};
    for (int i = 0; i < 100 && !ip.ip.addr; i++) {
        vTaskDelay(pdMS_TO_TICKS(100));
        esp_netif_get_ip_info(s_netif, &ip);
    }
    ESP_LOGI(TAG, "network up, ip " IPSTR, IP2STR(&ip.ip));
}

int sim_tcp_connect(int port, uint32_t timeout_ms)
{
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return -1;
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(port)};
    a.sin_addr.s_addr = inet_addr(g_sim.host_ip);
    struct timeval tv = {.tv_sec = timeout_ms / 1000, .tv_usec = (timeout_ms % 1000) * 1000};
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    if (connect(s, (struct sockaddr *)&a, sizeof a) != 0) { close(s); return -1; }
    int one = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    return s;
}

/* ---------------- test bench socket ---------------- */
static int s_bench = -1;
static SemaphoreHandle_t s_bench_mtx;
static volatile bool s_btn[2];
static volatile float s_temp_override = NAN;
static volatile float s_batt_override = NAN;

void sim_bench_send_line(const char *line)
{
    if (s_bench < 0) return;
    xSemaphoreTake(s_bench_mtx, portMAX_DELAY);
    size_t n = strlen(line);
    send(s_bench, line, n, 0);
    if (!n || line[n - 1] != '\n') send(s_bench, "\n", 1, 0);
    xSemaphoreGive(s_bench_mtx);
}

void hal_report(const char *fmt, ...)
{
    char buf[768];
    int64_t t = esp_timer_get_time() / 1000;
    int o = snprintf(buf, sizeof buf, "@%lld ", t);
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf + o, sizeof buf - o, fmt, ap);
    va_end(ap);
    sim_bench_send_line(buf);
}

void sim_btn_set(int which, bool level) { s_btn[which] = level; }
bool hal_btn_level(hal_btn_t b) { return s_btn[b]; }

typedef struct { int which; int ms; } press_t;
static void press_task(void *arg)
{
    press_t p = *(press_t *)arg;
    free(arg);
    s_btn[p.which] = true;
    vTaskDelay(pdMS_TO_TICKS(p.ms));
    s_btn[p.which] = false;
    vTaskDelete(NULL);
}
static void bench_press(int which, int ms)
{
    press_t *p = malloc(sizeof *p);
    p->which = which; p->ms = ms;
    xTaskCreate(press_task, "press", 2048, p, 8, NULL);
}

static void bench_cmd(char *line)
{
    char a[16] = {0}, b[16] = {0};
    int v = 0;
    float f = 0;
    if (sscanf(line, "BTN %15s %15s %d", a, b, &v) >= 2) {
        int w = !strcmp(a, "PR") ? HAL_BTN_PROMPT : HAL_BTN_SECOND_BRAIN;
        if (!strcmp(b, "tap")) bench_press(w, 150);
        else if (!strcmp(b, "hold")) bench_press(w, v ? v : 2000);
        else if (!strcmp(b, "down")) s_btn[w] = true;
        else if (!strcmp(b, "up")) s_btn[w] = false;
    } else if (!strncmp(line, "TEMP model", 10)) {
        s_temp_override = NAN;
    } else if (sscanf(line, "TEMP %f", &f) == 1) {
        s_temp_override = f;
    } else if (!strncmp(line, "BATT model", 10)) {
        s_batt_override = NAN;
    } else if (sscanf(line, "BATT %f", &f) == 1) {
        s_batt_override = f;
    } else if (sscanf(line, "SD_RATE %d", &v) == 1) {
        g_sim.sd_write_Bps = v;
    } else if (sscanf(line, "BLE_RATE %d", &v) == 1) {
        g_sim.ble_Bps = v;
    } else if (sscanf(line, "SD_STALL %d", &v) == 1) {
        g_sim_force_stall_ms = v;
    } else {
        ESP_LOGW(TAG, "bench: unknown '%s'", line);
    }
}

static void bench_task(void *arg)
{
    char line[128];
    int n = 0;
    for (;;) {
        char c;
        int r = recv(s_bench, &c, 1, 0);
        if (r <= 0) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
        if (c == '\n') { line[n] = 0; bench_cmd(line); n = 0; }
        else if (n < (int)sizeof line - 1) line[n++] = c;
    }
}

/* ---------------- battery and thermal model (all currents are estimates) ---------------- */
static float s_mah_used, s_current_ma, s_temp_c = 25;
static uint64_t s_last_sd;
static int64_t s_spk_until_us;

static float model_current_ma(float sd_MBps)
{
    /* From docs/hardware-and-power.md, XIAO "after savings" column (est.). */
    float i = 3.0f + 10.0f;                              /* misc + BLE link */
    bool cam = g_sim_cam_fps > 0, mic = g_sim_pwr[HAL_PWR_MIC];
    i += (cam || mic) ? 45.0f : 20.0f;                   /* CPU busy vs idle with BLE */
    if (cam) i += 45.0f + 3.0f * g_sim_cam_fps           /* OV5640: 90 mA at 15 fps, 60 at 5 */
               + 7.5f + 0.5f * g_sim_cam_fps;            /* camera data transfer + PSRAM */
    i += 5.0f + 25.0f * sd_MBps;                         /* microSD: about 30 mA at 1 MB/s */
    if (mic) i += 1.2f;
    if (g_sim_pwr[HAL_PWR_WIFI]) i += 100.0f;            /* Wi-Fi active, est. */
    i += (esp_timer_get_time() < s_spk_until_us) ? 20.0f : 0.5f;
    return i;
}

static void power_task(void *arg)
{
    const float usable = 0.9f;
    s_mah_used = g_sim.batt_mah * usable * (1.0f - g_sim.batt_start_pct / 100.0f);
    s_temp_c = g_sim.ambient_c + 10;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        uint64_t w = g_sim_sd_written + g_sim_sd_read;
        float sd_MBps = (w - s_last_sd) / 1e6f;
        s_last_sd = w;
        s_current_ma = model_current_ma(sd_MBps);
        s_mah_used += s_current_ma / 3600.0f;
        /* first-order thermal model: 40 C per watt above ambient, 120 s time constant (est.) */
        float target = g_sim.ambient_c + 40.0f * (s_current_ma * 3.8f / 1000.0f);
        s_temp_c += (target - s_temp_c) * (1.0f / 120.0f);
    }
}

float hal_temp_c(void)
{
    if (!isnan(s_temp_override)) return s_temp_override;
    return g_sim.temp_model ? s_temp_c : 45.0f;
}

int hal_battery_pct(void)
{
    if (!isnan(s_batt_override)) return (int)s_batt_override;
    float usable = g_sim.batt_mah * 0.9f;
    float pct = 100.0f * (usable - s_mah_used) / usable;
    return pct < 0 ? 0 : (int)(pct + 0.5f);
}

int hal_battery_mv(void) { return 3300 + hal_battery_pct() * 9; }

void hal_power_hint(hal_pwr_t what, bool on) { g_sim_pwr[what] = on; }

void hal_get_stats(hal_stats_t *s)
{
    s->sd_bytes_written = g_sim_sd_written;
    s->sd_bytes_read = g_sim_sd_read;
    s->sd_pauses = g_sim_sd_pauses;
    s->sd_pause_ms_total = g_sim_sd_pause_ms;
    s->cam_driver_drops = g_sim_cam_drops;
    s->battery_mah_used = s_mah_used;
    s->model_current_ma = s_current_ma;
}

/* ---------------- speaker ---------------- */
void hal_spk_voice(int id, const char *name)
{
    s_spk_until_us = esp_timer_get_time() + 1500000;
    hal_report("VOICE %d %s", id, name);
}

void hal_spk_pcm(const int16_t *pcm, size_t samples)
{
    s_spk_until_us = esp_timer_get_time() + (int64_t)samples * 1000000 / 16000;
    hal_report("SPK_PCM samples=%u", (unsigned)samples);
    vTaskDelay(pdMS_TO_TICKS(samples * 1000 / 16000));
}

const char *hal_platform_name(void) { return "sim-qemu"; }

esp_err_t te_hal_init(void)
{
    s_rng_mtx = xSemaphoreCreateMutex();
    s_bench_mtx = xSemaphoreCreateMutex();
    cfg_load();
    s_rng = g_sim.seed ? g_sim.seed : 1;
    sim_net_init();
    for (int i = 0; i < 50 && s_bench < 0; i++) {
        s_bench = sim_tcp_connect(g_sim.bench_port, 1000);
        if (s_bench < 0) vTaskDelay(pdMS_TO_TICKS(200));
    }
    if (s_bench >= 0) xTaskCreatePinnedToCore(bench_task, "bench", 3072, NULL, 9, NULL, 0);
    else ESP_LOGW(TAG, "no test bench connected");
    xTaskCreatePinnedToCore(power_task, "power_model", 2560, NULL, 3, NULL, 0);
    hal_report("SIMCFG sd_write_Bps=%lu ble_Bps=%lu wifi_Bps=%lu seed=%lu",
               (unsigned long)g_sim.sd_write_Bps, (unsigned long)g_sim.ble_Bps,
               (unsigned long)g_sim.wifi_Bps, (unsigned long)g_sim.seed);
    return ESP_OK;
}
