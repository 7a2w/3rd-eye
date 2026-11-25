# Third Eye earpiece: test on an emulated XIAO ESP32S3 Sense

Best Team, CEN100 section 16. November 23, 2026.

Numbers marked **(est.)** are estimates or come from a model we made up. They are not measurements. Everything else was measured in the emulator. Remember the emulator is not the real board (section 9).

Source code, build steps and test scripts: `firmware/third-eye-sim/` (start with its `README.md`). Raw results: `firmware/third-eye-sim/results/`.

## 1. Short answer

**Every earpiece feature works in the emulator: 20 out of 20 automated tests pass, and a 1-hour lecture recording ran with zero dropped frames.** The code fits the XIAO's flash and PSRAM easily.

Three things still need attention on the real board:

1. **Fast internal RAM (SRAM) is tight while Wi-Fi is sending a clip.** PSRAM is fine. This is the biggest risk (section 7).
2. **Sending a clip while still recording is slow**, about 2 to 2.5 minutes per clip on a good card instead of the 15 to 30 s we guessed. The card can't write video and read the clip back fast enough at the same time (section 5).
3. **A cheap microSD card can't keep up with 720p at 15 fps.** The firmware copes by lowering the frame rate. Buy a good card.

While testing we found and fixed four bugs that would also have hit the real board (section 3).

## 2. What we built

| | Real XIAO ESP32S3 Sense | Emulator (Espressif QEMU 9.2.2) |
|---|---|---|
| Processor | ESP32-S3, 2 cores, 240 MHz | Same chip model, 2 cores. Speed is **not** the same (section 8) |
| Fast RAM (SRAM) | 512 KB | Same memory map |
| PSRAM | 8 MB, octal | 8 MB, octal (checked at boot: 8,388,608 bytes) |
| Flash | 8 MB | 8 MB image |
| microSD | 1-bit SD mode | Emulated card in 1-bit mode, real ESP-IDF SD driver, 1 GB image. A **speed model** slows it to real-card speed |
| Camera (OV5640) | Makes 720p JPEG frames | Simulated: 1280 × 720 JPEG-shaped frames, 54 to 66 KB each, 15 fps |
| 2 × SPH0645 mics | I2S stereo, 18-bit samples | Simulated: a 440 Hz test "voice" plus noise, stereo, 16 kHz |
| Buttons, temperature, battery | GPIO, chip sensor, ADC | Set by the test script. Battery and heat follow a model **(est.)** |
| BLE and Wi-Fi to the phone | Radio | TCP links to a mock phone script over QEMU's emulated Ethernet, with a speed model |
| Speaker (voice lines) | I2S amplifier | Reported to the test script |

**One firmware, two hardware layers.** All the earpiece logic is in `main/`. It only talks to the hardware through one small interface, `te_hal.h`. That interface has two versions: `src/sim/` for the emulator and `src/xiao/` for the real board. The `src/xiao/` version uses the real camera, mic, SD, button, battery, temperature, BLE (NimBLE) and Wi-Fi drivers. It compiles and links for the ESP32-S3, but **it has never run on a real board**.

**Tasks and cores** (as in `docs/software-design.md`): camera, audio and SD writer run on core 1. BLE, Wi-Fi transfer and control (buttons, states, heat, battery) run on core 0.

**Time.** The feature tests and the 1-hour lecture ran in **real time**: QEMU's clock followed the computer's clock, and QEMU never fell behind (it used about half of one host CPU core). The CPU-load estimate used **instruction-counted virtual time** instead (section 8).

## 3. Things we changed, and why

| What | Why |
|---|---|
| **Used QEMU 9.2.2 (Nov 2026)**, not the QEMU that ESP-IDF 5.4.1 installs (9.0.0). | 9.0.0 refuses more than 4 MB of PSRAM and has no SD card for the ESP32-S3. 9.2.2 has both. Its PSRAM must be switched to octal mode, so the test script starts QEMU itself instead of `idf.py qemu`. |
| **BLE and Wi-Fi replaced by TCP links** to a mock phone, with a speed model. | QEMU has no radio (as the assignment expected). |
| **Placeholder memory for the radio stacks**: 40 KB of SRAM held all the time for BLE, plus 60 KB while Wi-Fi is on **(est.)**. | The real BLE and Wi-Fi stacks can't run in QEMU, but they use SRAM. Holding fake blocks of that size makes the memory numbers more honest. |
| **Audio buffer is 34 s (2.2 MB), not 30 s (1.9 MB).** | Writing a clip's 30 s of audio to the card takes 1.2 to 3.6 s, and the mics keep recording into the same buffer meanwhile. Without 4 s of spare room, the start of the clip's audio would be overwritten as it is being saved. |
| **Reading a clip for transfer pauses when the PSRAM write buffer is over 25% full.** | First version paused at 50%. The buffer then sat half full during every transfer, and ordinary card pauses pushed it over the limit, so the frame rate dropped. Recording now gets priority. |
| **Added automatic frame-rate lowering (back-pressure).** If the write buffer stays over 60% full for 2 s, fps steps 15 → 10 → 5. It steps back up after 20 s under 15%. | Without it, a slow card just drops frames until the clip is broken. |
| **Bug fixed: crash at start-up.** The BLE task could report "phone connected" before the control task was ready. | It happened once in about 20 boots. The real board could hit it too. |
| **Bug fixed: crash with no or broken SD card.** Now the earpiece still streams audio and answers prompts, says "memory card problem", and refuses to save clips. | The first version crashed as soon as Listen started. |
| **Bug fixed: name clash.** Our `hal_init` had the same name as a function inside Espressif's Wi-Fi library. | Only showed up when building for the real board. Renamed to `te_hal_init`. |
| **Real-board settings for less SRAM**: smaller I2S and Wi-Fi buffers (`sdkconfig.xiao`, `xiao_mic.c`). | Section 7. Compiled but not tested. |
| **Live audio stream is mono** (front + rear mixed), ADPCM, 8 KB/s. Clips keep **raw stereo**. | Matches the 8 KB/s in the software design. The phone's beamforming (`docs/microphone-options.md`) works on the stereo clips, not the live stream. |
| **Live stream pauses during a prompt.** | So the phone doesn't transcribe the question as lecture. Recording to the 30 s buffer continues. |
| **Real-board Wi-Fi joins the phone's hotspot.** | Open decision 5 (own network vs hotspot) is still yours. Only `xiao_wifi.c` changes either way. |

## 4. Feature results

Each test boots a fresh emulator with a blank card and checks the results automatically. **PASS** means every check in that test passed.

| Feature (v2 flowchart / software design) | Test | What was checked | Result |
|---|---|---|---|
| Boot on XIAO specs, Sleep state | `boot` | 2 cores, 8 MB flash, 8 MB octal PSRAM. Starts in Sleep, BLE connects, camera and Wi-Fi off, no audio sent | **PASS** |
| Listen state, compressed audio stream to phone | `listen_stream` | Short press starts Listen. "Listening" voice line. Camera at 15.0 fps. Stream **8.16 KB/s**, no gaps. Phone decodes the 440 Hz test tone (99% of the sound power at 440 Hz) | **PASS** |
| 30 s rolling buffer | `rolling_buffer` | After 75 s (68 MB written), the card holds only the newest 15 two-second files (28 MB) | **PASS** |
| Short press saves a clip; Wi-Fi only during transfer | `button_save` | Clip saved, "clip saved" voice line. Wi-Fi off before, on for the transfer, off after. Phone gets 436 frames (29 s at 15 fps; every feature test got 435 to 442), no missing frames, 30.0 s stereo audio, checksum OK | **PASS** |
| Save from phone key phrase; phone listen/stop commands | `phone_save` | "due friday" command saves a clip and the phrase is stored with it. Save ignored in Sleep. Phone "stop" and "listen" work | **PASS** |
| Clip deleted only after the phone confirms it | `confirm_before_delete` | Phone says "bad copy": clip kept. Phone never answers: clip kept. Third try confirmed: clip deleted | **PASS** |
| Transfer-failed path, retry every 5 s | `transfer_failed` | Phone refuses the connection, then drops it halfway. Wi-Fi off after each failure, retry 6.5 s and 13 s later (at least 5 s), then success | **PASS** |
| Phone-lost path in Listen, offline queue | `phone_lost_listen` | Earpiece notices within seconds, "phone disconnected" voice line, keeps recording. Two button saves while offline. Reconnect tried every **5.0 s**. When the phone is back: "phone connected", both clips sent and deleted | **PASS** |
| Long press stops Listen | `long_press_stop` | Long press: "stopped listening", camera and mic off, waits for the queued clip to send, then Sleep. Stream stops, rolling buffer deleted | **PASS** |
| Prompt from Listen | `prompt_listen` | Prompt button: 3 s of voice (24 KB ADPCM) and a 61 KB JPEG sent over BLE in 1.4 s. Answer played. Back to Listen with no dropped frames, stream resumes | **PASS** |
| Prompt from Sleep | `prompt_sleep` | Camera turns on just for one frame, then back to Sleep. Nothing recorded | **PASS** |
| Prompt error paths | `prompt_errors` | LLM fails: "Sorry, I couldn't answer". No answer in 15 s: same line. Phone lost mid-prompt: "phone disconnected", back to Listen. Prompt while phone away: offline line, stays in Listen | **PASS** |
| Database-edit approval with the Prompt button | `prompt_approval` | Short press = yes, long press = no, no press in 10 s = no. Phone receives all three answers | **PASS** |
| Temperature throttling | `thermal` | 65 °C: 10 fps. 75 °C: 5 fps, "too hot", Wi-Fi transfers held. 85 °C: camera off, audio keeps going. Cool again: 15 fps, "cooled down", held clip sent | **PASS** |
| Low battery | `battery` | 15%: "low battery", 10 fps. 5%: "battery critical", files closed, Sleep, Listen refused. Recharged: works again | **PASS** |
| Card nearly full | `storage_full` | 128 MB card: once less than 80 MB is free, saves are refused with a "storage full" voice line. Recording continues | **PASS** |
| No or broken microSD card | `no_card` | "Memory card problem" voice line. Audio stream and prompts still work, save refused, no crash | **PASS** |
| Speed model (3 tests) | `speed_*` | Section 5 | **PASS** |

**Voice lines** in the firmware: listening, stopped listening, clip saved, phone disconnected, phone connected, "Sorry, I couldn't answer", too hot, cooled down, low battery, battery critical, storage full, approve change, memory card problem. On the real board they are beeps for now. Recorded audio still has to be added (`hal_spk_voice` in `xiao_core.c`).

**Known limit:** a clip is saved by moving the newest 2-second files into the clip folder. Two saves less than 30 s apart therefore don't overlap: the second clip only gets what was recorded after the first one. Saves less than 3 s apart are merged into one.

## 5. Speed model results

The emulator's card and network are much faster than the real ones, so the firmware's simulated drivers hold every read and write back to these speeds:

| Part | Model |
|---|---|
| Good microSD | Writes **1.6 MB/s**, reads 2.0 MB/s **(est.)**. A short pause of 40 to 250 ms about every 2 MB written, and a long pause of 400 to 800 ms about every 200 MB **(est.)**. One bus, so reads and writes take turns |
| Cheap microSD | **3 times slower**: 0.53 MB/s writes, with longer and more frequent pauses |
| BLE | **50 or 100 KB/s**. Only 40% of that while Wi-Fi is on, because both share one antenna **(est.)** |
| Wi-Fi | 1.5 MB/s. 70% of that while BLE is also on **(est.)** |
| Wi-Fi start-up | 1.5 s to turn on and connect **(est.)** |

In each test the earpiece records for 33 s, then saves two clips about 40 s apart. The clips are sent over Wi-Fi **while recording continues**, so the card is writing video and reading the clip back at the same time. In the middle we also forced one extra-long 1.5 s card pause.

| Case | PSRAM write buffer peak (of 3 MB) | Frames dropped | Time to send one ~28 MB clip while recording | Longest gap in the live audio stream |
|---|---|---|---|---|
| Good card, BLE 50 KB/s | 2.60 MB (83%) | **0** | 121 s and 137 s | 0.08 s |
| Good card, BLE 100 KB/s | 2.60 MB (83%) | **0** | 120 s and 134 s | 0.07 s |
| Cheap card, BLE 50 KB/s | 3.12 MB (99%) | **4** (before fps dropped) | 97 to 104 s, but clips are only 11 to 12 MB (5 to 10 fps) | 0.08 s |
| Good card, **not** recording (Listen stopped) | none | none | **28 s** (1.05 MB/s) | none |

**What this means**

- **Good card: the write buffer never overflowed.** The 3 MB buffer covered every normal card pause plus the forced 1.5 s one. The frame rate dipped to 10 fps once, right after the 1.5 s pause, and came back to 15 fps on its own.
- **Cheap card: 720p at 15 fps doesn't fit.** 0.9 MB/s of video is more than the card's 0.53 MB/s. The buffer filled and 4 frames were lost before the firmware cut to 5 to 10 fps. After that, clips were complete but low frame rate. **Use a genuine high-endurance card and test it** (see `docs/software-design.md` section 4).
- **BLE speed hardly matters.** Even 50 KB/s with Wi-Fi taking 60% of the airtime leaves 20 KB/s, and the stream needs 8 KB/s. The audio stream had no gaps in any case.
- **Clip transfers during recording are slow: about 2 to 2.5 minutes per clip.** With video using about 60% of the card's time, plus pauses, little is left for reading a 28 MB clip back. When not recording, a clip takes 28 s. Suggestion: queue clips during the lecture and send them in breaks or after class (open decision 5). This also saves battery and heat.

## 6. One-hour lecture recording

This is the "Test first" test from `docs/software-design.md` section 4, done in the emulator. It ran in **real time** (60 minutes) with the good-card speed model, BLE at 60 KB/s, a fresh 1200 mAh battery model and the heat model on.

**Timeline:** start Listen at 0:00. Button save at 5:00. Phone key-phrase save at 12:00. A 3 s prompt at 20:00. **Phone dropout from 25:00 to 28:00**, with a button save during it at 26:00. Phone saves at 35:00 and 52:00, a button save at 45:00. Long press to stop at 60:00.

| Measure | Result |
|---|---|
| Recording time | 3,586 s (59.8 min) |
| Frames from camera / written to card | 52,178 / 52,177 (the last one was still in the buffer when recording stopped) |
| **Dropped frames** | **0** (write buffer 0, camera driver 0) |
| **PSRAM write buffer high-water mark** | **2.24 MB of 3 MB (71%)** |
| Live audio stream | 68,326 packets, 0 gaps, 0 dropped |
| Clips | 6 saved, 6 received, 6 confirmed, 6 deleted. 425 to 455 frames and 30.0 s of audio each, all checksums OK, 0 failed transfers |
| Phone dropout | "Phone disconnected" voice line, kept recording, 37 reconnect tries at 5 s intervals. "Phone connected" when back, offline clip sent |
| **Total data written to the card** | **3.15 GB** (the software design guessed 3.6 GB/hour **(est.)**) |
| Data read back for transfers | 171 MB |
| **Card space used** | About 28 to 29 MB while recording (the rolling buffer). Up to 59 MB while a saved clip waited to be sent. 64 KB after stopping (everything confirmed and deleted) |
| Card pauses (model) | 1,516 pauses, 222 s in total. Longest single write 751 ms |
| Frame rate | 15 fps for 89% of the time. 10 fps while the heat model passed 65 °C during Wi-Fi transfers. Briefly 5 to 10 fps once after a cluster of card pauses (back to 15 fps within about 40 s) |
| Wi-Fi on | About 22% of the hour (6 transfers of 126 to 152 s) |

**Memory over the hour (leaks and fragmentation).** We compare samples taken in the same state (Listen, Wi-Fi off):

| Time | Free SRAM | Largest free SRAM block | Free PSRAM | Battery (model) | Chip temp (model) |
|---|---|---|---|---|---|
| 0:05 | 182,623 B | 83,968 B | 2,044,076 B | 99% | 52.6 °C |
| 0:20 | 182,327 B | 83,968 B | 2,044,076 B | 93% | 54.8 °C |
| 0:35 | 182,327 B | 83,968 B | 2,044,076 B | 89% | 55.2 °C |
| 0:50 | 182,327 B | 83,968 B | 2,044,076 B | 83% | 57.0 °C |
| 0:60 | 182,327 B | 83,968 B | 2,044,076 B | 80% | 54.7 °C |

- **No memory leak:** free SRAM and PSRAM are the same at the end as at the start of Listen.
- **No fragmentation creeping in:** the largest free block stays at 83,968 bytes all hour. During a Wi-Fi transfer it drops to 31,744 bytes and recovers when Wi-Fi turns off.
- Lowest free SRAM in the hour: 80,299 B, during transfers. Lowest free PSRAM: 1,934,496 B.

**Battery (model, est.).** The model adds up the currents from the "after savings" XIAO column of `docs/hardware-and-power.md`, depending on what is on at each moment. It used **214 mAh in the hour**, an average of **214 mA (est.)**, with a peak of 302 mA during Wi-Fi transfers. The 1200 mAh battery model ended at **80%**. That works out to **about 5 hours (est.)** on 1200 mAh (1080 mAh usable), close to the 5.3 h in the hardware document. Six transfers in one hour is a lot. Sending clips after class instead, when one takes 28 s rather than over 2 minutes, would save about 15 to 20 mAh per hour **(est.)**.

**Heat (model, est.).** The model assumes the chip runs 40 °C hotter than the room for every watt used, and takes about 2 minutes to warm up. Under that guess the chip reached 65 °C during each Wi-Fi transfer, so the firmware stepped down to 10 fps until it cooled. **We made up the heat model.** It only shows that the throttling logic works. The real temperatures must be measured on the board.

Full data (one sample every 15 s): `firmware/third-eye-sim/results/lecture-60min-good.csv`.

## 7. Memory against the XIAO's limits

**Flash (8 MB)**

| Build | Program size | Space (3 MB app partition) | Verdict |
|---|---|---|---|
| Real-board build (with BLE, Wi-Fi, camera drivers) | 1,184,606 B (1.13 MB) | 38% of 3 MB; the rest of the 8 MB is free | **OK, lots of room** |
| Emulator build | 490,870 B | 16% | OK |

Our own code is only about 19 KB of that (15 KB application, 4 KB drivers). The rest is ESP-IDF, Wi-Fi (about 250 KB) and BLE (about 140 KB).

**PSRAM (8 MB)**

| Use | Size |
|---|---|
| Write buffer for card pauses | 3.00 MB |
| Audio: 34 s of 16-bit stereo at 16 kHz | 2.18 MB |
| Prompt audio (10 s max) | 0.32 MB |
| BLE receive buffer | 0.16 MB |
| Latest camera frame for prompts | 0.13 MB |
| Camera frame buffers (emulator: 2 × 100 KB) | 0.29 MB |
| **Lowest free PSRAM seen (any test)** | **1.94 MB** |

**PSRAM verdict: OK.** About 6 MB is used, more than the 4.5 MB **(est.)** in the software design, mostly because the audio buffer is stereo and has 4 s of spare room. On the real board the camera driver's frame buffers are about 70 KB bigger, and the Wi-Fi stack moves some buffers into PSRAM. Expect about **1.6 to 1.8 MB free (est.)**.

**Internal SRAM (512 KB)**

| | Emulator (measured) | Real-board build |
|---|---|---|
| Static use (code in RAM + variables) | 75 KB | **171 KB** (measured from the build) |
| Free heap at the start | 419 KB total heap, 182 KB free after start-up | about 95 KB less than the emulator (est.) |
| Lowest free heap, any test (includes the 100 KB radio placeholders) | **72.7 KB** (during a Wi-Fi transfer) | **somewhere between running out and about 40 KB spare (est.)** |
| Largest free block during a transfer | 31.7 KB | unknown |

**How we got the real-board estimate:** we started from the emulator's lowest free SRAM (72.7 KB). We subtracted the extra 96 KB of static RAM that the real build uses (Wi-Fi, BLE and camera drivers). We added back the emulator-only parts (the emulated Ethernet's buffers, test tasks, and network buffers that move to PSRAM on the real board: about 30 to 95 KB). We subtracted real-board-only parts (camera and I2S DMA buffers, about 30 to 45 KB). The answer depends on numbers we can't measure in the emulator, so it is a wide range.

**SRAM verdict: tight while Wi-Fi is on. It must be measured on the real board.** The firmware already prints free SRAM every few seconds on the real board too. Ways to save more if it runs short:

- Shrink the SD staging buffer from 32 to 16 KB, and the transfer buffer from 16 to 8 KB (`te_config.h`): saves 24 KB.
- Share the 16 KB audio-save buffer with the staging buffer: saves 16 KB.
- Smaller Wi-Fi buffer pools: already set in `sdkconfig.xiao` (untested).
- Send clips only when not recording. Then the camera, SD writing and Wi-Fi never need SRAM at the same time.

**Task stacks:** the smallest margins were the control task (604 bytes free of 4 KB) and the Wi-Fi transfer task (652 bytes free of 4 KB). Give each 1 KB more before flashing the real board, because the real Wi-Fi and BLE code goes deeper than the emulator's.

## 8. CPU load (estimate)

**How we estimated it:** QEMU's "instruction counting" mode makes the emulated chip run exactly 250 million instructions per second per core. That is close to a 240 MHz chip doing about one instruction per clock. FreeRTOS records how long each core spends idle, so busy % = 100% − idle %. Raw results:

| State | Core 0 (BLE, Wi-Fi, control) | Core 1 (camera, audio, SD) |
|---|---|---|
| Sleep | 1% | 1% |
| Listen (recording + live stream) | 1% | 7% |
| Listen + sending a clip over Wi-Fi | 8% (max 11%) | 9% (max 10%) |

**Why the real load will be higher (est.):** instruction counting ignores time spent waiting for PSRAM, flash and cache misses. It also leaves out the real BLE and Wi-Fi stacks, which don't run in the emulator, and the real camera driver's copying. Multiplying by 2 to 4 for those gives about **15 to 30% of core 1 while recording and 20 to 40% of core 0 during a transfer (est.)**. That fits within the software design's "30 to 50% of one core" guess. **CPU is not the bottleneck.** The card speed and SRAM are.

## 9. What an emulator cannot prove

- **Real speed.** QEMU doesn't run at the chip's real speed. All timing (card, BLE, Wi-Fi) came from our speed model, which uses estimated numbers. The CPU load is an estimate (section 8).
- **The real radio.** No BLE or Wi-Fi radio was used. Range, interference in a full lecture hall, phone Bluetooth quirks (iPhone vs Android), how BLE and Wi-Fi really share the antenna, and real hotspot behaviour are all untested.
- **The radio stacks' real memory use.** The 40 KB and 60 KB SRAM placeholders are guesses (section 7).
- **Heat.** The chip and camera temperatures are a made-up model. The OV5640 is known to run hot (over 70 °C without the heat sink).
- **Battery life.** The currents come from the hardware document's estimates, not a meter.
- **The real camera.** Real JPEG size changes with the scene. Autofocus, exposure and the camera driver's own frame drops weren't tested.
- **The real microphones.** Real sound levels, the gain setting and the noise filter on real speech, and the two mics' timing.
- **The real microSD card.** Real cards pause in their own pattern, wear out and slow down as they fill.
- **Power cuts and brown-outs.** Files may be damaged if the battery dies mid-write.
- **The real-board drivers themselves.** They compile, but they have never run.

## 10. What to test on the real XIAO next

1. **Flash the `xiao` build** and check each driver alone: camera frames arrive at 15 fps, both mics give left and right audio, the card mounts in 1-bit mode, buttons, temperature sensor, battery reading (needs a 2 × 100 kΩ divider to pin D0), BLE connects to the phone app.
2. **Card speed test:** record 720p at 15 fps for 1 hour on the card you plan to use. Log dropped frames and the write-buffer high-water mark (the firmware already reports both). Then repeat with a cheap card.
3. **SRAM during Wi-Fi:** send clips while recording and watch the lowest free SRAM. If it falls below about 20 KB, apply the savings in section 7.
4. **Heat:** with the heat sink on, measure the chip temperature (firmware) and the case surface (thermometer) over 1 hour, with and without Wi-Fi transfers. Set the 65, 75 and 85 °C thresholds in `te_config.h` from what you measure, and check the case stays under about 43 °C **(est. limit)**.
5. **Battery:** measure the real current with a USB power meter in Sleep, in Listen, and during a transfer. Replace the model numbers and recompute battery life.
6. **Radio in a real lecture hall:** BLE range and dropouts, Wi-Fi transfer time to the phone's hotspot, and the audio stream while Wi-Fi is sending.
7. **Real phone behaviour:** the phone app must send PINGs (at least every 4 s), commands, replies and confirmations in the format the mock phone in `tools/sim.py` uses.
8. **Voice lines:** record them and replace the beeps.
9. **Pins:** check the proposed mic, speaker, button and battery pins in `xiao_pins.h` against your wiring.

## 11. How to re-run

See `firmware/third-eye-sim/README.md`. In short: build with ESP-IDF 5.4.1, put QEMU 9.2.2 on the PATH, then run `python tools/run_tests.py` (about 25 min), `python tools/run_lecture.py` (1 hour) and `python tools/cpu_estimate.py` (about 4 min).
