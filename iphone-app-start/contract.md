---
cursor:
  subagentId: "bc-928c7bf7-1104-5eb6-bea7-8a6333ad3bb2"
---

# Third Eye for iPhone: build contract

A static web app for iPhone Safari that does what the laptop app (`third_eye.zip`) does, using the phone's mic and camera. Plain HTML, CSS and ES modules. No build step, no server, no npm at runtime. It must run from any static HTTPS host (GitHub Pages) under a sub-path, so **every URL is relative** (`./js/app.js`, never `/js/app.js`).

Final location: `/cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/app/third_eye_iphone/` (the coordinator assembles it). Workers write only to `internal/iphone-app-work/<their-name>/`, laid out as if that folder were the app root (so `capture/js/capture.js` lands at `app/third_eye_iphone/js/capture.js`).

Source to port, unzipped at `/tmp/src/third_eye/` (re-unzip from `internal/uploads/third_eye.zip` if missing). Writing rules: `internal/third-eye-work/brief.md` ("Plain writing" and "Dashboard" sections apply to code, comments and UI copy).

## Folder layout and owners

```
index.html               ui
manifest.webmanifest     ui
sw.js                    ui      (cache-first app shell, lists every file below)
icons/                   ui      (180, 192, 512 PNG + apple-touch-icon)
css/app.css              ui
js/app.js                ui      controller: the laptop's main.py App class
js/ui.js                 ui      renders state, wires buttons
js/settings.js           ui      settings screen + load/save (see Settings)
js/bus.js                ui      tiny event emitter (spec below; write it first, others import it)
js/util.js               ui      fmtTime, shortTime (ports of sync.py), escapeHtml, uid
js/capture.js            capture mic + camera, PCM chunks, level, ask-question recording, wake lock, interruptions
js/buffer.js             capture rolling 30 s clip buffer
js/slides.js             capture SlideWatcher port (change detection only; OCR is ai's)
js/notes.js              capture NotesWriter port, in memory + persisted
js/db.js                 capture IndexedDB wrapper
js/export.js             capture share/download lecture files (Web Share API, zip)
js/ai.js                 ai      callClaude, callGemini, callOpenAI, callAi (ports of assistant.py)
js/transcribe.js         ai      speech to text engines
js/ocr.js                ai      slide text (Tesseract.js, or Gemini/Claude vision)
js/assistant.js          ai      Assistant.answer, offlineAnswer, speak
js/studysheet.js         ai      generate(), aiSheet, offlineSheet, toMarkdown, toIcs, toDocx
vendor/tesseract/        ai      vendored Tesseract.js v5 (worker, core wasm, eng.traineddata.gz)
```

## Shared conventions

- ES modules, `export` named functions/classes. No frameworks. camelCase in JS (ports of snake_case names keep the same words: `add_speech` -> `addSpeech`).
- Times: `t` is seconds since the lecture started (float), exactly as the laptop.
- Console log prefix like the laptop: `console.log('[capture] ...')`.
- Never hardcode an API key. Read keys from `getSettings()` only.
- Any feature that Safari can't do must fail soft: emit a `notice` event with a plain message and keep the rest working.

### bus.js

```js
export const bus = { on(name, fn), off(name, fn), emit(name, data) }
```

Events (name: payload):

| Event | Payload | Emitted by |
|---|---|---|
| `level` | `{ level }` 0..1 | capture, ~10/s |
| `chunk` | `{ t, pcm: Float32Array (16 kHz mono), blob?: Blob }` every `chunkSeconds` | capture |
| `frame` | `{ t, canvas }` ~5/s while recording | capture -> slides |
| `slide` | `{ t, n, blob: Blob (image/jpeg), dataUrl }` | slides |
| `speech` | `{ t, text }` live text from an engine | transcribe |
| `entries` | `{ version }` notes changed | notes |
| `clip` | `{ id, t, seconds }` a clip was saved | buffer |
| `interrupted` | `{ reason: 'hidden'|'ended'|'audio-interrupted', t }` | capture |
| `resumed` | `{ t }` | capture |
| `notice` | `{ level: 'info'|'warn'|'error', text }` | anyone -> ui |
| `status` | `{ text }` same as laptop `self.status` | app |

### Settings (settings.js, localStorage key `thirdeye.settings`)

```js
export const DEFAULTS = {
  course: '',
  anthropicKey: '', aiModel: 'claude-sonnet-5-5',
  geminiKey: '', geminiModel: '',
  openaiKey: '',
  sttEngine: 'auto',        // 'auto' | 'safari' | 'gemini' | 'openai'
  ocrEngine: 'auto',        // 'auto' | 'tesseract' | 'ai' | 'off'
  camera: 'environment',    // 'environment' | 'user' | 'off'
  speakAnswers: true,
  chunkSeconds: 8, questionSeconds: 6, silenceRms: 0.004,
  slideChangeThreshold: 3, slideStableFrames: 15, minSecondsBetweenSlides: 5,
  clipSeconds: 30,
  contextMinutes: 5, reviewDays: [1, 3, 7], reminderHour: 18,
}
export function getSettings()            // DEFAULTS merged with saved
export function saveSettings(partial)
export function aiProvider()             // 'Claude' | 'Gemini' | '' — same rule as config.ai_provider()
```

Keys stay on the phone (localStorage). The settings screen says so and has a "Forget keys" button.

## Module interfaces

### capture.js (port of audio_capture.py + the camera half of main.py)

```js
export class Capture {
  async open({ camera })      // getUserMedia; must be called from a user tap. Starts level meter, preview. Paused (meter only), like open_paused().
  get videoEl()               // <video playsinline muted> showing the camera, for the UI to place
  begin()                     // start lecture clock: sessionStart = now, paused=false, chunks start flowing
  paused                      // boolean, settable (toggle_pause)
  level                       // 0..1, rule: max(min(1, rms*12), level*0.8)
  sessionStart                // ms timestamp
  elapsed()                   // seconds since begin, excluding nothing (same as laptop)
  async askQuestion(seconds)  // returns Float32Array 16 kHz of the user's voice; lecture audio is not chunked meanwhile
  async switchCamera(facing)  // 'environment' | 'user' | 'off'
  stop()                      // flush last partial chunk, stop tracks
  snapshot()                  // HTMLCanvasElement of the current frame (full size)
}
export function pcmToWav(float32, sampleRate = 16000) // Blob audio/wav
```

- Resample to 16 kHz mono in JS (AudioContext runs at 44.1/48 kHz on iPhone). Use an AudioWorklet if available, ScriptProcessor as fallback.
- AudioContext must be created/resumed inside a tap handler (iOS rule).
- Silence check is the transcriber's job (as in the laptop), capture always emits chunks.
- Wake Lock (`navigator.wakeLock.request('screen')`) while recording; re-request on `visibilitychange`.
- When the page is hidden or the screen locks, iOS stops the mic and camera. Emit `interrupted`, write nothing, and on return re-acquire tracks if they ended and emit `resumed`. The app records the gap with `notes.addGap(t0, t1)`.

### buffer.js (the earpiece's 30 s rolling buffer, see docs/software-design.md)

```js
export class RollingBuffer {
  constructor(capture, seconds = 30)
  start(); stop()
  async saveClip(lectureId)   // keeps the last `seconds` of audio+video, stores in IndexedDB, emits 'clip', returns clip record
}
```

Suggested approach: restart a `MediaRecorder` on the camera+mic stream every 5 s so every segment is a standalone file (Safari records `video/mp4`), keep segments covering the last `seconds`, and on save store them in order. Fallback when MediaRecorder or video is unavailable: keep a PCM ring buffer and save a WAV plus the latest JPEG frames. Clip record: `{ id, lectureId, t, seconds, mime, parts: [Blob, ...] }`.

### slides.js (port of vision.py SlideWatcher, no OCR)

```js
export class SlideWatcher {
  constructor(settings)       // thresholds from settings
  process(canvas, t)          // per frame. 160x90 gray, 5x5 blur, changePercent = % pixels with |diff|>30
  count
}
export function changePercent(a, b)  // a,b Uint8ClampedArray gray 160x90
```

Same logic as the laptop: moving if change vs previous > 1%; save when changed vs last saved > threshold AND stable >= stableFrames AND >= minSeconds since last. Emits `slide` with a JPEG blob. Note: the laptop processes ~30 fps; at 5 fps scale `slideStableFrames` down (`Math.ceil(15 * 5/30)` = 3) and say so in a comment.

### notes.js (port of sync.py NotesWriter)

```js
export class NotesWriter {
  static async create(course)          // new lecture; id like '2026-11-25_1341_BIOL_1010' (same rule as laptop folder name)
  static async load(id)
  id, course, started (Date), entries, version
  addSpeech(t, text); addSlide(t, imageKey, text); addQa(t, question, answer); addGap(t0, t1)
  setSlideText(n, text)                // OCR result arrives later
  structured()                         // [{t, kind:'speech', text} | {t, kind:'slide', img, text} | {t, kind:'qa', q, a} | {t, kind:'gap', t1}]
  transcript(lastSeconds?)             // same as laptop
  slideText(lastOnly?)
  timedTranscript()
  renderMarkdown()                     // live_notes.md, same layout as laptop _render_md
  async saveFile(name, blob)           // study_sheet.md etc.
  async listFiles()                    // [{name, size}]
}
export async function listLectures()   // newest first: {id, course, started, entryCount, hasSheet}
export async function deleteLecture(id)
```

Entries are kept in time order (transcription can lag). Every change bumps `version`, emits `entries`, and is saved to IndexedDB (debounced <= 1 s) so a reload or crash loses at most a second.

### db.js

IndexedDB `thirdeye`, version 1, stores: `lectures` (key `id`: `{id, course, started, entries, sheet}`), `blobs` (key `"<lectureId>/<name>"`: Blob; slide images `slide_001.jpg`, files `study_sheet.md`, `reminders.ics`, `study_sheet.docx`, `study_sheet.json`, `live_notes.md`), `clips` (key `id`). Call `navigator.storage.persist()` once.

### export.js

```js
export async function shareFiles(lectureId, names?)  // navigator.share({files}) if canShare, else download links
export async function downloadZip(lectureId)         // store-only zip of every file for that lecture, no library
export function downloadBlob(name, blob)
```

### ai.js (port of assistant.py network calls)

```js
export async function callClaude(system, user, maxTokens = 600)   // fetch https://api.anthropic.com/v1/messages with header 'anthropic-dangerous-direct-browser-access': 'true'
export async function callGemini(system, user, maxTokens = 600, fast = false, extraParts = [])  // same model fallback lists and retry rules as the laptop
export async function callAi(system, user, maxTokens = 600, fast = false)  // Claude first, then Gemini, else throws 'no AI key set'
```

### transcribe.js

```js
export class Transcriber {
  constructor(settings)        // picks engine: 'auto' = gemini if geminiKey, else openai if openaiKey, else safari
  engine                       // name shown in the UI
  status                       // 'ready' | 'loading' | 'error: ...'
  async transcribe(pcm, useContext = true)  // Float32Array 16 kHz -> text. Skips silence (rms < silenceRms). Keeps last text as context prompt.
  startLive(onText); stopLive()             // only for the 'safari' engine (webkitSpeechRecognition, continuous), which can't take PCM
}
```

Engines: Gemini (audio inline as WAV base64, free tier), OpenAI `whisper-1` / `gpt-4o-mini-transcribe` (multipart), Safari `webkitSpeechRecognition` (no key; text arrives live, app timestamps it with `capture.elapsed()`). For the question recording with the safari engine, run a short recognition session instead of PCM.

### ocr.js

```js
export async function ocrImage(blobOrCanvas, settings)  // -> text, with the laptop's line filter (len>=3, >=50% letters)
export function ocrEngineName(settings)
```

Tesseract.js loaded lazily from `./vendor/tesseract/` (works offline after first load). 'ai' engine sends the JPEG to Gemini/Claude vision.

### assistant.js

```js
export class Assistant { provider; online; async answer(question, recentTranscript, slideText) }  // same SYSTEM prompt, max 200 tokens, fast
export function offlineAnswer(question, transcript)
export function keywords(text); export const STOPWORDS
export function speak(text)   // speechSynthesis; iOS needs one utterance spoken inside a tap first (call speak('') in the Start handler)
```

### studysheet.js

```js
export async function generate(notes, settings)  // returns sheet object; saves study_sheet.md, reminders.ics, study_sheet.docx, study_sheet.json via notes.saveFile
export function offlineSheet(course, transcript, slides)
export function toMarkdown(sheet, course, date, reviewDays)
export function toIcs(sheet, course, date, settings)
export async function toDocx(sheet, course, date)   // minimal WordprocessingML in a store-only zip; return null if it fails
```

Sheet JSON keys exactly as the laptop: `title, tldr, key_points, key_terms[{term,definition}], exam_questions, todos[{task,due_in_days}], confusing_parts, _note`.

## App state (app.js -> ui.js)

`app.state()` returns the same shape as the laptop `/state`, adapted:

```js
{ phase: 'setup'|'recording'|'finishing'|'done', mode: 'OFF'|'REC'|'ASK'|'PAUSED',
  course, elapsed: '00:12:31', model: transcriber.status, stt: transcriber.engine, ai: provider || 'offline',
  status, asking, askRemaining, camera: {facing, ok}, mic: {ok, level, error},
  paused, slides, version, entries, files, sheet, reviews, interrupted: bool }
```

Plus a `lectures` view (past lectures on this phone, open one to see its notes, sheet and files) and a `settings` view.

## Feature map (laptop -> iPhone)

| Laptop | iPhone |
|---|---|
| sounddevice mic | getUserMedia audio, AudioWorklet resample to 16 kHz |
| OpenCV webcam, camera list | getUserMedia video, back/front camera switch |
| --audio-file demo mode | "Use a recording" file picker: decode with AudioContext.decodeAudioData and feed it as chunks in real time |
| faster-whisper offline | Gemini or OpenAI transcription with a key, Safari speech recognition without |
| Tesseract OCR | Tesseract.js (vendored), or AI vision |
| Claude / Gemini assistant | same APIs called from the browser |
| OS text to speech | speechSynthesis |
| REC light / GPIO LED | eye icon and red bar, same modes |
| live_notes.md in sync folder | IndexedDB + Share to Files/iCloud Drive |
| study_sheet.md/.docx/.ics/.json | same four files, generated in the browser |
| 30 s rolling buffer (earpiece design) | RollingBuffer, "Save last 30 s" button |
| dashboard at localhost:8000 | the app itself |
