/* Pin map for the Seeed XIAO ESP32S3 Sense.
 * Camera and SD pins are fixed by the Sense expansion board (Seeed wiki).
 * Mic, speaker, button and battery pins are our proposal: check them
 * against the final wiring. */
#pragma once

/* OV5640 on the Sense camera connector */
#define PIN_CAM_XCLK   10
#define PIN_CAM_SIOD   40
#define PIN_CAM_SIOC   39
#define PIN_CAM_Y9     48
#define PIN_CAM_Y8     11
#define PIN_CAM_Y7     12
#define PIN_CAM_Y6     14
#define PIN_CAM_Y5     16
#define PIN_CAM_Y4     18
#define PIN_CAM_Y3     17
#define PIN_CAM_Y2     15
#define PIN_CAM_VSYNC  38
#define PIN_CAM_HREF   47
#define PIN_CAM_PCLK   13

/* microSD on the Sense board: only D0 is wired, so 1-bit SDMMC mode */
#define PIN_SD_CLK     7
#define PIN_SD_CMD     9
#define PIN_SD_D0      8
#define PIN_SD_CS_D3   21   /* card D3/CS line, held high in SDMMC mode (shared with the user LED) */

/* 2 x SPH0645 (I2S RX) and a MAX98357A-type amplifier (I2S TX) on one full-duplex I2S port */
#define PIN_I2S_BCLK   2    /* D1 */
#define PIN_I2S_WS     3    /* D2 */
#define PIN_I2S_DIN    4    /* D3: both mics' DOUT (front SEL=GND -> left, rear SEL=3V3 -> right) */
#define PIN_I2S_DOUT   43   /* D6: amplifier DIN */
#define PIN_AMP_SD     44   /* D7: amplifier shutdown, high = on */

/* buttons to GND, internal pull-ups */
#define PIN_BTN_SECOND_BRAIN 5   /* D4 */
#define PIN_BTN_PROMPT       6   /* D5 */

/* battery through a 2 x 100 k divider (the XIAO has no battery sense of its own) */
#define PIN_BATT_ADC   1    /* D0, ADC1 channel 0 */
#define BATT_DIVIDER   2
