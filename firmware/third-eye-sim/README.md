# Third Eye earpiece firmware: emulator build and tests

ESP-IDF firmware for the Seeed XIAO ESP32S3 Sense (ESP32-S3, 2 cores at 240 MHz,
512 KB SRAM, 8 MB octal PSRAM, 8 MB flash, microSD in 1-bit mode). The same
application code builds for two platforms:

- **sim**: runs in Espressif's QEMU with 8 MB PSRAM and an emulated SD card.
  Camera, mics, buttons, temperature and battery are simulated. BLE and Wi-Fi
  are replaced by TCP links to a mock phone script. A speed model holds the SD
  card, BLE and Wi-Fi to realistic speeds.
- **xiao**: the real board drivers (esp32-camera for the OV5640, I2S for the two
  SPH0645 mics and the speaker amp, SDMMC 1-bit, GPIO buttons, ADC battery, chip
  temperature sensor, NimBLE, Wi-Fi). It compiles and links, but it has
  **not been run on hardware yet**.

The test report is `docs/xiao-emulator-test.md` in the project store.

## Layout

```
main/                 application (hardware-independent)
  ctrl.c              Sleep / Listen / Prompt state machine, buttons, heat, battery, voice lines
  capture.c           camera task, audio task (gain, high-pass, 34 s PSRAM ring, ADPCM stream)
  storage.c           PSRAM write buffer -> 2 s chunk files, 30 s rolling buffer, clip save
  link.c              BLE framing, reconnect every 5 s, phone-lost detection, commands
  xfer.c              Wi-Fi clip transfer, offline queue, delete only after the phone confirms
  metrics.c           heap / buffer / CPU / card / battery report
  te_config.h         all tunable numbers (thresholds, sizes, timeouts)
components/te_hal/    the thin driver layer
  include/te_hal.h    the interface the app uses
  src/sim/            QEMU drivers + speed model + battery/thermal model
  src/xiao/           real XIAO drivers (pins in xiao_pins.h)
tools/
  sim.py              harness: QEMU launcher, mock phone (BLE + Wi-Fi), test bench
  run_tests.py        20 automated feature and error-path tests
  run_lecture.py      1-hour lecture recording with the speed model
  cpu_estimate.py     CPU load from QEMU instruction counting
results/              JSON/CSV results of the last runs (no build output)
```

## Build

Needs ESP-IDF v5.4.1 and Espressif QEMU **esp-develop-9.2.2-20261109 or newer**
(the older 9.0.0 release rejects 8 MB PSRAM and has no SD card on the esp32s3 machine).

```bash
. ~/esp/esp-idf/export.sh
# QEMU: download qemu-xtensa-softmmu-esp_develop_9.2.2_20261109-x86_64-linux-gnu.tar.xz
# from https://github.com/espressif/qemu/releases, unpack, and put qemu/bin on PATH.

# emulator build (build output kept outside the source folder)
idf.py -B /tmp/te-sim -DSDKCONFIG=/tmp/te-sim/sdkconfig \
       -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.sim" build

# real-board build
idf.py -B /tmp/te-xiao -DSDKCONFIG=/tmp/te-xiao/sdkconfig \
       -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.xiao" build
idf.py -B /tmp/te-xiao -p /dev/ttyACM0 flash monitor     # on the real XIAO
idf.py -B /tmp/te-xiao size                              # static memory use
```

## Run the tests

```bash
python tools/run_tests.py --build /tmp/te-sim -j 2          # all tests, about 25 minutes
python tools/run_tests.py --build /tmp/te-sim --only thermal,battery
python tools/run_lecture.py --build /tmp/te-sim              # 1 hour, real time
python tools/cpu_estimate.py --build /tmp/te-sim             # about 4 minutes
```

Each test boots a fresh emulator with a blank SD image under `/tmp/te-tests/<name>/`
(`serial.log` = firmware console, `phone.log` = everything the mock phone and
bench saw). Results go to `results/test-results.json`.

QEMU is started directly by `tools/sim.py` (not `idf.py qemu`) because it needs
`-m 8M`, `-global driver=ssi_psram,property=is_octal,value=true` (the XIAO's
PSRAM is octal) and an SD card drive.

## Speed-model settings

Set per test in `tools/sim.py` (`GOOD_CARD`, `CHEAP_CARD`, `BLE_SLOW`, `BLE_FAST`) and
written into the `simcfg` flash partition of the emulator image. The bench can also
force a card pause (`SD_STALL <ms>`), set the temperature (`TEMP <C>`) or battery
(`BATT <pct>`), and press buttons (`BTN SB tap`, `BTN PR hold 3000`).

## Before flashing the real board

- Check the proposed pins in `components/te_hal/src/xiao/xiao_pins.h` against the wiring.
- The battery needs a 2 x 100 k divider to D0; the XIAO has no battery sense pin.
- Store the phone hotspot SSID/password in NVS (namespace `wifi`, keys `ssid`, `pass`).
- Voice lines are beeps until recorded audio is added (`hal_spk_voice` in `xiao_core.c`).
