# Third Eye: Hardware, Camera and Power

Best Team, CEN100 section 16. Draft for the design notebook, November 19, 2026.

Numbers marked **(est.)** are our own estimates or calculations and must be measured on the real hardware. Numbers with a source in square brackets come from datasheets, sellers or people who tested the hardware; see Sources at the end.

## 1. Recommendation (read this first)

**Should we switch to a Raspberry Pi? Yes, if reading slides from about 15 m is a firm requirement.** Use a **Raspberry Pi Zero 2 W** with the official **Raspberry Pi Camera Module 3 (standard lens)**, in a **split design**:

- **At the ear:** the camera, the two SPH0645 microphones from `docs/microphone-options.md`, and the small speaker.
- **Clipped on or behind the neck:** the Pi Zero 2 W, an Adafruit PowerBoost 1000C charger and 5 V booster, and a **2500 mAh lithium-polymer (LiPo) battery** (Adafruit #328, 50 × 60 × 7.3 mm, 50 g, CA$19.95 at PiShop.ca [21][22]).
- **Expected battery life: about 7 hours with the power-saving plan in section 7, and about 5 hours without it (est.).** That beats the 4-hour target with margin.

**Why the Pi wins here:** far-away slides need many pixels. The Pi can take **12-megapixel stills** with the IMX708 camera while it records the 720p buffer, and its built-in H.264 video encoder keeps the 30-second buffer small enough to live in memory. The XIAO's best camera takes 5-megapixel stills, which read slides to only about 6 to 8 m in real use (est.; section 3).

**What it costs us:** the Pi uses about **twice the power** of the XIAO (about 1 to 1.5 W versus 0.75 W, est.). It needs a **2500 mAh battery instead of 1200 mAh**. It is too big for the ear (65 × 30 mm board, about 12 g), and it takes 20 to 30 seconds to start up (est.). The software is **easier** for a first-year team, though. You write Python on Linux, and the 30-second rolling buffer is a ready-made feature of the Picamera2 library [17].

**Do not use the camera we bought (Arducam B0310) as it is.** Its 120° lens spreads the pixels so wide that 720p video can only read slides from about 1.5 m away. Either use Camera Module 3 (66° view, autofocus, brighter F1.8 lens), or swap the B0310's lens for a longer M12 lens (section 4).

**Camera alternative if we stay on the XIAO ESP32S3 Sense:** the **Seeed OV5640 autofocus camera for XIAO ESP32S3 Sense (Seeed part 114993115)**. It is 8.5 × 8.5 × 5.4 mm on a 70.5 mm flex cable and plugs into the Sense's camera connector. Autofocus works through the esp32-camera driver. It sells on Amazon.ca [9][10][11][12]. Section 5 has the details.

**If the team drops the 15 m requirement to about 8 m or less**, stay with the XIAO ESP32S3 Sense, the Seeed OV5640 autofocus camera and a 1200 mAh battery. Expect about 5 hours (est.). The whole earpiece then stays at the ear, with only the battery on a short cable.

**Not recommended: ESP32-P4 boards.** The IMX708 works on them only through a hobby driver that cannot take full 12-megapixel stills. Their power use has never been measured, and on one board a camera burned out because of a cable mix-up (section 6).

## 2. The camera we bought: Arducam IMX708 (B0310)

The Amazon.ca listing (ASIN B0BZR6XL3Y) is **Arducam SKU B0310**: "12MP IMX708 HDR 120°(H) Wide Angle Camera Module with M12 Lens" [1][2].

| Item | Value | Source |
|---|---|---|
| Board size | 25 × 24 mm (25.00 × 23.86 mm) | [2][4] |
| Height including lens | 15.36 mm | [3] |
| Lens | M12 screw mount, manual focus, 2.87 mm focal length, F2.8, removable | [2][3] |
| Field of view | 152° diagonal, 120° horizontal, 66° vertical | [2][3] |
| Sensor | Sony IMX708, 4608 × 2592 pixels (11.9 MP), 1/2.43", HDR mode up to 3 MP | [2] |
| Connector on the camera | 15-pin, 1.0 mm pitch flat flex cable (FPC) socket | [1] |
| Cable included | 150 mm, 15-pin to 22-pin (the 22-pin end fits the Pi Zero). Arducam's own page also lists a 150 mm 22-to-22-pin cable. Sellers list the cables differently, so check the box. | [2][3] |
| Interface | MIPI CSI-2, 2 lanes, raw 10-bit output | [2][3] |
| Weight | Not published; about 5 to 8 g with the M12 lens (est.; the boxed parcel is 18 g) | [1] |
| Price | CA$74.21 on Amazon.ca (import charges included) | [1] |

**Does it work with the XIAO ESP32S3 Sense? No, confirmed.** The IMX708 sends raw sensor data over a high-speed MIPI CSI-2 link. The ESP32-S3 only has a parallel (DVP) camera port and no image processor (ISP) to turn raw data into a picture. Espressif's own table lists MIPI-CSI as "N/A" for the ESP32-S3 [5][6].

## 3. Can it read slides from the back of the hall? (checking the team's math)

**The rule:** a slide is 40 lines of 24 pt text wide (a 13.33-inch widescreen slide divided by 1/3 inch per 24 pt line). With **800 pixels across the screen**, each letter gets about 20 pixels, which is enough to read. **The team's assumption is reasonable.**

**The formula:** the camera sees a strip of width `W = 2 × d × tan(HFOV / 2)` at distance `d`. HFOV is the horizontal field of view. The screen gets `pixels across = N × S / W`, where N is the image width in pixels and S is the screen width. Setting that to 800 gives the farthest readable distance:

`d_max = N × S / (800 × 2 × tan(HFOV / 2))`

**Results for a 3 m and a 4 m wide screen (est.):**

| Camera and mode | Pixels across (N) | Horizontal view | Ideal reading distance (3 m / 4 m screen) | Real-world (× 0.7, est.) |
|---|---|---|---|---|
| Team's assumption, 720p video | 1280 | 66° | 3.7 / 4.9 m | 2.6 / 3.4 m |
| Team's assumption, 5 MP still | 2592 | 66° | 7.5 / 10.0 m | 5.2 / 7.0 m |
| Team's assumption, 12 MP still | 4608 | 66° | 13.3 / 17.7 m | 9.3 / 12.4 m |
| **Seeed OV5640 AF (XIAO)**, 720p video | 1280 | about 58° (est.) | 4.3 / 5.7 m | 3.0 / 4.0 m |
| **Seeed OV5640 AF (XIAO)**, 5 MP still | 2592 | about 58° (est.) | 8.7 / 11.6 m | 6.1 / 8.1 m |
| **Arducam B0310 as bought**, 720p video | 1280 | 120° | 1.4 / 1.8 m | 1.0 / 1.3 m |
| **Arducam B0310 as bought**, 12 MP still | 4608 | 120° | 5.0 / 6.7 m | 3.5 / 4.7 m |
| **Camera Module 3 standard**, 720p video | 1280 | 66° | 3.7 / 4.9 m | 2.6 / 3.4 m |
| **Camera Module 3 standard**, 720p with 2× digital zoom on the screen area | 1280 | about 36° (est.) | 7.4 / 9.9 m | 5.2 / 6.9 m |
| **Camera Module 3 standard**, 12 MP still | 4608 | 66° | 13.3 / 17.7 m | 9.3 / 12.4 m |
| B0310 with a 6 mm M12 lens, 12 MP still | 4608 | about 57° (est.) | 16.1 / 21.4 m | 11.3 / 15.0 m |
| B0310 with an 8 mm M12 lens, 12 MP still | 4608 | about 44° (est.) | 21.4 / 28.6 m | 15.0 / 20.0 m |

**What this means for the team's numbers:**

- **720p video, about 4 to 5 m: correct** (3.7 to 4.9 m at 66°).
- **OV5640 5 MP stills, 10 to 13 m: too optimistic.** At 66° it is 7.5 to 10 m. The real Seeed module has a slightly narrower view (about 58°, calculated from its 3.29 mm focal length [12]), which gives 8.7 to 11.6 m.
- **IMX708 12 MP stills, 15 to 20 m: a bit optimistic.** At 66° it is 13 to 18 m. **With the 120° lens we bought, it is only 5 to 7 m.**
- **"Real-world" column:** cameras rarely deliver full sharpness. The colour filter, a tiny lens, JPEG compression, head movement and viewing the screen at an angle all blur fine detail. We assume about 70% of the ideal (est.). Test this in the real hall.

**Key lesson: the lens matters as much as the megapixels.** Halving the view angle roughly doubles the reading distance. A narrower lens shows less of the room, though. At 15 m, a 44° lens still covers about 12 m of wall, which is plenty for a screen. Up close, it only covers about 2.4 m of whiteboard from 3 m away.

**Whiteboards (est.):** handwriting about 5 cm tall needs about 15 pixels per letter. Camera Module 3 stills reach about 12 m and its 720p video about 3 m.

## 4. Best camera overall for far-away slides

| Camera | Sensor, pixels across | Horizontal view | Autofocus | HDR | Low light | Works on Pi Zero 2 W | Size | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Raspberry Pi Camera Module 3, standard** [13] | IMX708, 4608 | 66° | Yes (phase-detect, fast) | Yes, up to 3 MP | Good: F1.8, 1.4 µm pixels | Yes, official software | 25 × 24 × 11.5 mm, 200 mm cable | **Recommended.** Best balance of reach, autofocus, low light and easy software. CA$36.45 at PiShop.ca [13]. |
| Arducam B0310 (what we bought) [2] | IMX708, 4608 | 120° | No (manual M12) | Yes | Weaker: F2.8 lets in about 2.4× less light than F1.8 | Yes | 25 × 24 × 15.4 mm | Too wide as is. Keep it as the **long-range option** with a 6 to 8 mm M12 lens (section 3), focused once on the far distance. |
| Arducam 16 MP IMX519 (B0371) [14] | IMX519, 4656 | 66° | Yes | No | Similar: F1.75, smaller 1.22 µm pixels | Yes, but autofocus needs Arducam's own camera library | 25 × 24 mm | **No real gain.** Its extra pixels go to height (4:3 shape), not width, so reach is the same as the IMX708 (4656 vs 4608 pixels across). |
| Arducam 64 MP Hawkeye (B0399) [15] | 64 MP, 9152 (16 MP / 4624 on Pi Zero 2 W) | 72° | Yes | No | Worse: tiny 0.8 µm pixels | Only at 16 MP | 25 × 24 mm | **No.** On the Pi Zero 2 W it is limited to 16 MP, so it reads no farther than the IMX708. Full 64 MP needs a Pi 4 or 5, which is too big and uses 3 to 6 W (est.). |
| Seeed OV5640 AF (for the XIAO) [11][12] | OV5640, 2592 | about 58° (est.) | Yes (contrast-detect, slower) | No | Weaker: smaller 1/4" sensor | Not needed (XIAO part) | 8.5 × 8.5 × 5.4 mm | Best choice **for the XIAO**, but reaches only about half as far as the IMX708. |

**Best overall: Raspberry Pi Camera Module 3 (standard).** To reliably read 24 pt text at 15 m from a 3 m screen, test the B0310 with a longer M12 lens next to it. Even the best small camera only just reaches 15 m. Bigger fonts or bigger screens help a lot: reading distance grows in step with screen width.

## 5. If we stay on the XIAO: the closest camera to the IMX708

**Seeed "OV5640 Camera for XIAO ESP32S3 Sense (With Heat Sink)", Seeed part 114993115 (Digi-Key 1597-114993115-ND)** [10][11].

| Item | Value | Source |
|---|---|---|
| Fits the Sense camera connector? | Yes. It is made for the Sense and plugs into its 24-pin, 0.5 mm camera socket in place of the stock camera | [10][12] |
| Camera body | **8.5 × 8.5 × 5.4 mm** (lens and autofocus motor) | [12] |
| Flex cable | **70.5 mm** overall length including the body, 6 mm wide, 24 contacts at 0.5 mm pitch | [12] |
| Lens | 3.29 mm focal length, F2.8, 69° diagonal view (about 58° horizontal, est.) | [12] |
| Sensor | OV5640, 2592 × 1944 (5 MP), 1/4", 1.4 µm pixels; 720p at up to 60 fps | [10][11] |
| Extras | Two heat sinks, 7 × 6 × 7 mm and 14 × 14 × 7 mm | [10] |
| Where to buy in Canada | Amazon.ca, ASIN B0FGJLZ3K6. We saw prices from about CA$15 to CA$46 depending on the seller, so check before buying. Also Digi-Key (ships to Canada). | [11][10] |

**Autofocus with the esp32-camera driver: confirmed, with conditions.**
- Espressif's **esp32-camera** driver (v2.1.9, November 2026) now includes an **OV5640 autofocus helper** (`esp_camera_af.h`). Turn it on in menuconfig, then call `esp_camera_af_init()`. It loads the OV5640's autofocus firmware over the camera's control bus [7].
- In **Arduino**, Seeed's wiki uses the "OV5640 Auto Focus for ESP32 Camera" library on top of the same driver (`ov5640.focusInit()`, then `ov5640.autoFocusMode()`) [8][9].
- **Only this separately sold module has autofocus.** The OV5640 that ships on the Sense board is fixed-focus [9].
- For lectures, you can also lock focus once on the far distance. That saves a little power and avoids "hunting".

**How close is it to the IMX708?**

| Feature | IMX708 (B0310 / Camera Module 3) | Seeed OV5640 AF | Closer or worse? |
|---|---|---|---|
| Resolution | 12 MP (4608 across) | 5 MP (2592 across) | Worse: about half the reach for stills |
| Autofocus | Camera Module 3: fast phase-detect. B0310: manual | Contrast-detect autofocus | Similar to Camera Module 3; better than the B0310 |
| Low light | Sensor area about 23 mm² | About 10 mm², F2.8 | Worse: about 2.3× less light-collecting area |
| HDR (bright screen and dim room together) | Yes, up to 3 MP | No | Worse |
| Field of view | 120° (B0310) or 66° (Camera Module 3) | About 58° horizontal | Narrower, which is better for reading distant slides |
| Heat | Normal | Over 70 °C when streaming; about 54 °C with Seeed's low-drive register fix and heat sink | Needs the fix [9] |

## 6. Board comparison

| | **Raspberry Pi Zero 2 W + IMX708** | **ESP32-P4 board + IMX708** | **XIAO ESP32S3 Sense + OV5640 (low-power baseline)** |
|---|---|---|---|
| Board size | 65 × 30 × about 5 mm [16] | FireBeetle 2 ESP32-P4: 25.4 × 60 mm [26]; Waveshare ESP32-P4-NANO: 50 × 50 mm [25]; Wireless-Tag P4-TINY: 33 × 69 mm [27] | 21 × 17.8 × 15 mm with camera board [18] |
| Weight | About 12 g [16] | Not published (est. 10 to 20 g) | 6.6 g [18] |
| IMX708 support | **Official** (libcamera, Picamera2) | **Not official.** Espressif's list does not include the IMX708 [5]. A community driver (`mushbraindave/esp_cam_sensor_imx`) works [24] | **No** (needs MIPI) |
| Video | Hardware H.264 up to 1080p30 [16]. 720p uses the whole sensor (full view) | Hardware H.264 up to 1080p30 [6]. The driver's 720p is a **centre crop** (56% of the view) at 28 to 56 fps [24] | MJPEG (one JPEG per frame) made inside the camera; 720p at 15 fps tested by others [19] |
| Full-resolution stills | **12 MP** | **No.** The driver tops out at 2304 × 1296; the ISP's limit is 1920 × 1080 [5][24] | 5 MP |
| 30 s buffer, 720p 15 fps | H.264 at about 2 Mbit/s = **about 7.5 MB in RAM** (est.), via Picamera2 `CircularOutput2` [17]. Plus 1.9 MB of audio. No SD wear. | H.264 = about 7.5 MB (est.) in the 32 MB PSRAM, plus 1.9 MB audio. Must be hand-written in C. | MJPEG at about 0.9 MB/s = **about 28 MB on microSD** in 2 s chunks, plus 1.9 MB audio in PSRAM (see software-design.md) |
| Power while recording (published or measured) | 1.15 W with rpicam-vid on a Zero 2 W [20a]. About 1.5 W (300 mA at 5 V) for a Zero W with Camera Module 3 [20b]. About 2 W while streaming over Wi-Fi [20c] | None published. Chip alone: 65 to 123 mA at 3.3 V at 360 MHz [23]; MIPI up to 50 mA more [23]. **Estimate 0.8 to 1.2 W** for the board | 155 mA at 3.8 V (0.6 W) in the Wi-Fi webcam demo [18]. Under 300 mA (about 1.1 W) streaming video [19] |
| Battery current at 3.7 V (est.) | About 300 to 460 mA (sections 7 and 8) | About 240 to 360 mA | About 205 to 285 mA |
| Battery for 4 h + 25% margin (est.) | **2500 mAh**, 50 × 60 × 7.3 mm, 50 g [22] | 1500 to 2000 mAh, about 60 × 36 × 7 mm, 34 g [28] | **1200 mAh**, 34 × 62 × 5 mm, 23 g [21] |
| Software effort | **Easiest:** Python, ready-made rolling buffer, Linux Bluetooth and Wi-Fi tools | **Hardest:** ESP-IDF C, hobby camera driver, separate ESP32-C6 chip for Wi-Fi | Medium: Arduino or ESP-IDF C; we write the buffer and SD handling ourselves |
| Main risks | Size and battery (needs a split design); 20 to 30 s start-up; SD card damage if power is cut | No 12 MP stills; unmeasured power. On the P4-TINY, the camera connector's pin order is reversed, and a standard Pi cable burned out a camera [24] | Reach limited to about 6 to 8 m; heat; SD speed near its limit |

## 7. Power-saving plan (ranked by savings)

Savings are for the recommended Pi Zero 2 W setup, measured on the 5 V side. All are **estimates** unless a source is given.

| Rank | Technique | Saves (est.) | How |
|---|---|---|---|
| 1 | **Pause recording when there is nothing to record** (breaks, a quiet "pause" button) | Up to 100% during the pause | Stop the camera stream; keep Bluetooth on so the phone can wake it |
| 2 | **Turn Wi-Fi off except for uploads** | 30 to 40 mA | `rfkill block wifi`; switch on only to send clips and stills, ideally in batches. Wi-Fi activity adds about 60 mA [20d] |
| 3 | **Trim the Pi** (HDMI off, LEDs off, unused services off) | About 45 mA | CNX Software got a Zero 2 W from about 120 mA down to under 75 mA at idle [20d] |
| 4 | **Keep the 30 s buffer in RAM, not on the SD card** | 10 to 20 mA, and no card wear | Picamera2 `CircularOutput2(buffer_duration_ms=30000)` [17]; write to SD only when a clip is saved |
| 5 | **Efficient power board** | About 10% of the total | A synchronous boost converter rated over 90% efficient (PowerBoost 1000C [21b]) instead of a cheap 80% one. Use its low-battery pin to shut the Pi down cleanly |
| 6 | **Limit CPU speed and work** | 10 to 15 mA | Let the hardware encoder do the work; cap the CPU (for example `arm_freq=600` in config.txt); avoid per-frame Python processing. A user measured 1.15 W for the plain recorder versus 1.5 to 3 W for Python code that processes frames [20a] |
| 7 | **Stills only on slide change, not on a fast timer** | 3 to 10 mA | See section 9 |
| 8 | **Bluetooth Low Energy (BLE) settings** | A few mA | Connection interval of 30 to 50 ms. Send compressed mono audio (about 8 KB/s), not raw stereo (64 KB/s) |
| 9 | **Shut down the speaker amplifier when silent** | About 2 mA | Drive the amplifier's shutdown (SD) pin low between voice lines. A MAX98357A-type amplifier idles at a few mA and draws under 1 µA when shut down (est.; check the datasheet) |
| 10 | **Lower frame rate or resolution in the buffer** | Small on the Pi; large on the XIAO | On the Pi, frame rate barely changes power [20a]. On the XIAO, a 5 fps buffer cuts camera, SD and CPU power by about 30% (est.). The catch: a saved clip is only as good as what was buffered, so a 5 fps buffer gives 5 fps clips. Full 15 fps only starts once the save is pressed |

## 8. Power budgets and battery life (all estimates)

**Recommended: Pi Zero 2 W + Camera Module 3, 720p at 15 fps buffer, 12 MP stills on slide change** (mA at 5 V).

| Component | Before savings | After savings |
|---|---|---|
| Pi Zero 2 W base (CPU, RAM, HDMI, LEDs) | 120 [20d] | 75 [20d] |
| Wi-Fi (connected all lecture vs uploads only) | 40 | 10 |
| Camera Module 3 sensor, streaming | 50 | 50 |
| Image processor (ISP) + H.264 encoder + CPU work | 60 | 45 |
| SD writes (continuous vs only on save) | 15 | 0 |
| 12 MP stills (about 60 per hour) | 5 | 5 |
| BLE link to phone | 10 | 10 |
| 2 × SPH0645 microphones (0.6 mA each [29]) | 1.2 | 1.2 |
| Speaker amplifier (idle vs shut down; voice lines are rare) | 2.4 | 1 |
| **Total at 5 V** | **about 304 mA (1.5 W)** | **about 197 mA (1.0 W)** |
| **Battery current at 3.7 V** (90% boost efficiency, plus 5 mA for the power board [21b]) | **about 460 mA** | **about 300 mA** |
| **Life on 2500 mAh** (90% usable = 2250 mAh) | **about 4.9 h** | **about 7.5 h** |

The measured 1.15 to 1.5 W [20a][20b] sits between these two columns, so the estimates look reasonable. If our own test shows over 1.7 W, use a bigger battery (two 18650 cells) or cut Wi-Fi time further.

**Fallback: XIAO ESP32S3 Sense + Seeed OV5640 AF, 720p at 15 fps MJPEG to microSD, 5 MP stills** (mA at 3.8 V battery).

| Component | Before savings | After savings | 5 fps buffer option |
|---|---|---|---|
| ESP32-S3 CPU (240 MHz vs 160 MHz) | 60 | 45 | 35 |
| PSRAM and camera data transfer | 15 | 15 | 10 |
| OV5640 sensor (default vs low-drive fix) | 110 | 90 | 60 |
| microSD writes | 35 | 30 | 12 |
| Wi-Fi (always on vs uploads only) | 40 | 8 | 8 |
| BLE audio stream | 15 | 10 | 10 |
| 2 × SPH0645 microphones [29] | 1.2 | 1.2 | 1.2 |
| Speaker amplifier | 2.4 | 0.5 | 0.5 |
| 5 MP stills (about 60 per hour) | 3 | 3 | 3 |
| LEDs, regulator, misc. | 5 | 3 | 3 |
| **Total** | **about 285 mA (1.1 W)** | **about 205 mA (0.78 W)** | **about 145 mA (0.55 W)** |
| **Life on 1200 mAh** (1080 mAh usable) | **about 3.8 h** | **about 5.3 h** | **about 7.4 h** |

The "before" total matches the "under 300 mA" measured by the FPV project [19]. Note: Seeed's spec table lists a slow built-in charge current (about 50 to 100 mA [18]), so a 1200 mAh battery would take over 12 hours to charge. Add a 500 mA LiPo charger in the battery pack.

## 9. Full-resolution slide stills alongside the 30 s buffer

**Worth doing, on either board.** Stills are what make far-away slides readable (section 3), and they cost little power.

**How it works:**
- **Pi:** keep recording the 720p buffer. On a trigger, briefly switch the camera to full resolution and save a 12 MP JPEG (Picamera2 `switch_mode_and_capture_file`). This leaves a short gap of about 0.5 to 1 s in the video (est.).
- **Triggers:** (a) **slide change**, by comparing a tiny 160 × 90 grey preview frame once a second and saving when it changes a lot; (b) a **safety timer** every 60 s if nothing changed; (c) the **button** or the phone.
- **XIAO:** the same idea, switching the OV5640 to 2560 × 1920 JPEG for one frame. Spotting slide changes is harder because frames arrive already compressed. A cheap trick is to watch for a sudden jump in JPEG file size (est.).

| | Pi + Camera Module 3 (12 MP) | XIAO + OV5640 (5 MP) |
|---|---|---|
| Size per still (est.) | 2 to 4 MB JPEG | 0.4 to 0.8 MB JPEG |
| Storage, 60 stills per hour for 4 h (est.) | About 0.5 to 1 GB | About 0.1 to 0.2 GB |
| Storage, every 30 s for 4 h (est.) | About 1 to 2 GB | About 0.2 to 0.4 GB |
| Extra power, 60 per hour (est.) | About 5 mA at 5 V for capture, plus about 5 mA for Wi-Fi upload | About 3 mA, plus about 2 mA for upload |
| Upload time per still (1 to 2 MB/s Wi-Fi, est.) | 1 to 4 s | Under 1 s |
| Effect on the 30 s video | Short gap (about 0.5 to 1 s, est.) | Short gap (about 0.3 to 1 s, est.); extra SD load is absorbed by the 3 MB write buffer |

Any 32 GB card holds a whole term's stills if the phone deletes them after upload. The phone can also run text recognition (OCR) on the stills, which helps the AI summaries more than the video does.

## 10. Will it fit on the ear?

**Pi design: split.**
- **Ear unit (est.):** about 30 × 28 × 16 mm and 15 to 20 g. It holds Camera Module 3 (25 × 24 × 11.5 mm), two microphone boards (16.7 × 12.7 × 1.8 mm each [29]) and a small speaker.
- **Cable:** a thin flat camera ribbon (22-pin on the Pi Zero end, 15-pin on the camera end), about 30 cm long, plus four or five thin wires for the microphones and speaker. Check available ribbon lengths at PiShop.ca. Long camera ribbons can pick up interference, so test video quality with the real cable.
- **Clip-on or neck pack (est.):** about 70 × 55 × 22 mm and about 75 g. It holds the Pi Zero 2 W (65 × 30 mm), the PowerBoost 1000C (23 × 45 × 10 mm, 6 g [21b]) and the 2500 mAh battery (50 × 60 × 7.3 mm, 50 g [22]). It runs warm (about 1 W), so add vents and keep it off bare skin.

**XIAO design: nearly all at the ear.**
- **Ear unit (est.):** the XIAO with its camera board (21 × 17.8 × 15 mm, 6.6 g), the OV5640 on its 70 mm flex, the microphones and the speaker. About 35 × 25 × 18 mm and 15 g. The flex is too short to move the board away from the camera, and the camera's parallel wiring does not work over long cables.
- **Battery:** the 1200 mAh battery (34 × 62 × 5 mm, 23 g [21]) is too big for the ear. Put it in a small clip-on pack on a 2-wire cable.

## 11. Next steps

1. **Decide whether 15 m is firm.** That one answer chooses the Pi or the XIAO.
2. Buy a **Camera Module 3** (CA$36.45, PiShop.ca) and a **Pi Zero 2 W**. Bring them and the B0310 to the real lecture hall. Take 12 MP stills of a 24 pt slide from 5, 10 and 15 m to check the table in section 3.
3. Run a **1-hour recording test** with a USB power meter. Log watts, temperature and dropped frames.
4. Choose the battery from the measured watts: battery mAh ≈ 1000 × watts × 4 h × 1.25 ÷ (0.9 boost efficiency × 3.7 V × 0.9 usable capacity). Example: 1.0 W gives about 1670 mAh.

## Sources

[1] Amazon.ca listing, Arducam IMX708 120° M12 (ASIN B0BZR6XL3Y), including reviewer notes on cables. https://www.amazon.ca/Arducam-IMX708-Camera-Module-Raspberry/dp/B0BZR6XL3Y
[2] Arducam B0310 datasheet (Digi-Key copy) and Arducam product page. https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8904/B0310.pdf ; https://www.arducam.com/presalearducam-12mp-imx708-hdr-120-wide-angle-camera-module-with-m12-lens-for-raspberry-pi.html
[3] RobotShop, B0310 listing (25 × 24 × 15.36 mm, 150 mm 15-to-22-pin cable). https://www.robotshop.com/products/arducam-12mp-imx708-hdr-120-wide-angle-camera-module-w-m12-lens-rpi
[4] Digi-Key, Arducam B0310 (25.00 × 23.86 mm). https://www.digikey.co.uk/en/products/detail/arducam/B0310/19116507
[5] Espressif, esp_cam_sensor README (supported sensors; ESP32-S3 has no MIPI-CSI; P4 ISP limit 1920 × 1080). https://github.com/espressif/esp-video-components/tree/master/esp_cam_sensor
[6] Espressif, ESP-Video and ESP-H264 docs (P4 hardware H.264 up to 1080p30; S3 has no ISP or H.264 hardware). https://docs.espressif.com/projects/esp-video-components/en/latest/esp32p4/ESP_Video/index.html ; https://docs.espressif.com/projects/esp-techpedia/en/latest/esp-friends/solution-introduction/multimedia/component-description/esp-h264.html
[7] Espressif, esp32-camera README, "Autofocus (OV5640)", release v2.1.9. https://github.com/espressif/esp32-camera
[8] 0015 (Eric Nam), ESP32-OV5640-AF library. https://github.com/0015/ESP32-OV5640-AF
[9] Seeed Studio wiki, Camera Usage for XIAO ESP32S3 Sense (OV5640 autofocus, fixed-focus stock camera, heat fix 70 °C to 54 °C). https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/
[10] Seeed Studio product page and Digi-Key listing, OV5640 Camera for XIAO ESP32S3 Sense, part 114993115. https://www.seeedstudio.com/OV5640-Camera-for-XIAO-ESP32S3-Sense-With-Heat-Sink-p-5739.html ; https://www.digikey.co.uk/en/products/detail/seeed-technology-co-ltd/114993115/21277047
[11] Amazon.ca, OV5640 Camera for XIAO ESP32S3 Sense (ASIN B0FGJLZ3K6). https://www.amazon.ca/OV5640-Camera-XIAO-ESP32S3-Sense/dp/B0FGJLZ3K6
[12] Seeed, OV5640 module approval sheet MJY5OAF-F3M-V1 (drawing page 3: 8.5 × 8.5 × 5.4 mm, 70.5 mm overall, EFL 3.29 mm, F2.8, 69° view). https://files.seeedstudio.com/wiki/OV5640_for_ESP32S3_sense/OV5640_Datasheet.pdf
[13] Raspberry Pi, Camera Module 3 product brief; PiShop.ca listing (CA$36.45, 66° horizontal view, 25 × 24 × 11.5 mm, F1.8). https://pip-assets.raspberrypi.com/categories/786-raspberry-pi-camera-module-3/documents/RP-008151-DS-1-camera-module-3-product-brief.pdf ; https://www.pishop.ca/product/raspberry-pi-camera-module-3/
[14] Arducam, 16 MP IMX519 wiki and product brief (4656 × 3496, 66° horizontal, custom libcamera for autofocus). https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/16MP-IMX519/
[15] Arducam, 64 MP Hawkeye wiki and product page (72° horizontal, 0.8 µm pixels, 16 MP limit on Pi Zero 2 W). https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/64MP-Hawkeye/ ; https://www.arducam.com/blog/product/64mp-af-for-raspberry-pi/
[16] Raspberry Pi, Zero 2 W product brief (65 × 30 mm, H.264 encode 1080p30, 512 MB); TME listing (12.01 g gross). https://pip-assets.raspberrypi.com/categories/584-raspberry-pi-zero-2-w/documents/RP-008359-DS-1-raspberry-pi-zero-2-w-product-brief.pdf ; https://www.tme.eu/ng/en/details/sc1176/raspberry-pi-minicomputers/raspberry-pi/raspberry-pi-zero-2-w-512mb-ram/
[17] Raspberry Pi, Picamera2 `CircularOutput2` source and circular capture example. https://github.com/raspberrypi/picamera2/blob/main/examples/pyav_circular_capture.py
[18] Seeed Studio wiki, Getting Started with XIAO ESP32-S3 (size, power figures, charge current); Bastelgarage (6.6 g). https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/ ; https://www.bastelgarage.ch/seeed-studio-xiao-esp32-s3-sense-with-camera
[19] natiy4, hx-esp32-cam-fpv README (OV5640 720p on ESP32-S3, under 300 mA). https://github.com/natiy4/hx-esp32-cam-fpv
[20a] Picamera2 issue #489, Pi Zero 2 W power (rpicam-vid 1.15 W, Python 1.5 to 3 W, frame rate made little difference). https://github.com/raspberrypi/picamera2/issues/489
[20b] Raspberry Pi forum, Camera Module 2 and 3 power (Pi Zero W system never over 300 mA at 5 V). https://forums.raspberrypi.com/viewtopic.php?t=347469
[20c] Curious Scientist, bird camera (Zero 2 W + Camera Module 3, about 400 mA at 5 V streaming). https://curiousscientist.tech/blog/bird-camera-raspberry-pi-zero-2-w
[20d] CNX Software, Raspberry Pi Zero 2 W power deep dive (about 120 mA idle, under 75 mA tuned); ODG Electronics (Wi-Fi about +60 mA). https://www.cnx-software.com/2021/12/09/raspberry-pi-zero-2-w-power-consumption/ ; https://www.origin-ic.com/blog/raspberry-pi-zero-2-w/47761
[21] PiShop.ca, Adafruit 1200 mAh LiPo (34 × 62 × 5 mm, 23 g, CA$14.95); Newark Canada. https://www.pishop.ca/product/lithium-ion-polymer-battery-3-7v-1200mah/ ; https://canada.newark.com/adafruit/258/batt-rechar-3-7v-lithium-polymer/dp/96Y0775
[21b] PiShop.ca, Adafruit PowerBoost 1000C (over 90% efficient, 5 mA quiescent, 23 × 45 × 10 mm, 6 g). https://www.pishop.ca/product/powerboost-1000-charger-rechargeable-5v-lipo-usb-boost-1a-1000c/
[22] Adafruit #328, 2500 mAh LiPo (50 × 60 × 7.3 mm, 50 g); PiShop.ca CA$19.95 (lists the older 51 × 65 × 8 mm, 52 g version). https://www.adafruit.com/product/328 ; https://www.pishop.ca/product/lithium-ion-polymer-battery-3-7v-2500mah/
[23] Espressif, ESP32-P4 datasheet, Table 5-7 (current in active mode); ESP32-P4 hardware design guidelines (MIPI PHY up to 50 mA). https://documentation.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32p4/schematic-checklist-esp32p4.html
[24] mushBrainDave, esp_cam_sensor_imx (IMX708 driver for ESP32-P4: modes, crop, measured fps, P4-TINY cable warning). https://github.com/mushBrainDave/imx708
[25] Waveshare, ESP32-P4-NANO docs; CNX Software (50 × 50 mm). https://docs.waveshare.com/ESP32-P4-NANO
[26] DFRobot, FireBeetle 2 ESP32-P4 (25.4 × 60 mm). https://www.dfrobot.com/product-2950.html
[27] Wireless-Tag, WT9932P4C61-TINY (33 × 69 mm). https://wiki.wireless-tag.com/docs/en/WT9932P4C61-TINY/board_features.html
[28] Adafruit #2011, 2000 mAh LiPo (60 × 36 × 7 mm, 34 g). https://www.adafruit.com/product/2011
[29] Best Team, microphone options (2 × SPH0645 on Adafruit #3421, 600 µA each, 16.7 × 12.7 × 1.8 mm; 30 s stereo audio about 1.9 MB). /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/docs/microphone-options.md
