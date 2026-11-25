/* Two SPH0645 mics (RX) and the speaker amplifier (TX) on one full-duplex
 * I2S port: 16 kHz, 32-bit stereo slots, shared BCLK and WS. */
#include "te_hal.h"
#include "xiao_pins.h"
#include "driver/i2s_std.h"

i2s_chan_handle_t g_i2s_tx;
static i2s_chan_handle_t s_rx;
static bool s_rx_on;

esp_err_t xiao_i2s_init(void)
{
    i2s_chan_config_t cc = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    cc.dma_desc_num = 4;      /* 4 x 10 ms: keeps internal DMA RAM to about 5 KB per direction */
    cc.dma_frame_num = 160;
    esp_err_t e = i2s_new_channel(&cc, &g_i2s_tx, &s_rx);
    if (e != ESP_OK) return e;
    i2s_std_config_t sc = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(HAL_MIC_RATE_HZ),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {.mclk = I2S_GPIO_UNUSED, .bclk = PIN_I2S_BCLK, .ws = PIN_I2S_WS,
                     .dout = PIN_I2S_DOUT, .din = PIN_I2S_DIN},
    };
    if ((e = i2s_channel_init_std_mode(g_i2s_tx, &sc)) != ESP_OK) return e;
    if ((e = i2s_channel_init_std_mode(s_rx, &sc)) != ESP_OK) return e;
    return i2s_channel_enable(g_i2s_tx);
}

esp_err_t hal_mic_start(void)
{
    if (s_rx_on) return ESP_OK;
    s_rx_on = true;
    return i2s_channel_enable(s_rx);
}

void hal_mic_stop(void)
{
    if (!s_rx_on) return;
    i2s_channel_disable(s_rx);
    s_rx_on = false;
}

size_t hal_mic_read(int32_t *lr, size_t frames, uint32_t timeout_ms)
{
    size_t got = 0;
    if (i2s_channel_read(s_rx, lr, frames * 8, &got, timeout_ms) != ESP_OK) return 0;
    return got / 8;
}
