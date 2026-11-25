#pragma once
#include <stdint.h>
#include <stdbool.h>

/* Speed-model and test-bench settings. Read at boot from the "simcfg"
 * flash partition, which the test harness writes into the QEMU flash image. */
typedef struct {
    char host_ip[16];
    int bench_port, ble_port, wifi_port;
    /* microSD card model */
    uint32_t sd_write_Bps;        /* sustained write speed */
    uint32_t sd_read_Bps;         /* sustained read speed */
    uint32_t sd_pause_every_kb;   /* mean data written between short card pauses */
    uint32_t sd_pause_min_ms, sd_pause_max_ms;
    uint32_t sd_long_every_mb;    /* mean data between long pauses */
    uint32_t sd_long_min_ms, sd_long_max_ms;
    uint32_t sd_meta_ms;          /* cost of one FAT metadata operation */
    /* radio model */
    uint32_t ble_Bps;             /* BLE application throughput */
    uint32_t wifi_Bps;            /* Wi-Fi application throughput */
    uint32_t coex_ble_pct;        /* share of BLE throughput kept while Wi-Fi is on */
    uint32_t coex_wifi_pct;       /* share of Wi-Fi throughput while BLE is also active */
    uint32_t wifi_assoc_ms;       /* time to bring Wi-Fi up and connect */
    /* power model */
    float batt_mah;
    float batt_start_pct;
    bool temp_model;
    float ambient_c;
    uint32_t seed;
} sim_cfg_t;

extern sim_cfg_t g_sim;
extern volatile int g_sim_cam_fps;      /* 0 when camera is off */
extern volatile bool g_sim_pwr[];       /* indexed by hal_pwr_t */
extern volatile uint64_t g_sim_sd_written, g_sim_sd_read;
extern volatile uint32_t g_sim_sd_pauses, g_sim_sd_pause_ms;
extern volatile uint32_t g_sim_cam_drops;
extern volatile int g_sim_force_stall_ms;

uint32_t sim_rand(void);
uint32_t sim_rand_range(uint32_t lo, uint32_t hi);
void sim_bench_send_line(const char *line);
void sim_btn_set(int which, bool level);
void sim_net_init(void);
int sim_tcp_connect(int port, uint32_t timeout_ms);
/* Holds the caller for `bytes` at `rate_Bps`, using a running deadline so that
 * many small calls add up to the right average speed. */
typedef struct { int64_t next_free_us; } sim_pacer_t;
void sim_pace(sim_pacer_t *p, uint32_t bytes, uint32_t rate_Bps);
/* Same, but the caller only waits once more than `buffer_bytes` are queued,
 * like a network stack's send buffer that the radio drains in the background. */
void sim_pace_buffered(sim_pacer_t *p, uint32_t bytes, uint32_t rate_Bps, uint32_t buffer_bytes);
