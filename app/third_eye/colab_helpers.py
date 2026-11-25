"""
Helpers for running Third Eye in Google Colab.

Colab runs on a Google server, so it can't use your webcam/mic live. Instead it works on a
lecture you upload (audio or video), and you ask questions by typing or through the browser mic.
It reuses the same modules as the laptop version: sync.py, vision.py, assistant.py, study_sheet.py.
"""
import base64
import time
from pathlib import Path

import cv2
import numpy as np

import config
from assistant import Assistant
from sync import NotesWriter, fmt_time
from vision import _small_gray, change_percent, ocr_image

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_models = {}


# ---------------- speech to text ----------------
def _load_model(size: str, use_gpu: bool):
    from faster_whisper import WhisperModel
    key = (size, use_gpu)
    if key not in _models:
        if use_gpu:
            _models[key] = WhisperModel(size, device="cuda", compute_type="float16")
        else:
            _models[key] = WhisperModel(size, device="cpu", compute_type="int8")
    return _models[key]


def _gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def transcribe_file(path: str, writer: NotesWriter, model_size: str = "base.en", use_gpu=None) -> int:
    """Transcribe a whole lecture file into the notes, printing lines as they come. Returns line count."""
    if use_gpu is None:
        use_gpu = _gpu_available()
    for attempt_gpu in ([True, False] if use_gpu else [False]):
        try:
            model = _load_model(model_size, attempt_gpu)
            print(f"Transcribing on {'GPU' if attempt_gpu else 'CPU'} with '{model_size}'...")
            segments, info = model.transcribe(path, language="en", vad_filter=True, beam_size=1)
            total = info.duration or 0
            start_clock, count = time.time(), 0
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                writer.add_speech(seg.start, text)
                count += 1
                pct = f"{100 * seg.end / total:4.0f}%" if total else ""
                print(f"{pct}  {fmt_time(seg.start)}  {text}")
            print(f"\nDone: {count} lines from {fmt_time(total)} of audio "
                  f"in {fmt_time(time.time() - start_clock)}.")
            return count
        except Exception as e:
            if attempt_gpu:
                print(f"(GPU didn't work: {e.__class__.__name__}. Switching to CPU.)")
                with writer._lock:   # throw away any partial GPU lines before retrying
                    writer.entries = [x for x in writer.entries if x[1] != "speech"]
                continue
            raise
    return 0


def transcribe_clip(path: str, model_size: str = "base.en") -> str:
    """Short clip (e.g. a spoken question) -> text."""
    model = _load_model(model_size, False)
    segments, _ = model.transcribe(path, language="en", beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


# ---------------- Third Eye camera: slides ----------------
def extract_slides(video_path: str, writer: NotesWriter, every_sec: float = 1.0) -> int:
    """Find slide/board changes in a lecture video, save snapshots and read their text."""
    if Path(video_path).suffix.lower() not in VIDEO_EXTS:
        print("This is an audio file, so there are no slides to capture. (Upload a video to use the camera feature.)")
        return 0
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Couldn't open the video for slide capture.")
        return 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(fps * every_sec))
    prev, last_saved, stable, saved, idx = None, None, 0, 0, 0
    print("Scanning video for slide changes...")
    while True:
        if idx % step:                      # skip frames quickly without decoding them
            if not cap.grab():
                break
            idx += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        g = _small_gray(frame)
        moving = prev is not None and change_percent(g, prev) > 1.0
        prev = g
        stable = 0 if moving else stable + 1
        changed = last_saved is None or change_percent(g, last_saved) > config.SLIDE_CHANGE_THRESHOLD
        if changed and stable >= 2:
            last_saved = g
            saved += 1
            path = writer.folder / f"slide_{saved:03d}.jpg"
            cv2.imwrite(str(path), frame)
            text = ocr_image(frame)
            writer.add_slide(t, str(path), text)
            print(f"  {fmt_time(t)}  slide {saved}: {text[:70].replace(chr(10), ' / ') or '(no text found)'}")
        idx += 1
    cap.release()
    print(f"Captured {saved} slides.")
    return saved


def add_slide_photos(paths, writer: NotesWriter) -> int:
    """Add photos of slides/whiteboard you took yourself."""
    n = 0
    end_t = writer.entries[-1][0] + 1 if writer.entries else 0
    for p in paths:
        img = cv2.imread(str(p))
        if img is None:
            print(f"  skipped {p} (not an image)")
            continue
        n += 1
        dest = writer.folder / f"photo_{n:03d}.jpg"
        cv2.imwrite(str(dest), img)
        text = ocr_image(img)
        writer.add_slide(end_t, str(dest), text)
        print(f"  {Path(p).name}: {text[:80].replace(chr(10), ' / ') or '(no text found)'}")
    return n


# ---------------- assistant ----------------
def ask(question: str, writer: NotesWriter, speak_answer: bool = True) -> str:
    assistant = Assistant()
    answer = assistant.answer(question, writer.transcript(), writer.slide_text())
    t = writer.entries[-1][0] if writer.entries else 0
    writer.add_qa(t, question, answer)
    print(f"YOU: {question}\nAI:  {answer}")
    if speak_answer:
        say_in_browser(answer)
    return answer


def say_in_browser(text: str):
    """Play the answer as audio in the notebook (needs internet, which Colab has)."""
    try:
        from gtts import gTTS
        from IPython.display import Audio, display
        out = "/content/answer.mp3" if Path("/content").exists() else "answer.mp3"
        gTTS(text).save(out)
        display(Audio(out, autoplay=True))
    except Exception as e:
        print(f"(couldn't play audio: {e})")


RECORD_JS = """
async function recordQuestion(ms) {
  const stream = await navigator.mediaDevices.getUserMedia({audio: true});
  const rec = new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  const stopped = new Promise(res => rec.onstop = res);
  const box = document.createElement('div');
  box.style = 'padding:8px 12px;background:#ffa000;color:#000;border-radius:8px;font-weight:bold;display:inline-block';
  box.textContent = '● Listening... ask your question now';
  document.body.appendChild(box);
  rec.start();
  await new Promise(r => setTimeout(r, ms));
  rec.stop(); await stopped;
  stream.getTracks().forEach(t => t.stop());
  box.remove();
  const buf = new Uint8Array(await new Blob(chunks).arrayBuffer());
  let s = ''; for (let i = 0; i < buf.length; i += 8192) s += String.fromCharCode(...buf.subarray(i, i + 8192));
  return btoa(s);
}
"""


def record_question(seconds: int = 6) -> str:
    """Record from YOUR browser's microphone (Colab only). Returns the saved file path."""
    from google.colab.output import eval_js
    from IPython.display import Javascript, display
    display(Javascript(RECORD_JS))
    b64 = eval_js(f"recordQuestion({int(seconds * 1000)})")
    path = "/content/question.webm"
    Path(path).write_bytes(base64.b64decode(b64))
    return path
