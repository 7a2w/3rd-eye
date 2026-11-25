/* OV5640 through Espressif's esp32-camera driver: 1280x720 JPEG made by the
 * sensor, two frame buffers in PSRAM. The frame rate is set by skipping
 * frames; lowering the sensor's own frame rate would also save sensor power
 * (to do on the real board). */
#include "te_hal.h"
#include "xiao_pins.h"
#include "esp_camera.h"
#include "esp_timer.h"
#include "esp_log.h"

static bool s_on;
static int s_fps = 15;
static int64_t s_next_us;
static uint32_t s_seq;

esp_err_t hal_cam_start(int fps)
{
    s_fps = fps;
    if (s_on) return ESP_OK;
    camera_config_t c = {
        .pin_pwdn = -1, .pin_reset = -1, .pin_xclk = PIN_CAM_XCLK,
        .pin_sccb_sda = PIN_CAM_SIOD, .pin_sccb_scl = PIN_CAM_SIOC,
        .pin_d7 = PIN_CAM_Y9, .pin_d6 = PIN_CAM_Y8, .pin_d5 = PIN_CAM_Y7, .pin_d4 = PIN_CAM_Y6,
        .pin_d3 = PIN_CAM_Y5, .pin_d2 = PIN_CAM_Y4, .pin_d1 = PIN_CAM_Y3, .pin_d0 = PIN_CAM_Y2,
        .pin_vsync = PIN_CAM_VSYNC, .pin_href = PIN_CAM_HREF, .pin_pclk = PIN_CAM_PCLK,
        .xclk_freq_hz = 20000000, .ledc_timer = LEDC_TIMER_0, .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG, .frame_size = FRAMESIZE_HD, .jpeg_quality = 12,
        .fb_count = 2, .fb_location = CAMERA_FB_IN_PSRAM, .grab_mode = CAMERA_GRAB_LATEST,
    };
    esp_err_t e = esp_camera_init(&c);
    if (e == ESP_OK) { s_on = true; s_next_us = 0; }
    return e;
}

void hal_cam_stop(void)
{
    if (!s_on) return;
    esp_camera_deinit();
    s_on = false;
}

void hal_cam_set_fps(int fps) { s_fps = fps; }

bool hal_cam_get(hal_frame_t *f, uint32_t timeout_ms)
{
    if (!s_on) return false;
    for (;;) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (!fb) return false;
        s_seq++;
        int64_t now = esp_timer_get_time();
        if (now < s_next_us) { esp_camera_fb_return(fb); continue; }
        s_next_us = (s_next_us && now - s_next_us < 1000000 / s_fps ? s_next_us : now) + 1000000 / s_fps;
        f->buf = fb->buf; f->len = fb->len; f->ts_us = now; f->sensor_seq = s_seq; f->priv = fb;
        return true;
    }
}

void hal_cam_release(hal_frame_t *f) { esp_camera_fb_return((camera_fb_t *)f->priv); }
