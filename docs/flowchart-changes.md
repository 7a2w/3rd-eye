# Software flowchart v2: what changed and why

Best Team, CEN100 section 16. November 19, 2026.

- Editable file: `docs/flowchart-v2.drawio` (open at [app.diagrams.net](https://app.diagrams.net) or in the diagrams.net desktop app)
- Picture: `media/flowchart-v2.png`
- Original: `internal/flowchart-original.webp`

The structure, colours and intent are the same as the original: Sleep, Listen state (blue), Prompt state (orange), the cloud agents, the Main database (green), the Reminder timer (purple), the database-edit approval loop (lavender), End Prompt SubState (light green) and the uploads and clouds (pink). The chart is now split into four columns so you can see which device does each step: Earpiece, Phone app, Cloud, and Replies and reminders. Dashed arrows are wireless links (BLE, Wi-Fi or internet).

## Team to confirm: the phone is now the bridge to the cloud

**This is the biggest change. Please agree on it as a team before you keep it.**

- **Original:** the earpiece uploaded straight to the cloud over Wi-Fi ("upload as live", "No wifi connection").
- **v2:** the earpiece talks only to the phone. BLE stays on all the time and carries the button presses, commands, live audio and voice lines. Wi-Fi turns on only to send saved 30-second clips to the phone, using the earpiece's own small network or the phone's hotspot. The phone then uses its own internet to reach the cloud.
- **Why:** campus Wi-Fi usually needs a login page, which the earpiece can't fill in. Video is too big for BLE, and Wi-Fi uses too much battery to leave on. This matches section 1 of `docs/software-design.md`.
- **Knock-on changes:** the "No wifi connection" checks become "Phone connected (BLE)?" on the earpiece and "Internet available?" on the phone. "Rpi receives Schedule" becomes "phone receives reply or reminder". The phone is a new column, outlined in yellow.

## Listen path

| Change | Why |
|---|---|
| Replaced "Real world interface output (approx every 15s or when output stops)" and "upload as live" with a **30 s rolling buffer** of audio and video, with the oldest data overwritten. A clip is saved by copying the buffer. | This is the requirement from November 19. Video is too big to stream all the time. |
| Added the two things that **save a clip**: tapping the Second Brain button (short press), or the phone hearing a key phrase ("due", "exam", "assignment") and sending a "save clip" command over BLE. | The original never said what makes the device keep something. This uses both triggers from the software design. Open decision 3 in the design doc (button only, key phrases only, or both) is still yours to make. |
| **Stopping Listen is now a long press**, so a short press can save a clip. Long press leads to "toggle sleep: mic + camera off", then "wait for queued clips to finish sending", then Sleep. | Before, pressing the same button again stopped recording. One button now needs two gestures. Please confirm this is what you want. |
| Added a compressed copy of the live audio going to the phone over BLE (about 8 KB/s), and "live speech-to-text on phone". The cloud's "process and convert to text" now receives that transcript. | The phone does speech-to-text in the software design. It also has to listen live to catch key phrases. |
| "process and convert to images" now works on the **saved clips** (key frames such as slides and the board). | Only saved clips reach the phone and cloud. Full video is never streamed. |
| Removed "wait 2s then ensure upload finish" and "ensure finish sending output when video under 15s (toggle ended prematurely)". | Those dealt with 15-second uploads that might be cut short. With a rolling buffer, nothing is half-sent when you stop. The only job left is finishing queued clip transfers, which is covered. |

## Prompt path

| Change | Why |
|---|---|
| The prompt now sends **voice + the latest camera frame** to the phone over BLE. The phone uploads it "as prompt info". | This keeps your "process and convert to images" step for prompts. One frame (about 60 KB) fits over BLE. Full video doesn't. |
| End Prompt SubState no longer goes to "toggle sleep (stop output)". It goes to "ensure finish sending the last of the prompt", then to the same BLE check. | If the student was in Listen mode, the camera and mic must stay on. What happens after the answer is decided at the end of the chat (see below). |
| The prompt's offline queue moved to the phone ("add prompt to offline queue on phone, mark with ID", then "check internet every 5 s", then "play online again voice line, then upload"). The yes/no loop is kept. | The phone is now the device that needs internet. |

## Missing error paths added

- **Earpiece loses the phone (BLE), Listen:** it keeps recording into the 30 s buffer (button saves still work), plays the offline voice line, and tries to reconnect every 5 s.
- **Earpiece loses the phone (BLE), Prompt:** it plays the offline voice line and goes back to the state it was in before the prompt.
- **Clip can't be sent over Wi-Fi:** the clip goes into an offline queue on the earpiece (marked with an ID) and is retried every 5 s. The original Listen-side "add to offline que and mark with id" had no retry and went nowhere.
- **Phone has no internet, Listen:** the transcript and clips go into an offline queue on the phone and upload when it's back online.
- **Saved clip deleted from the earpiece only after the phone confirms it arrived.** Without this, saved clips would fill the earpiece's storage.
- **LLM agent fails or times out:** the earpiece plays an error voice line ("Sorry, I couldn't answer. Please try again.") instead of going silent.
- **Earpiece not connected when a reply or reminder arrives:** the phone shows a notification instead.
- **Database edit refused:** "explain changes and request approval" now leads to "Student approves? (Prompt button reply)". Yes leads to "make changes", which saves to the Main database. No leads to "discard changes". The original had no "no" branch.

## Dangling or unclear arrows fixed

- **"recording before"** (after "end chat") is now a decision, "Was Listen on before the prompt?". Yes goes back to the Listen state with recording still running. No goes back to Sleep.
- **"propmpt action"** (after "prompt yes") is now "back to Prompt state", so the conversation continues in the normal Prompt path.
- **"play online agian voiceline"** went nowhere. It now leads to the upload.
- **The second "Sleep" hexagon** is kept, because it's the end of the stop-Listen path.
- **Both "send to device" clouds** now go to one "phone receives reply or reminder" step, then the BLE check, then "earpiece speaker plays it".
- **"make changes"** now points into the Main database ("saved"). Before, it looped back into the sorting agent, which made the approval loop circular.

## Naming and spelling made consistent

- Spelling: earpoeice and earpeice became earpiece, que became queue, Remider became Reminder, calender became calendar, usefull became useful, INPORTANT became IMPORTANT, agian became again, propmpt became prompt.
- Wording: "gave input" became "pressed". "Rpi" was removed because the board isn't decided yet (XIAO ESP32S3 Sense or a Pi Zero 2 W class board). "Sorting agent to configure database" became "Sorting agent to organize database (Obsidian)". "llm readout" became "LLM reads out".
- The two buttons are always called "Second Brain button" and "Prompt button".

## Works with either board

The device steps don't name any hardware ("30 s rolling buffer", "save clip", "offline queue on earpiece"), so the chart is the same whether the team uses the XIAO ESP32S3 Sense or a Raspberry Pi Zero 2 W (see `docs/hardware-and-power.md`). How each board does it:

- **Pi Zero 2 W:** the buffer is kept in memory as H.264 video using Picamera2, and is written to the SD card only when a clip is saved.
- **XIAO:** the buffer is MJPEG video in 2 s chunk files on the microSD card, with the audio in PSRAM.

Both boards have BLE and Wi-Fi, so the phone-bridge design is the same for either one.

## Not added on purpose

Overheating and low-battery handling, cloud cost limits, privacy prompts and on-phone-only AI are all in `docs/software-design.md` but weren't in your chart. They're left out so the chart only shows what you asked for.

## Original labels we couldn't read or weren't sure about

The original image is high resolution (16383 × 6083), so every label could be read. These were readable but unclear in meaning, so please check how we interpreted them:

- "important Dates and time **restrained** stuff that may need to be added to schedule": read as time-constrained items. Renamed "important dates and time-bound items that may need scheduling".
- "**toggle use**": read as "turn the mic and camera on". Kept as "toggle use: mic + camera on".
- "**recording before**": read as "go back to recording if it was on before". Turned into the "Was Listen on before the prompt?" decision.
- "**Rpi** receives Schedule": read as the Raspberry Pi receiving any message from the cloud (reminders and answers), not only the schedule.
