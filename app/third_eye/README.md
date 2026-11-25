# Third Eye: AI earpiece prototype (laptop demo)

This prototype runs on a laptop in place of the earpiece. Third Eye is an always-on AI assistant you
wear: it listens to whatever is going on (a class, a meeting, a conversation, a call), works out what
the situation is, and handles the rest without being asked. It was built for university students with
ADHD, insomnia, or attention problems, but it works anywhere.

What it does on its own:

- Starts listening as soon as the window opens. No setup needed.
- Works out the situation (lecture, meeting, conversation, studying, phone call...) and names the session.
- Notes tasks, deadlines and events as people mention them, with dates worked out ("next Friday at 3"),
  and keeps `tasks.ics` up to date for your calendar.
- Explains a term or an unanswered question in your ear, at most once every 45 seconds.
- Answers anything when you say **"Hey Third Eye, ..."**. It also knows the time, the date, your open
  tasks, and can catch you up ("what did I miss?").
- After 10 minutes of quiet it ends the session, writes a summary and starts a new one.
- Saves every session to your Obsidian vault, if you have one.

### AI key

It works offline with simple rules, but it is much smarter with an AI key. Double-click **Set AI Key.bat**, paste the key, then restart Third Eye. Or set one of these yourself:

| Key | Cost | Get it |
|---|---|---|
| `GEMINI_API_KEY` | Free tier | aistudio.google.com |
| `ANTHROPIC_API_KEY` | Paid | console.anthropic.com |

```
setx GEMINI_API_KEY "your-key"
```

### Obsidian

Third Eye finds the vault Obsidian last had open and writes each session to `Third Eye/` inside it:
one note per session (summary, terms, tasks, pictures, transcript) and a running `Third Eye/Tasks.md`.
Tasks use the `- [ ] task 📅 2026-11-28` form, so the Tasks and Dataview plugins pick them up.
To use a different vault: `setx OBSIDIAN_VAULT "C:\Users\you\Documents\MyVault"`.

| Real device | In this demo |
|---|---|
| Earpiece camera | Laptop webcam |
| Earpiece microphone | Laptop mic |
| Recording indicator light | Blinking red **REC** dot on the video (and a real LED on GPIO 17 if run on a Raspberry Pi) |
| Earpiece speaker | Laptop speakers / earbuds |
| Chest pack (battery + processor) | The laptop |
| Sync to phone | A cloud-synced notes folder (Google Drive, OneDrive, Dropbox or iCloud) |

## Quick reference

**Start it:** double-click **Start Third Eye.bat** in this folder. Or, in a terminal:
```
cd %USERPROFILE%\Downloads\third_eye\third_eye
py -3.12 main.py
```
**Stop it:** click **Quit** in the dashboard, or press **Ctrl+C** in the terminal (or close it).

| In the dashboard | What it does |
|---|---|
| (nothing) | It starts listening by itself when the window opens |
| Say **"Hey Third Eye, ..."** | Ask anything, hands free |
| **Talk to Third Eye** | Listens to your question for 6 s, then answers out loud |
| Type in the box + **Enter** | Ask a typed question (works during and after the lecture) |
| **Pause** / **Resume** | Privacy mode: nothing is recorded until you resume |
| **End session** | Finishes the transcript, then builds the study sheet + reminders |
| **Look again** | Looks for cameras again after plugging one in |
| **New session** / **Quit** | Start another session / close the program (closing the window quits too) |

| Command-line options (add after `main.py`) | |
|---|---|
| `--course "BIOL 1010"` | Pre-fill the course name |
| `--camera 1` | Start on camera 1 (0 is usually the built-in webcam) |
| `--no-camera` | Run without a camera |
| `--mic 2` | Use microphone number 2 (or pick it in the dashboard) |
| `--audio-file lecture.mp3` | Use a recorded lecture instead of the mic (demo backup) |
| `--mute` | Don't play that recording out loud |
| `--model tiny.en` / `small.en` | Faster / more accurate speech-to-text (default `base.en`) |
| `--port 8001` | Use another port if 8000 is busy |
| `--no-browser` | Don't open the window automatically |
| `--manual` | Wait for **Start listening** instead of starting right away |
| `--browser` | Use a browser tab instead of the app window |

| Other useful commands | |
|---|---|
| `py -3.12 -m pip install -r requirements.txt` | Install or repair the packages |
| `py -3.12 camera_test.py` | Check which cameras work (saves test photos) |
| `setx GEMINI_API_KEY "AIza..."` | Save a free Gemini key (then open a new terminal) |
| `setx ANTHROPIC_API_KEY "sk-ant-..."` | Save a Claude key instead |
| `echo %GEMINI_API_KEY%` | Check the key is visible to this terminal |

Your notes, slide pictures, study sheets and `reminders.ics` are saved in `ThirdEyeNotes` (one folder per lecture).
Point `SYNC_FOLDER` in `config.py` at a Google Drive / OneDrive folder to get them on your phone automatically.

## What it does

1. **Live speech to text.** It transcribes the professor every ~8 seconds, offline, using Whisper.
   Each line is time-stamped.
2. **Third Eye camera.** It watches the board or slides with the camera. When the slide changes and the
   view holds still, it saves a snapshot and reads the text (OCR) into the notes.
3. **Ask out loud.** Click **Ask a question** and ask something like *"what did she just say about glycolysis?"*
   The assistant uses the last 5 minutes of the lecture plus the current slide, and answers out loud
   in 1–3 sentences.
4. **Study sheet + reminders.** When you end the lecture, it makes a one-page study sheet (TL;DR, key
   points, key terms, self-test questions, to-dos, confusing parts) as `.md` and `.docx`, plus a
   `reminders.ics` calendar file with spaced review reminders (+1, +3 and +7 days) and homework
   deadlines.
5. **Privacy.** **Pause** stops all recording, and the eye's pupil goes grey. The light is controlled in one
   place, so it can't show "off" while recording.
6. **Dashboard.** Everything runs from a clean dashboard in your web browser: setup, live notes and the study sheet.

## Setup (about 10 minutes)

Use Python 3.9 or newer.

```bash
cd third_eye
py -3.12 -m pip install -r requirements.txt
```

**Slide reading (optional):** install the Tesseract program.
- Windows: installer from https://github.com/UB-Mannheim/tesseract/wiki (tick "add to PATH")
- macOS: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

**AI answers and AI study sheets (optional but much better):** set **one** of these keys.

- **Free: Google Gemini.** Go to **aistudio.google.com**, sign in with a Google account, click **Get API key →
  Create API key**, and copy it. Then, in a terminal, run:
  `setx GEMINI_API_KEY "your-key-here"`
  The free tier has request limits (if you hit one, wait a minute). Google may use free-tier requests to improve
  its products, so don't use it for anything private.
- **Paid: Claude.** Get a key at **console.anthropic.com** (pay-as-you-go), then run:
  `setx ANTHROPIC_API_KEY "sk-ant-..."`

After `setx`, close the terminal and open a new one. The dashboard's top-right chip shows **AI: Gemini** or
**AI: Claude** when it worked. (On a Mac use `export GEMINI_API_KEY="..."` instead of `setx`.)
Without a key everything still runs. Answers come from searching the transcript, and the study sheet
is built from the most important sentences.

**Sync to your phone:** set `SYNC_FOLDER` in `config.py` (or the `THIRD_EYE_SYNC` environment
variable) to a Google Drive, Dropbox, OneDrive or iCloud folder on the laptop. Each lecture gets its
own subfolder that shows up on your phone.

## Run it

On Windows, use `py -3.12` instead of `python`:

```bash
python main.py                                   # opens the dashboard in your browser
python main.py --course "BIOL 1010" --camera 1   # pre-fill the course, start on camera 1
python main.py --audio-file lecture.mp3          # demo with a recorded lecture instead of the mic
python main.py --model tiny.en                   # faster on slow laptops
```

The dashboard opens at **http://localhost:8000**. Leave the black terminal window open; it's the engine.
Closing the browser tab doesn't stop the program, so press **Ctrl+C** in the terminal (or click **Quit**) to stop.

**The dashboard has three screens:**
1. **Setup:** type the course, pick your camera (with a live preview) and your microphone (talk and the meter
   bar should move). Third Eye starts listening as soon as the window opens (use --manual to wait for a click).
2. **Recording:** camera with the REC light, live notes on the right (transcript, captured slides, your
   questions). **Ask a question** listens to your question for 6 seconds, then answers out loud. You can
   also type a question at the bottom. **Pause** stops all recording. **End lecture** builds the study sheet.
3. **Study sheet:** key points, key terms, test-yourself questions, to-dos, review dates, and download buttons
   (Word, text, calendar reminders, full notes).

## Connecting a camera

The camera menu on the setup screen lists every camera that works (**Look again** checks again after you plug one in).

| Camera | How |
|---|---|
| **Built-in webcam** | Usually **Camera 0**. Nothing to set up. |
| **USB webcam** (best for the demo; clip it to your collar or glasses to act like the earpiece camera) | Plug it in, wait ~5 seconds, click **Look again**, pick **Camera 1** (or 2). |
| **Your phone as the camera** | Install a free "phone as webcam" app on the phone and the laptop, e.g. **DroidCam** (Android/iPhone) or **Camo**. On Windows 11 you can also use **Phone Link** (Settings → Bluetooth & devices → Mobile devices → "Use as a connected camera"). Once it's connected it appears as another camera; click **Look again** and pick it. |
| **Tiny camera for the real earpiece** (Option B) | A mini USB camera module, or a Raspberry Pi camera on the Pi. It shows up the same way. |

**If the camera shows no picture:**
- Close other apps that might be using it (Zoom, Teams, Discord, the Windows Camera app). Only one app can use a camera at a time.
- Windows: **Settings → Privacy & security → Camera**. Turn on *Camera access* and *Let desktop apps access your camera*.
- Mac: **System Settings → Privacy & Security → Camera**. Allow **Terminal** (or VS Code).
- Some laptops have a camera privacy shutter or a keyboard key (often F8/F10) that turns the camera off.

**Microphone:** the same privacy pages have a *Microphone* section. In the app, pick the mic from the menu and
check that the bar moves when you talk. AirPods and other headsets show up there too.

## Demo-day script (about 3 minutes)

1. Put on earbuds and say what the device is. Point at the REC light: *"It always shows when it's
   recording."*
2. Play a 2–3 minute clip of a real lecture with `--audio-file` (reliable in a noisy room). Text appears
   in the notes as the professor talks.
3. Point the camera at a printed slide or a whiteboard. The slide picture and its text appear in the notes.
4. Click **Ask a question**: *"What did the professor just say about ___?"* The answer comes back out loud.
5. Click **Pause** to show privacy mode, then **End lecture**. The study sheet appears. Click **Add review
   dates to calendar**.

## Files

```
Start Third Eye.bat  double-click to start (Windows)
main.py           runs everything (camera, mic, lecture flow)
camera_test.py    checks which cameras work
ui_server.py      local web server for the dashboard
web/dashboard.html  the dashboard (HTML/CSS/JS)
config.py         all settings
indicator.py      recording light (screen dot / Raspberry Pi LED)
audio_capture.py  mic or recorded-lecture input
transcriber.py    offline speech to text (faster-whisper)
vision.py         slide-change detection + OCR
assistant.py      live Q&A (Claude API or offline) + text to speech
sync.py           saves the notes file in the synced folder
study_sheet.py    end-of-lecture study sheet (.md/.docx) + calendar reminders (.ics)
```

## Troubleshooting

- **No transcription:** your mic may be quiet. Lower `SILENCE_RMS` in `config.py`, or pick the mic
  with `--mic N` (list devices with `python -m sounddevice`).
- **Too slow / captions lag:** use `--model tiny.en`.
- **Wrong camera:** pick it in the camera menu (see *Connecting a camera*).
- **Too many or too few slide snapshots:** adjust `SLIDE_CHANGE_THRESHOLD` (a %) in `config.py`.

## Moving to hardware (Option B)

Copy the folder to a Raspberry Pi 5, plug in a USB mic, a Pi camera or USB camera, and an LED on
GPIO 17, then run `pip install gpiozero`. The REC light then drives the real LED. Run with
`--model tiny.en` for speed.

## Note on consent

Many universities restrict recording lectures without permission, but often approve it as an
accommodation through the disability or accessibility services office. The visible REC light,
privacy pause, and offline transcription are all part of making the device acceptable to use.
