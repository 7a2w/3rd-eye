/* BLE link to the phone with NimBLE: one GATT service with an RX
 * characteristic (phone writes) and a TX characteristic (earpiece notifies).
 * Presents a plain byte stream to the app, like the sim's TCP socket. */
#include <string.h>
#include "te_hal.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/stream_buffer.h"

static const char *TAG = "xiao_ble";

/* 128-bit UUIDs for the Third Eye service (random, ours) */
static const ble_uuid128_t SVC_UUID = BLE_UUID128_INIT(0x7e, 0x3e, 0x00, 0x01, 0x54, 0x45, 0x59, 0x45, 0x10, 0x00, 0x80, 0x00, 0x00, 0x80, 0x5f, 0x9b);
static const ble_uuid128_t RX_UUID = BLE_UUID128_INIT(0x7e, 0x3e, 0x00, 0x02, 0x54, 0x45, 0x59, 0x45, 0x10, 0x00, 0x80, 0x00, 0x00, 0x80, 0x5f, 0x9b);
static const ble_uuid128_t TX_UUID = BLE_UUID128_INIT(0x7e, 0x3e, 0x00, 0x03, 0x54, 0x45, 0x59, 0x45, 0x10, 0x00, 0x80, 0x00, 0x00, 0x80, 0x5f, 0x9b);

static uint16_t s_tx_handle;
static volatile uint16_t s_conn = BLE_HS_CONN_HANDLE_NONE;
static volatile bool s_subscribed;
static volatile uint16_t s_mtu = 23;
static uint8_t s_addr_type;
static StreamBufferHandle_t s_rx;
static void advertise(void);

static int chr_access(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint8_t tmp[256];
        uint16_t n = 0;
        while (ctxt->om) {
            n = OS_MBUF_PKTLEN(ctxt->om);
            if (n > sizeof tmp) n = sizeof tmp;
            ble_hs_mbuf_to_flat(ctxt->om, tmp, n, NULL);
            break;
        }
        if (xStreamBufferSend(s_rx, tmp, n, 0) != n) ESP_LOGW(TAG, "rx overflow");
    }
    return 0;
}

static const struct ble_gatt_svc_def s_svcs[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &SVC_UUID.u,
     .characteristics = (struct ble_gatt_chr_def[]){
         {.uuid = &RX_UUID.u, .access_cb = chr_access, .flags = BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP},
         {.uuid = &TX_UUID.u, .access_cb = chr_access, .flags = BLE_GATT_CHR_F_NOTIFY, .val_handle = &s_tx_handle},
         {0}}},
    {0}};

static int gap_event(struct ble_gap_event *ev, void *arg)
{
    switch (ev->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (ev->connect.status == 0) {
            s_conn = ev->connect.conn_handle;
            /* 30 to 50 ms interval saves power and still carries the audio stream */
            struct ble_gap_upd_params p = {.itvl_min = 24, .itvl_max = 40, .latency = 0,
                                           .supervision_timeout = 400};
            ble_gap_update_params(s_conn, &p);
        } else advertise();
        break;
    case BLE_GAP_EVENT_DISCONNECT:
        s_conn = BLE_HS_CONN_HANDLE_NONE;
        s_subscribed = false;
        advertise();
        break;
    case BLE_GAP_EVENT_SUBSCRIBE:
        if (ev->subscribe.attr_handle == s_tx_handle) s_subscribed = ev->subscribe.cur_notify;
        break;
    case BLE_GAP_EVENT_MTU:
        s_mtu = ev->mtu.value;
        break;
    case BLE_GAP_EVENT_ADV_COMPLETE:
        advertise();
        break;
    default:
        break;
    }
    return 0;
}

static void advertise(void)
{
    struct ble_hs_adv_fields f = {0};
    f.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    const char *name = ble_svc_gap_device_name();
    f.name = (uint8_t *)name;
    f.name_len = strlen(name);
    f.name_is_complete = 1;
    ble_gap_adv_set_fields(&f);
    struct ble_gap_adv_params ap = {.conn_mode = BLE_GAP_CONN_MODE_UND, .disc_mode = BLE_GAP_DISC_MODE_GEN};
    ble_gap_adv_start(s_addr_type, NULL, BLE_HS_FOREVER, &ap, gap_event, NULL);
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    ble_hs_id_infer_auto(0, &s_addr_type);
    advertise();
}

static void host_task(void *p)
{
    nimble_port_run();
    nimble_port_freertos_deinit();
}

esp_err_t xiao_ble_init(void)
{
    s_rx = xStreamBufferCreateWithCaps(32 * 1024, 1, MALLOC_CAP_SPIRAM);
    esp_err_t e = nimble_port_init();
    if (e != ESP_OK) return e;
    ble_hs_cfg.sync_cb = on_sync;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_svc_gap_device_name_set("ThirdEye");
    ble_gatts_count_cfg(s_svcs);
    ble_gatts_add_svcs(s_svcs);
    nimble_port_freertos_init(host_task);
    return ESP_OK;
}

bool hal_ble_connected(void) { return s_conn != BLE_HS_CONN_HANDLE_NONE && s_subscribed; }
esp_err_t hal_ble_try_connect(void) { return hal_ble_connected() ? ESP_OK : ESP_FAIL; }  /* advertising runs all the time */
void hal_ble_disconnect(void)
{
    if (s_conn != BLE_HS_CONN_HANDLE_NONE) ble_gap_terminate(s_conn, BLE_ERR_REM_USER_CONN_TERM);
}

int hal_ble_send(const void *buf, size_t n, uint32_t timeout_ms)
{
    const uint8_t *p = buf;
    size_t chunk = s_mtu > 3 ? s_mtu - 3 : 20;
    TickType_t until = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    for (size_t o = 0; o < n;) {
        if (!hal_ble_connected()) return -1;
        size_t k = n - o < chunk ? n - o : chunk;
        struct os_mbuf *om = ble_hs_mbuf_from_flat(p + o, k);
        if (om && ble_gatts_notify_custom(s_conn, s_tx_handle, om) == 0) { o += k; continue; }
        if (xTaskGetTickCount() > until) return -1;
        vTaskDelay(pdMS_TO_TICKS(5));   /* controller buffers full: wait for the next connection event */
    }
    return (int)n;
}

int hal_ble_recv(void *buf, size_t n, uint32_t timeout_ms)
{
    if (!hal_ble_connected()) { vTaskDelay(pdMS_TO_TICKS(timeout_ms)); return -1; }
    return (int)xStreamBufferReceive(s_rx, buf, n, pdMS_TO_TICKS(timeout_ms));
}
