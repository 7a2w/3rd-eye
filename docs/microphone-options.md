# Third Eye: microphone options for hearing a lecturer 15 m away

For Best Team, CEN100 section 16. Written November 19, 2026.

**Short answer:** use **two Knowles SPH0645LM4H-B I2S microphones on Adafruit breakout boards (Adafruit #3421)**. Each board is **16.7 × 12.7 × 1.8 mm**. Place them **18 mm apart** in a front-to-back line on the outer face of the earpiece. These mics work on both the XIAO ESP32S3 Sense and the Raspberry Pi Zero 2 W, cost about CAD $10 each in Canada, and are in stock. Be realistic about what they can do. At 15 m with no PA system, no small ear-worn mic will give clean transcripts. With the room's PA on, it should work reasonably well. The limit is the room, not the mic. Numbers marked **(estimate)** are textbook rules of thumb or our own calculations, not measurements.

---

## 1. What is realistic at 15 m

### Speech gets quieter with distance
Sound out in the open drops about **6 dB every time the distance doubles**. From 1 m to 15 m that adds up to about **23.5 dB** (20·log₁₀(15)).

- Normal voice: about 60 dBA at 1 m, so about **36 dBA** at 15 m (direct sound only).
- Raised "lecture" voice: about 66 dBA at 1 m, so about **42 dBA** at 15 m.

(estimate, typical speech levels)

### Room noise is louder than that
An occupied lecture hall usually sits around **40–45 dBA** **(estimate)**. That noise comes from ventilation, laptops, students moving, and whispering. An empty classroom is designed for 35 dBA or less. This means the lecturer's direct voice at 15 m is about **0 to +5 dB above the room noise**. Speech-to-text works well at about **+15 dB or better** and makes many errors below about +5 to +10 dB **(estimate)**.

### Echo (reverberation) is the bigger problem
In a hall, most of the sound reaching you at 15 m has bounced off walls and the ceiling first. The **critical distance** is the distance where direct sound and echoed sound are equally loud. For a typical 3000 m³ hall with a reverberation time of 1 second, it comes out at about **4 m** **(estimate**, from Dc ≈ 0.057·√(Q·V/RT60) with Q = 2 for a talker). At 15 m the echo is about **10 dB louder than the direct voice** **(estimate)**. Echo smears syllables together, and speech-to-text handles it badly. A louder or quieter mic doesn't fix that. Only being closer, using a directional pickup, or using the PA helps.

### The PA system is your friend
When the lecturer uses a microphone and the hall speakers, the speakers are usually much closer to you than the lecturer is. Speech at your seat is then typically **65–75 dBA**, which is **+20 dB or more** above room noise **(estimate)**. That is good enough for speech-to-text. One catch: several speakers at different distances give slightly delayed copies of the voice, so a little echo remains. Don't aim the beamformer so narrowly that it rejects the ceiling speakers.

### Which mic specs matter

- **SNR (signal-to-noise ratio)** tells you how quiet the mic's own hiss is. Self-noise = 94 − SNR, in dBA, so a 65 dB SNR mic hisses at 29 dBA and a 73 dB SNR mic at 21 dBA. Aim for **64 dB or more**. Above that the gain is small, because room noise (40+ dBA) drowns out the hiss. Example: 40 dBA room noise plus 29 dBA mic hiss gives 40.3 dBA total. With 21 dBA hiss it gives 40.05 dBA. That's only about 0.3 dB better **(estimate)**. SNR matters more when two mics are subtracted for beamforming (section 3).
- **Acoustic overload point (AOP)** is the loudness where the mic starts distorting. 120 dB SPL is plenty. Lectures never get near it, so every option here passes.
- **Sensitivity** is how big the digital number is for a given loudness, in dBFS at 94 dB SPL. −26 dBFS is typical. For a two-mic array, what matters most is the **tolerance** (±1 dB or ±3 dB), because the two mics must match.
- **Directionality** is whether the mic hears from all sides (omni) or mostly from the front. All small MEMS mics are omnidirectional. You get directionality from **two mics plus math** (section 3).
- **Interface** is PDM or I2S digital output. **I2S** works on both boards with no extra parts. **PDM** works on ESP32 boards (the S3 and P4 decode it in hardware). On the Pi Zero 2 W, PDM needs a patched kernel driver, which isn't supported [8].

**Bottom line for 15 m:** without the PA, expect a transcript with many errors. It may still catch keywords like "due Friday", but it won't be a clean transcript. With the PA, expect a usable transcript. **Test this in your real lecture hall early** (section 5).

---

## 2. Microphone options

All options below are omnidirectional MEMS mics running from 1.6–3.6 V, so they connect directly to the 3.3 V pins on both boards.

| Option | Interface | SNR / self-noise | AOP | Sensitivity (tolerance) | Size | Current (each) | Price (CAD) | Where to buy in Canada | Works with |
|---|---|---|---|---|---|---|---|---|---|
| **A. Knowles SPH0645LM4H-B on Adafruit #3421 (recommended)** [1][2] | I2S, 18-bit | 65 dBA / 29 dBA | 120 dB SPL | −26 dBFS (−29 to −23) | Chip 3.50 × 2.65 × 0.98 mm; **board 16.7 × 12.7 × 1.8 mm** | 600 µA | $9.47 Newark, $10.41 DigiKey.ca, $11.95 PiShop.ca | [Newark Canada](https://canada.newark.com/adafruit/3421/adafruit-i2s-mems-microphone-breakout/dp/48AC8094), [DigiKey.ca](https://www.digikey.ca/en/products/detail/adafruit-industries-llc/3421/6691114), [PiShop.ca](https://www.pishop.ca/product/adafruit-i2s-mems-microphone-breakout-sph0645lm4h/), BuyaPi, Elmwood | XIAO ESP32S3 ✔, Pi Zero 2 W ✔ |
| **B. TDK ICS-43434 on Adafruit #6049** [3][4] | I2S, 24-bit | 65 dBA / 29 dBA | 120 dB SPL | −26 dBFS ±1 dB | Chip 3.50 × 2.65 × 0.98 mm; board ~16.5 × 12.7 mm | 490 µA | ~$12.50 (US $8.95, **estimate** after conversion) | Leftover stock only. Adafruit says the chip is **discontinued** [4]. | XIAO ✔, Pi ✔ |
| **C. Infineon IM73D122V01 (bare chip)** [5][6] | PDM | **73 dBA / 21 dBA** (best) | 122 dB SPL | −26 dBFS ±1 dB | 4.00 × 3.00 × 1.20 mm; needs your own small PCB | 980 µA | ~$3.80 for the chip (US $2.73, **estimate**) plus PCB cost | [DigiKey](https://www.digikey.com/en/products/detail/infineon-technologies/IM73D122V01XTMA1/16999563) (40,000+ in stock), Newark. The flex evaluation kit is out of stock, with a 97-week lead time [7]. | XIAO ✔, ESP32-P4 ✔, **Pi ✘** (no supported PDM driver) |
| Baseline: mic already on the XIAO Sense (MSM261D3526H1CPM) [9] | PDM | 64 dBA / 30 dBA | 120 dB SPL | −26 dBFS ±1 dB | 3.50 × 2.65 × 0.94 mm, on the camera board | 670 µA | included | comes with the board | XIAO only |

**Ruled out: TDK T5848.** It looks attractive (68 dBA SNR, I2S, 310 µA, CAD $37 flex board at Newark), but its supply is limited to **1.62–1.98 V** [10]. Both boards use 3.3 V logic, so it would need a 1.8 V regulator and level shifters.

**Ruled out: "directional" mics.** No small directional MEMS mic exists, and shotgun or cardioid electret capsules are too big for an earpiece. Two omni mics with beamforming (section 3) is how earbuds and hearing aids get directionality.

### Why option A over C
- **It works on either board.** The board isn't decided yet. Because the IMX708 camera choice pushes toward a Pi, an I2S mic is the safe choice.
- **SNR barely matters here.** At 40+ dBA room noise, option C's 8 dB SNR advantage improves the final result by less than 1 dB for a single mic **(estimate)**.
- **It's easy to buy and solder.** You can order it in Canada this week, it comes on a solderable breakout, and there's a working Raspberry Pi guide [11]. Option C needs a custom PCB with a tiny pad-only (LGA) chip, which is hard to hand-solder.
- **Keep C as the upgrade path.** If you end up on an ESP32 board and do strong beamforming, the lower self-noise of option C becomes worthwhile (section 3). Have a small two-mic PCB assembled by a PCB service such as JLCPCB.

---

## 3. Is a two-mic array with beamforming worth it?

**Yes, modestly, and it costs almost nothing.** The second mic adds about CAD $10 and 0.6 mA. It needs **no extra pins**, because two I2S mics share one data line. One mic has its SEL pin tied to ground (left channel) and the other to 3.3 V (right channel) [11].

**What you gain (estimate):** a forward-facing two-mic beam (a "cardioid" or "hypercardioid" pickup pattern) rejects sound from the sides and back. In theory that improves the speech-to-echo and speech-to-noise ratio by about **4.8–6 dB**. On a real head, expect about **2–4 dB**. That helps, but it won't turn a 15 m recording without the PA into a clean one.

**How far apart the mics should be:** **15–20 mm, and 18 mm is the target.**
- The upper limit is set by aliasing. Spacing must be under half the wavelength of the highest frequency you keep. At 16 kHz sampling, the highest frequency is 8 kHz, whose wavelength is 343 / 8000 = 43 mm, so spacing must be under **21 mm**.
- The lower limit is set by low-frequency noise. Closer mics give weaker low-frequency output that must be boosted, and boosting amplifies the mics' self-noise. At 18 mm and 500 Hz, the raw difference signal is about 15 dB weaker than one mic **(estimate)**. That's why the beam is applied mainly **above about 800 Hz**, with a plain average of both mics used below that.
- Line the two sound holes up along the direction the wearer faces (an "endfire" array).

**What the firmware does (device, keep it simple):**
1. Read stereo I2S. Use 32-bit slots and keep the top 24 bits (the SPH0645 gives 18 valid bits). On the Pi, the `googlevoicehat-soundcard` overlay runs at a fixed 48 kHz [11], so resample to 16 kHz. On the ESP32, sample at 16 kHz directly.
2. Apply a high-pass filter at about 100 Hz. It removes DC offset, rumble, wind thumps, and handling bumps.
3. Apply a **fixed digital gain of about +24 dB** **(estimate; tune it in the real room)**. MEMS mics have no analog gain knob. Without gain, a lecturer at 15 m sits near −78 dBFS. With +24 dB, quiet speech moves well clear of 16-bit rounding noise, while loud PA speech peaks still stay below clipping.
4. Store and send **raw 16-bit stereo at 16 kHz**. That's 64 kB/s, easy over Wi-Fi. Note that the 30-second audio buffer grows from about 1 MB to about **1.9 MB**.

**What the phone app does (where the real processing belongs):**
1. **Match the two channels.** The SPH0645's sensitivity can vary by ±3 dB between parts. Adjust one channel's gain so both have the same long-term level during speech, or do a one-time calibration with a tone played from directly to the side.
2. **Beamforming.** Use a fixed forward differential beam above about 800 Hz, or an adaptive one (MVDR) if the team wants a stretch goal.
3. **Gentle noise suppression,** for example WebRTC NS on a low setting or RNNoise. **Don't overdo it.** Aggressive noise removal often makes speech-to-text *worse*. Always keep the raw recording and compare both versions.
4. **Automatic gain control** to about −20 dBFS, then speech-to-text.
5. **Duck the mic** (or use echo cancellation) while the earpiece speaker is playing, so the device doesn't transcribe itself.

(If the team chooses the XIAO ESP32S3, Espressif's ESP-SR library can do two-mic beamforming, noise suppression, and AGC on the device. Phone-side processing is still easier to change and test.)

---

## 4. Recommended setup and CAD guidance

**Parts:** 2 × Adafruit #3421 (SPH0645LM4H-B), solder wires directly with no headers, plus a 0.1 µF capacitor already on each board.

**Wiring:** both boards share 3.3 V, GND, BCLK, LRCL (WS), and DOUT. SEL goes to GND on the front mic and to 3.3 V on the rear mic.
- Pi Zero 2 W: BCLK on GPIO 18, LRCL on GPIO 19, DOUT on GPIO 20 [11].
- XIAO ESP32S3: any three free GPIOs set up for I2S standard mode.

**Current:** 2 × 0.6 mA = 1.2 mA, about 5 mAh over a 4-hour lecture day. That's negligible next to the board and camera.

### Dimensions for the CAD model
- **Each mic board:** **16.7 × 12.7 × 1.8 mm** [2]. Allow **3.0 mm** of height for solder blobs and wires **(estimate; measure your boards with calipers)**.
- **Mic chip on the board:** 3.50 × 2.65 × 0.98 mm. It sits on the component side, and its sound hole goes *through* the PCB to the other side [1][2].
- **Hole position on the board:** get it from Adafruit's published PCB file (GitHub: *Adafruit-I2S-MEMS-Microphone-Breakout-PCB*), or measure it. Don't guess.
- **Spacing between the two sound holes:** **18 mm ± 0.5 mm**, centre to centre, in a front-to-back line. Put the boards end to end, and record the real spacing for the app's beamformer.
- **Total mic footprint:** about **36 × 13 mm**, flat against the outer side wall.

### Sound port (the hole in the shell)
- **Which face:** the outer face of the earpiece (away from the head), with the two holes in a line pointing where the wearer looks. Never put the holes on the face that touches the head or hair, on the bottom (sweat, dust), or under a finger grip or strap.
- **Orientation:** mount each board with its **bare side (no components) against the shell wall**, so the PCB hole lines up with the shell hole [2].
- **Hole size:** **Ø1.0 mm** through the shell. The datasheets require the PCB hole to be at least 0.5 mm, larger than the mic's 0.375 mm port, and recommend 0.5–1.0 mm [3][10]; the shell hole follows the same logic. FDM 3D printers can't make a clean 1 mm hole, so model it at Ø1.2 mm, or print it closed and drill it with a 1.0 mm bit.
- **Wall thickness at the hole:** **1.0 mm.** Thin the wall locally with a Ø6 mm counterbore from the inside. A short, narrow sound path keeps the cavity's resonance above the speech band **(estimate: aim for under 2 mm total from outside air to the mic)**.

### Gasket (seals the path from the shell hole to the mic)
- **Ring gasket:** **inner diameter 2.0 mm, outer diameter 6.0 mm, 1.0 mm thick**, made of closed-cell foam (Poron or neoprene sticky foam) or soft silicone. Compress it to about **0.7 mm**: design the board pocket so the PCB sits 0.7 mm from the inner wall. This follows TDK's mounting and sealing guidance (AN-1003 and AN-1124 [3][10]), with sizes as **estimates** for this design.
- **Why it matters:** without a seal, sound leaks around the board into the hollow shell. That causes echoey, boomy pickup, and the two mics stop matching. 3D-printed parts also leak through layer gaps, so the gasket is essential.
- The gasket hole must never cover any part of the PCB or shell hole.

### Wind and handling noise
- **Mesh:** stick a Ø4 mm acoustic mesh disc (adhesive-backed acoustic vent or fine polyester mesh) in a **0.2 mm deep recess** over each outside hole. It blocks dust, sweat, and air puffs from walking or drafts.
- **Recess** each hole slightly, about 0.5 mm, so air flows over it instead of into it. Indoor "wind" is mostly from walking and head turns. The 100 Hz high-pass filter in firmware removes most of what's left.
- **Vibration isolation:** clamp each board only between the gasket and a soft foam pad behind it. No screws or hard plastic should touch the mic board. Leave slack in the wires.
- **Distance from other parts:** keep the mics **at least 10 mm** from the earpiece speaker, the camera's heat sink, and any hinge, clip, or button. Clicks and rubbing travel through the shell into the mic.

---

## 5. First test (do this before finalizing the CAD)
1. Tape the two breakout boards 18 mm apart onto a mock-up or a headband.
2. In your actual lecture hall, record a teammate reading the same paragraph from **5, 10, and 15 m**, with and without the PA. Also record one real lecture, if the professor gives permission.
3. Run speech-to-text on four versions: raw single mic, raw stereo average, beamformed, and beamformed plus noise suppression. Count word errors.
4. If accuracy at 15 m without the PA is poor, the honest options are: rely on the PA, sit closer, or treat 15 m as "keywords only". These matter more than any mic upgrade.

---

## Sources
1. Knowles SPH0645LM4H-B datasheet, Rev C (SNR 65 dBA, 600 µA, −26 dBFS, −29 to −23 dBFS tolerance, AOP 120 dB SPL, 3.50 × 2.65 × 0.98 mm). https://cdn-shop.adafruit.com/product-files/4455/4455_SPH0645LM4H-B.pdf
2. Adafruit I2S MEMS Microphone Breakout SPH0645LM4H (#3421), board size 16.7 × 12.7 × 1.8 mm, bottom port. https://www.pishop.ca/product/adafruit-i2s-mems-microphone-breakout-sph0645lm4h/ and https://www.adafruit.com/product/3421
3. TDK InvenSense ICS-43434 datasheet DS-000069 v1.2 (SNR 65 dBA, 490 µA, −26 dBFS ±1 dB, AOP 120 dB SPL, PCB sound hole ≥ 0.5 mm, mounting app notes AN-1003 and AN-1124). https://cdn-shop.adafruit.com/product-files/6049/6049_DS-000069-ICS-43434-v1.2.pdf
4. Adafruit I2S MEMS Microphone Breakout ICS-43434 (#6049), US $8.95, marked discontinued. https://www.adafruit.com/product/6049
5. Infineon IM73D122V01 datasheet (SNR 73 dBA, AOP 122 dB SPL, −26 dBFS ±1 dB, 980 µA at 3.072 MHz, 1.62–3.6 V, 4.00 × 3.00 × 1.20 mm, bottom port, IP57). https://www.infineon.com/assets/row/public/documents/30/49/infineon-im73d122-datasheet-en.pdf
6. DigiKey listing, IM73D122V01XTMA1 (US $2.73 each, in stock). https://www.digikey.com/en/products/detail/infineon-technologies/IM73D122V01XTMA1/16999563
7. DigiKey listing, KIT_IM73D122V01_FLEX (out of stock, 97-week lead time). https://www.digikey.com/en/products/detail/infineon-technologies/KITIM73D122V01FLEXTOBO1/16999573
8. Raspberry Pi forum, PDM microphones on the Pi Zero need a patched `bcm2835-i2s` kernel driver. https://forums.raspberrypi.com/viewtopic.php?start=1075&t=8496
9. Memsensing MSM261D3526H1CPM datasheet (the XIAO Sense on-board mic: SNR 64 dBA, 670 µA). https://cdn-reichelt.de/documents/datenblatt/A300/MIC-MSM261D3526H1CPM-ENG.pdf, and the Seeed XIAO ESP32S3 Sense page https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html
10. TDK T5848 datasheet DS-000479 v1.0 (supply 1.62–1.98 V, SNR 68 dBA; PCB hole 0.5–1.0 mm recommended; app notes AN-1003, AN-1124, AN-1140 on beamforming). https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8902/MMMICT5848-00-012.pdf
11. Adafruit Learn guide, I2S MEMS mic on Raspberry Pi (`dtoverlay=googlevoicehat-soundcard`, fixed 48 kHz, stereo via SEL pin, GPIO 18/19/20). https://learn.adafruit.com/adafruit-i2s-mems-microphone-breakout/raspberry-pi-wiring-test
