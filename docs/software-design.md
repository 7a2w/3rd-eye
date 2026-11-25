# Third Eye: How the Software Works and the Compute It Needs

Best Team, CEN100 section 16. Draft for the design notebook, November 19, 2026.

Numbers marked **(est.)** are our estimates and must be measured on the real board. Numbers with a source in brackets come from people who tested the hardware; see Sources at the end.

## 1. The big picture

Third Eye has three parts. Each does only the job it is good at.

- **Earpiece (XIAO ESP32S3 Sense).** Captures sound and video. Keeps the last 30 seconds on the microSD card. Sends things to the phone. It does **no AI**: the chip is too small for speech-to-text or summaries.
- **Phone app.** The "brain". Turns speech into text, finds deadlines and key points, stores clips, and shows the notes.
- **Cloud (optional).** Only used if the phone is too slow or we want better summaries. The app should work without it.

```
 EARPIECE (ESP32-S3)                    PHONE APP                        CLOUD (optional)
 ---------------------                  ---------                        ----------------
 PDM mic --> audio task --+--(BLE, compressed audio, ~8 KB/s)--> speech-to-text --> (or cloud STT)
                          |                                       |
 Camera --> JPEG frames --+--> 30 s rolling buffer on microSD     v
 (sensor makes the JPEGs)          |                         find deadlines /
                                   |                         key moments
 Button tap ---------------------->|<--(BLE "save clip" command)--+
                                   v                              |
                         save 30 s clip as a file                 |
                                   |                              v
                                   +--(Wi-Fi, ~31 MB clip)--> clip library --> summary (on phone or cloud LLM)
                                                                  |
                                                                  v
                                                    Student reviews: transcript, summary,
                                                    deadline list, 30 s video clips
```

### Step by step, from lecture to review

1. Student puts on the earpiece and opens the app. They connect over **Bluetooth Low Energy (BLE)**.
2. The earpiece records all the time, but only keeps the **last 30 seconds** of audio and video. Older data is written over.
3. At the same time it sends a **small, compressed audio stream** to the phone over BLE. Video does *not* go over BLE; it is too big.
4. The phone turns the audio into text live and watches for important phrases ("due Friday", "on the exam", "assignment").
5. A clip is saved when **(a)** the student taps the earpiece button, or **(b)** the phone hears a key phrase and sends a "save" command over BLE.
6. The earpiece copies the 30-second buffer into a saved clip file and keeps recording.
7. When convenient (right away, or after class), the earpiece turns on **Wi-Fi** and sends saved clips to the phone. Wi-Fi is about 20 times faster than BLE, but uses more power, so it is only on when needed.
8. After the lecture, the app writes a summary, a list of deadlines (which can go into the phone calendar), and links each item to its video clip.
9. The student reviews notes and deadlines on the phone.

## 2. Earpiece firmware in detail

The ESP32-S3 has **two processor cores** and runs **FreeRTOS**, which lets several small programs ("tasks") run side by side.

| Task | Core | What it does |
|---|---|---|
| Camera task | 1 | Takes finished JPEG frames from the camera (the camera chip compresses them itself) and puts them in a RAM queue. |
| Audio task | 1 | Reads the PDM mic at 16 kHz, 16-bit. Keeps 30 s of raw audio in PSRAM (about 1 MB). Compresses a copy with ADPCM (4 times smaller) for the BLE stream. |
| SD writer task | 1 | Writes frames from the RAM queue to the microSD card in large blocks. Manages the rolling buffer. |
| BLE task | 0 | Sends the audio stream; receives commands (start, stop, save clip, start Wi-Fi). |
| Wi-Fi upload task | 0 | Only runs when sending clips. Sends files to the phone. |
| Control task | 0 | Button, battery level, temperature check, status LED. |

**The 30-second rolling buffer.** HD video at 15 fps is about 1 MB every second **(est.)**, so 30 seconds is about **30 MB of video plus 1 MB of audio**. That cannot fit in RAM (8.5 MB total), so it lives on the microSD card. The firmware writes video in **2-second chunk files** and keeps 15 of them, deleting the oldest when a new one is made. To save a clip, it just renames the last 15 chunks into a `clips/` folder (fast, no copying) and adds the 30 s of audio from PSRAM.

**Why a big RAM write buffer.** SD cards sometimes pause for a fraction of a second while they clean up internally. A **2 to 3 MB buffer in PSRAM** holds frames during these pauses so none are lost. The FPV project uses a 3 MB buffer for this reason [1].

**Hand-off to the phone.**
- **BLE (always on, low power):** control commands and the compressed audio stream (about 8 KB/s). BLE can carry roughly 50 to 100 KB/s in practice **(est.)**, so audio fits easily, but one 31 MB clip would take 5 to 10 minutes.
- **Wi-Fi (on only when needed):** bulk clip transfer. In a busy classroom, expect about 1 to 2 MB/s **(est.)**, so one clip takes about 15 to 30 seconds. Campus Wi-Fi usually needs a login page, which the earpiece cannot handle, so the earpiece should create its own small network (or join the phone's hotspot) just for the transfer.

**Power and heat.** The FPV project measured the Sense using **less than 300 mA** while streaming video [1]. At 3.7 V that is about **1 W** in a device the size of a thumb, which will get warm. The OV5640 camera also **overheats without a heat sink** on these boards [2]. The firmware should read the chip's temperature sensor and drop to a lower frame rate or resolution if it gets too hot. Surfaces touching skin for a long time should stay below roughly 43 °C (commonly used limit for wearables, est.).

## 3. Compute and resource budget

| Stage | Resource | Need | Available | Verdict |
|---|---|---|---|---|
| Earpiece CPU | Processor load | 30 to 50% of one core while recording; more during Wi-Fi upload **(est.)** | 2 cores at 240 MHz | OK |
| Earpiece fast RAM | SRAM | about 250 KB (Wi-Fi + BLE stacks, tasks) **(est.)** | 512 KB | OK, but tight with Wi-Fi and BLE both on |
| Earpiece big RAM | PSRAM | about 4.5 MB: 0.5 MB camera frames, 3 MB SD buffer, 1 MB audio **(est.)** | 8 MB | OK |
| microSD writes | Write speed | about 1 MB/s video + 32 KB/s audio **(est.)** | about 1.6 MB/s measured on ESP32-S3 [1] | OK, about 1.5 times headroom |
| BLE | Throughput | 8 KB/s audio + commands | 50 to 100 KB/s **(est.)** | OK |
| Wi-Fi | Throughput | 31 MB per saved clip | 1 to 2 MB/s in a classroom **(est.)** | OK, 15 to 30 s per clip |
| Battery | Current | 250 to 300 mA (under 300 mA measured [1]) | 1-hour lecture needs about 300 mAh | Needs at least a 400 mAh battery |
| Phone: speech-to-text | Processing | 1 hour of audio | On-device: about 5 to 10 minutes per hour on a recent phone **(est.)** | OK |
| Phone or cloud: summary | Processing | about 9,000 words of transcript per hour | On-device small model: 1 to 3 minutes; cloud: under 1 minute **(est.)** | OK |

**Speech-to-text options (check prices before deciding; these move fast).**
- **On the phone, free:** Apple's built-in speech recognition (iPhone), Android's on-device recognizer, or an open-source Whisper model running in the app. Works with no internet and keeps lecture audio private. Accuracy on fast speakers and technical words is lower than the best cloud services.
- **Cloud:** OpenAI, Deepgram, AssemblyAI and Google all sell speech-to-text by the minute. Prices we have seen are about **US $0.10 to $0.40 per lecture hour (est.)**.

**Summaries.** One lecture hour of text is about 12,000 tokens (word pieces). A small cloud language model costs **under US $0.05 per lecture hour (est.)**; reading a few saved video frames (slides, whiteboard) adds a few cents. On-device models built into newer phones (Apple Intelligence, Gemini Nano on Android) can do basic summaries for free but are weaker.

**Total cloud cost:** roughly **US $0.15 to $0.50 per lecture hour (est.)**, or US $0 if everything runs on the phone. For a student with 15 lecture hours a week, that is about $2 to $8 per week if fully cloud-based.

## 4. Hardware feasibility check

**Camera frame rate: both claims confirmed in the sources.**
- **Stock OV2640:** tops out at **about 13 fps at 1280 x 720** [1]. A second project measured 12.5 fps [2]. It **cannot** do HD at 15 fps.
- **OV5640 on the XIAO S3 Sense:** reported at **30 fps at 1280 x 720** [1], because the ESP32-S3 can receive camera data twice as fast as the older ESP32. This is the developer's own testing, so we should check it on our board. The same developer notes 720p at 30 fps needs heavy compression to fit through Wi-Fi; at 15 fps that problem is halved. The OV5640 is a drop-in swap (same connector), sold separately [1].
- Some newer Sense boards may ship with a different camera chip. Check which one yours has.

**microSD speed: yes, but with little extra room.**
- The Sense's card slot is wired for the simple **1-bit mode only**. The faster 4-bit mode, which roughly doubles speed on the ESP32-S3 [2], is **not possible** on this board.
- In 1-bit mode the FPV project measured a **maximum of about 1.6 MB/s** of video writes on the ESP32-S3 [1]. Our 1 MB/s need fits, with about 50% headroom.
- Card quality matters a lot: a cheap no-name card was **3 times slower** than a genuine SanDisk card in testing [2].
- Recording all the time writes about **3.6 GB per lecture hour (est.)**, which wears out normal cards. Use a **"high endurance"** card.

**Recommended configuration**
- **Camera:** OV5640 (replace the stock OV2640), with a small heat sink.
- **Video:** 1280 x 720 at **15 fps**, medium JPEG quality, aiming for about 60 KB per frame (about 0.9 MB/s).
- **Storage:** genuine high-endurance microSD (Class 10 / U1 or better), 32 GB or less, formatted FAT32 [1]; SD/MMC 1-bit mode at high speed; 3 MB PSRAM write buffer.
- **Fallback if heat, SD speed or battery fails testing:** 800 x 600 at 15 fps (the OV2640 can do this [1]), or 720p at 10 fps. Either cuts SD writes and power by about a third or more.

**Test first:** write a 1-hour test program that records 720p at 15 fps to the card and logs dropped frames, temperature and battery drain. This answers the biggest risks before the CAD design is final.

## 5. Open decisions for the team

1. **Board choice:** confirm the XIAO ESP32S3 Sense, and buy an OV5640 camera module.
2. **Privacy:** sending all audio to the phone for live transcription is useful, but it means the lecture is always being "listened to". Alternatives: transcribe only saved clips, or only transcribe when the student turns it on. Professors may need to give permission.
3. **What triggers a save:** button only, key phrases only, or both?
4. **On-phone vs cloud AI:** free and private (phone) versus more accurate (cloud, small cost, needs internet).
5. **Wi-Fi setup:** earpiece makes its own network, or joins the phone's hotspot? When do uploads happen: right away, or after class?
6. **Battery size vs comfort:** at least 400 mAh for one lecture; a full day of classes needs a bigger battery or charging between classes.
7. **iPhone, Android, or both** for the app (this decides which built-in speech tools we can use).
8. **Heat limit:** what surface temperature counts as "too hot", and what the device does when it gets there.

## Sources

[1] natiy4, *hx-esp32-cam-fpv* README (camera frame rates, SD write limits, SD buffer, power, SD card format). https://github.com/natiy4/hx-esp32-cam-fpv. Firmware `components/air/main.cpp` shows the XIAO Sense card using SPI or 1-bit SD/MMC on GPIO 7, 8 and 9.

[2] s60sc, *ESP32-CAM_MJPEG2SD* README (OV2640 frame rates, 4-bit vs 1-bit speed on ESP32-S3, SD card quality, OV5640 heat, audio format). https://github.com/s60sc/ESP32-CAM_MJPEG2SD

Cloud prices and phone processing speeds are estimates based on 2025 to 2026 published pricing and typical performance; recheck current prices before finalizing.
