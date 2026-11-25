# Third Eye handoff

Written November 25, 2026, for whoever picks this up next. Read this first. The other docs it names hold the detail.

## Who and what

G B, on Best Team, CEN100 Introduction to Engineering, Fall 2026, section 16. The other members are Harjii, Emma, Michael, Varman, Bryson, Nicole, Ahnaf, George, Jian and Ahmad. Varman and Harjii write the design notebook, Harjii edits it, and Emma and George sketch.

Third Eye is an ear-worn lecture assistant. A mic and a camera capture the lecture, the device sends it to the student's phone, and AI on the phone turns it into notes, reminders and a study sheet. The earpiece does no AI itself.

The Phase 3 prototype is a CAD model showing how the hardware fits in a compact device. That CAD work is waiting on the board decision and on the team's parts list.

## How the user wants to be talked to

- Be direct and short. Lead with the answer.
- State things in the affirmative. Skip "X, not Y" phrasing.
- Don't pad with recaps of what they already said.
- Name tasks by what they are, never by their TE- numbers. Those are internal bookkeeping.

## Decisions already made

- November 18: mic plus camera, not mic only.
- November 19: the earpiece holds 30 seconds of audio and video, at HD (1280 x 720) and 15 fps. The buffer lives on the microSD card, not in RAM, because it is about 30 MB of video plus the audio.
- November 19: at least 4 hours of battery life, and a small mic that can pick up a lecturer from 15 m.
- Mic recommendation, not yet confirmed by the team: two Knowles SPH0645LM4H-B I2S mics on Adafruit #3421 breakouts, 16.7 x 12.7 x 1.8 mm, 18 mm apart front to back, about 0.6 mA each. Works on both candidate boards. See docs/microphone-options.md.
- November 23: the earpiece firmware was tested on an emulated XIAO ESP32S3 Sense. See "What the emulator test found" below.

## The board decision, still open

The camera the team bought is the Arducam B0310 (Amazon link titled "Arducam IMX708"). It is a MIPI CSI-2 sensor, so it cannot plug into the XIAO. As sold, with its 120 degree M12 lens, it reads slides to about 4 m.

- If 15 m is firm: Raspberry Pi Zero 2 W plus Camera Module 3, in a split design. The ear unit is about 30 x 28 x 16 mm (camera, mics, speaker) and a clip-on or neck pack is about 70 x 55 x 22 mm (Pi, PowerBoost 1000C, 2500 mAh LiPo), about 7.5 hours with power savings. Camera Module 3 stills read slides to about 9 to 12 m. Reaching 15 m needs a 6 to 8 mm M12 lens.
- If about 8 m is enough: XIAO ESP32S3 Sense plus the Seeed OV5640 autofocus camera (part 114993115, 8.5 x 8.5 x 5.4 mm), with a 1200 mAh battery in a clip-on pack, about 5.3 hours with savings. OV5640 stills read slides to about 6 to 8 m.

The IMX519 and the 64 MP Hawkeye add no reach on a Pi Zero 2 W. Take full-resolution stills on slide change instead of relying on the 720p video for reading slides. The full comparison is in docs/hardware-and-power.md.

## What the emulator test found

Report: docs/xiao-emulator-test.md. Code: firmware/third-eye-sim/.

All 20 feature and error-path tests passed on Espressif's QEMU (ESP32-S3, 8 MB octal PSRAM, 8 MB flash, 1-bit SD). A real-time 1-hour lecture run had 0 dropped frames, a PSRAM write-buffer peak of 2.24 of 3 MB, 3.15 GB written, no memory leak, and a modelled 214 mAh per hour, which is about 5 hours on the 1200 mAh pack.

Three things still need a real board:

1. Internal SRAM (512 KB) is tight while Wi-Fi sends a clip, and on the real board it could run out. The report lists ways to free memory.
2. Sending a clip while still recording takes 2 to 2.5 minutes, against 28 seconds once recording stops.
3. A cheap microSD card cannot sustain 720p at 15 fps. The firmware drops to 5 to 10 fps. Use a genuine high-endurance card.

The emulator has no real radio, camera or temperature, so range, heat and battery are estimates. The real-board drivers compile and have never run. Bugs found and fixed during the test: a start-up race, a crash with no SD card, and a `hal_init` name clash with the Wi-Fi library. The audio buffer was raised to 34 seconds (2.2 MB) so saving a clip does not overwrite its own audio.

## The software design

docs/software-design.md. The earpiece runs FreeRTOS: camera, audio and the SD writer on core 1; BLE, Wi-Fi upload and control on core 0. The 30 second buffer is stored as 2 second chunk files, with a 3 MB PSRAM write buffer. BLE carries the live audio (mono ADPCM, about 8 KB/s) and Wi-Fi carries the clips (about 31 MB each). Fallback settings are 720p at 10 fps, or 800 x 600 at 15 fps.

The flowchart (docs/flowchart-v2.drawio, media/flowchart-v2.png, docs/flowchart-changes.md) has four columns: Earpiece, Phone app, Cloud, Replies and reminders. The phone bridges to the cloud. BLE stays on and Wi-Fi turns on only for transfers. The earpiece steps are written so they fit either board.

## Stopped on request

On November 25, 2026 the user said to stop all of this work. Every agent stopped. Nothing below was finished, and nothing was pushed to GitHub. Don't resume it unless the user asks.

What actually got saved:

- The original upload, untouched: internal/uploads/third_eye.zip.
- A test harness only: internal/third-eye-work/harness/ (a fake lecture, slide video, whiteboard photos, and a driver script) and the shared brief at internal/third-eye-work/brief.md. The bug fixes were never saved. There is no fixes.patch, no rewritten Python, no new README, no new notebook, no new dashboard, and no screenshots.
- A start on the iPhone app only: internal/iphone-app-work/contract.md, three small scripts (bus.js, settings.js, util.js), and a vendored copy of Tesseract.js. There is no app/third_eye_iphone/ and no docs/iphone-app.md.

Known bugs in the original laptop app, found but not patched into the saved files: the newest PyAV breaks transcription in faster-whisper 1.2.1, so pin av==18.1.1; with no microphone the voice-question path leaves an audio-file lecture paused; with no sound card, playback kills the audio thread.

## Work that was underway when it stopped

1. **Laptop app cleanup.** The user uploaded third_eye.zip (saved at internal/uploads/third_eye.zip). It is a Python app: main.py, audio_capture.py, camera_test.py, transcriber.py, vision.py, assistant.py, study_sheet.py, sync.py, indicator.py, config.py, ui_server.py serving web/dashboard.html, colab_helpers.py, Third_Eye_Colab.ipynb, a README, and a Windows launcher "Start Third Eye.bat".

   The request, verbatim: "unzip this go through the code and make sure it is compatible for a test implimentation and then humanize it make it have no trace of ai redo the ui in a non ai way"

   Rules agreed for that work: behavior and features stay the same, including the AI features; the code, README, notebook and UI copy are rewritten in a plain voice with no AI tells (no narrating comments, no emoji, no words like "seamless", "robust", "leverage", "AI-powered"); the dashboard loses gradients, glows, glassmorphism, emoji icons and marketing copy in favor of a plain practical layout. The shared brief is internal/third-eye-work/brief.md and the test harness is internal/third-eye-work/harness/.

   Known bugs found so far: the newest PyAV breaks transcription in faster-whisper 1.2.1, so pin av==18.1.1; with no microphone the voice-question path leaves an audio-file lecture paused; with no sound card, playback kills the audio thread.

   Expected outputs: the cleaned app at app/third_eye/, a zip at docs/third_eye.zip, a review at docs/third-eye-app-review.md, and before/after screenshots at media/dashboard-before.png and media/dashboard-after.png.

2. **iPhone version.** The user asked for "a parralel iphone app thatr can do the exact same thing using the web interface in safari", built by several agents in parallel. It is a static web app that runs in Safari, uses the phone's mic and camera, and can be added to the Home Screen. Safari needs HTTPS for the mic and camera, and it stops recording when the screen locks or the user switches apps. Expected outputs: app/third_eye_iphone/, screenshots at media/iphone-app-1.png and on, and docs/iphone-app.md. The contract for its workers is internal/iphone-app-work/contract.md.

3. **GitHub.** The user created an empty public repo, https://github.com/7a2w/3rd-eye, and asked to push everything there. The plan is one clean first commit once both apps are finished, containing the two apps only, unless the user says to include the earpiece firmware and design docs too. Nothing has been pushed.

## Waiting on the team

- Is the 15 m slide-reading distance firm? That decides Pi versus XIAO.
- Does the phone act as the bridge to the cloud?
- Button gestures: short press saves a clip, long press stops Listen.
- Four unclear labels from their original flowchart, and how they were read: "time restrained stuff", "toggle use", "recording before", "Rpi receives Schedule".
- When do clips upload, during class or after? After class fixes the slow transfers and eases RAM, heat and battery. The code currently joins the phone's hotspot; the alternative is the earpiece making its own network.
- The rest of the "dead set" parts list, which was never sent. Dimensions and then the CAD layout depend on it.

## Offered but not accepted

A 1-hour test program to run on the real XIAO board. The steps are in section 10 of docs/xiao-emulator-test.md. Don't start it unless asked.

## Where things live

Everything is under /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/:

- docs/ holds the deliverables: hardware-and-power.md, microphone-options.md, software-design.md, flowchart-v2.drawio, flowchart-changes.md, xiao-emulator-test.md.
- media/flowchart-v2.png is the flowchart image.
- firmware/third-eye-sim/ is the emulated-XIAO firmware and its tests.
- internal/project-context.md is the running log of decisions, dated.
- internal/uploads/third_eye.zip is the user's original app, untouched.
- internal/ is scratch from the stopped work. The only pieces worth keeping are named above.
