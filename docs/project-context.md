# Third Eye project context

From Best Team's design notebook, shared November 18, 2026, plus decisions made in this Project since.

## Course and team
- CEN100 Introduction to Engineering, Fall 2026, section 16
- Team name: Best Team
- Members: Harjii, Emma, Michael, Varman, Bryson, Nicole, Ahnaf, George, Jian, Ahmad
- Notebook: Varman and Harjii write, Harjii edits, Emma and George sketch
- Midterm design review: November 4, 2026 (done)

## Concept
Third Eye is a small AI assistant worn around the ear that helps students remember lecture information. A microphone and a camera capture the lecture, the device sends it to a smartphone, and AI on the phone organizes and saves the important parts.

## Decisions
- November 18: microphone plus camera (not mic only).
- November 18: candidate board is the Seeed XIAO ESP32S3 Sense instead of a Raspberry Pi, for size. Not yet confirmed by the team.
- Plan: the team uploads its parts list, the agent finds each part's dimensions, then the team and agent discuss the CAD model.
- November 18: the team worried the XIAO's RAM and compute are too small. Estimate given: the device program needs about 1.5 MB of 8.5 MB RAM (mostly camera frame buffers in PSRAM) and well under half of one core, since speech-to-text and summaries run on the phone. Offered to write a test program that measures real usage once the team has the board.
- November 19: requirement that the device holds 30 seconds of audio and video (this replaces the earlier photos-only suggestion). Estimates at 10 fps: audio about 1 MB at 16 kHz; video about 2.5 MB at 320 x 240, 9 MB at 640 x 480, 20 MB at 1280 x 720. Recommended keeping the 30-second buffer on the microSD card rather than in RAM, and sending video over Wi-Fi because Bluetooth is too slow.
- November 19: team chose HD video (1280 x 720) at 15 fps. Estimate about 30 MB per 30 seconds plus 1 MB of audio, so the buffer must live on microSD. Flagged that HD at 15 fps, about 1 MB/s of SD writes, and heat are at the board's limits and should be tested early, with 800 x 600 or 10 fps as the fallback.
- November 19: software design written at /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/docs/software-design.md. The earpiece does no AI; the phone does speech-to-text and summaries, with cloud optional at about $0.15 to $0.50 per lecture hour. Recommended: OV5640 camera with a heat sink, 720p at 15 fps (about 60 KB per frame), a genuine high-endurance microSD of 32 GB or less in FAT32 using SD/MMC 1-bit mode with a 3 MB PSRAM write buffer, and at least a 400 mAh battery for a one-hour lecture. Fallback: 800 x 600 or 10 fps. First test: a 1-hour recording that logs dropped frames, heat and battery drain.
- November 19: camera set to the Arducam IMX708 module (https://www.amazon.ca/Arducam-IMX708-Camera-Module-Raspberry/dp/B0BZR6XL3Y). It is a MIPI CSI-2 raw sensor, so it cannot connect to the XIAO ESP32S3 Sense; keeping it means a Raspberry Pi Zero 2 W class board or possibly an ESP32-P4. Board options are being compared in docs/hardware-and-power.md.
- November 19: new requirements: at least 4 hours of battery life, and a small high-quality mic that can pick up a lecturer from 15 m away.
- November 19: the team's software flowchart is saved at internal/flowchart-original.webp. It has a Listen state and a Prompt state, cloud LLM agents with a database, a reminder timer, an offline queue, and voice output through a speaker in the earpiece. It assumes the earpiece uploads straight to the cloud over Wi-Fi.
- November 19: the team wants the earpiece to work in the real world at far distances, such as reading slides or boards from about 15 m. Estimate given: 720p video reads 24 pt slide text to about 4 to 5 m, OV5640 5 MP stills to about 10 to 13 m, IMX708 12 MP stills to about 15 to 20 m. Suggested full-resolution photos of slides on a timer or slide change alongside the 720p buffer. This favors the IMX708 and a Raspberry Pi-class board, pending the size and battery comparison.
- November 19: recommended mic (not yet confirmed by the team): two Knowles SPH0645LM4H-B I2S mics on Adafruit #3421 breakouts, 16.7 x 12.7 x 1.8 mm each, 18 mm apart front-to-back on the outer face, about 0.6 mA each; works with the XIAO and the Pi Zero 2 W. Stereo 16 kHz makes the 30 s audio buffer about 1.9 MB. At 15 m without a PA, transcripts will be poor; with the PA, usable. CAD: 1 mm port per mic (1.2 mm for FDM), gasket and mesh, at least 10 mm from speaker and heat sink. Details in docs/microphone-options.md.
- November 19: board comparison done in docs/hardware-and-power.md. The linked Arducam is SKU B0310: IMX708 with a 120° M12 manual-focus lens, too wide for distance as is. If 15 m is firm: Raspberry Pi Zero 2 W + Camera Module 3 (standard 66° lens) in a split design (ear unit about 30 x 28 x 16 mm with camera, mics and speaker; clip-on or neck pack about 70 x 55 x 22 mm with the Pi, PowerBoost 1000C and a 2500 mAh LiPo), about 7.5 h with power savings. If about 8 m is enough: XIAO ESP32S3 Sense + Seeed OV5640 AF camera (part 114993115, 8.5 x 8.5 x 5.4 mm), 1200 mAh battery in a clip-on pack, about 5.3 h with savings. Real-world slide reading: Camera Module 3 stills about 9 to 12 m, OV5640 stills about 6 to 8 m; 15 m needs a 6 to 8 mm M12 lens. Waiting on the team: is 15 m firm?
- November 19: flowchart v2 delivered (docs/flowchart-v2.drawio, media/flowchart-v2.png, docs/flowchart-changes.md), hardware-neutral so it fits either board. Waiting on the team to confirm: the phone as the bridge to the cloud; Second Brain short press saves a clip and long press stops Listen; how four unclear labels were read ("time restrained stuff", "toggle use", "recording before", "Rpi receives Schedule").
- November 23: firmware tested on an emulated XIAO ESP32S3 Sense (Espressif QEMU 9.2.2, 8 MB octal PSRAM, 1-bit SD). Report at docs/xiao-emulator-test.md, code at firmware/third-eye-sim/. All 20 feature and error-path tests pass. A real-time 1-hour lecture run had 0 dropped frames, PSRAM write buffer peak 2.24 of 3 MB, 3.15 GB written, no leaks, and modelled 214 mAh per hour (about 5 h on 1200 mAh, est.). Real-board risks: internal SRAM is tight during Wi-Fi transfers and must be measured; clip transfers while recording take 2 to 2.5 min (28 s when not recording); cheap microSD cards can't sustain 720p at 15 fps. Audio buffer raised to 34 s (2.2 MB). Real-board drivers compile but have never run. Waiting on the team: upload clips during or after class, and phone hotspot (current code) vs the earpiece's own network; also check the proposed pin map in xiao_pins.h.
- November 25: the user uploaded the laptop and Colab prototype (internal/uploads/third_eye.zip) and asked to make it run as a test, rewrite it so it does not read as AI-written, and redo the dashboard. They then asked for a Safari iPhone version of the same app, and created an empty public repo at https://github.com/7a2w/3rd-eye for one first commit of the two apps once both were done. They then ordered all of that work stopped. Nothing was rewritten, packaged, or pushed. Saved from the stop: the test harness at internal/third-eye-work/harness/, and a partial iPhone start (contract plus vendored Tesseract.js) at internal/iphone-app-work/. The handoff is docs/handoff.md.

## User research (October 2)
- Students struggle to keep up when professors speak quickly.
- Some students have trouble focusing and remembering important details.
- Deadlines and information mentioned only verbally get forgotten.
- Students would benefit from reviewing lecture information later.
- Constraints: affordability, comfort, recording privacy.
- Decision: capture important information rather than recording everything.

## Candidate components (September 30)
Raspberry Pi board, microphone, camera module, rechargeable battery, Bluetooth link to a phone, smartphone for processing.

## Open questions
- How small can the device be, and is it comfortable to wear?
- How does it connect to the phone?
- Will the battery last long enough? The camera draws several times the power of the mic alone, so photo snapshots rather than video were suggested.
- How to handle recording privacy?

## Phase 3 prototype
A CAD model showing how all the hardware fits together inside a compact device.

## Midterm review section owners (November 3)
- Problem and stakeholders: Varman, Ahnaf
- Boundary diagram: Harjii, Michael
- Concept and decision rationale: Bryson, Ahmad
- Top risks and design insight: Emma, George
- Phase 3 prototype plan: Jian, Nicole

## FMEA (October 19)
Individual entries by ID: Harjii 2, Varman 3, Emma 4, Bryson 7, Michael 8.

## Ideas considered before Third Eye
Data centre energy efficiency, regenerative escalators, a pillow alarm, a self-watering plant pot, a posture-correcting chair, and other brainstorm ideas from September 16 to 30.

## Missing from the shared text
The sketches, the code flowchart, and the FMEA table were images in the notebook and did not come through.
