"""
THIRD EYE - AI earpiece prototype (laptop demo)

Run it, and a dashboard opens in your web browser:
  1. Setup screen  - name the course, pick your camera and microphone, check the preview
  2. Recording     - live camera with REC light, live transcript, slides, ask questions
  3. Study sheet   - summary, key terms, self-test, to-dos, calendar reminders

The laptop stands in for the device:
  webcam -> earpiece camera, microphone -> earpiece mic, REC badge -> indicator light,
  speakers -> earpiece speaker, synced cloud folder -> notes on the user's phone.

Examples:
  python main.py
  python main.py --course "BIOL 1010" --camera 1
  python main.py --audio-file lecture.mp3        # demo with a recorded lecture
"""
import argparse
import os
import platform
import queue
import threading
import time
import webbrowser

import cv2

import config
import study_sheet
from assistant import Assistant, speak
from audio_capture import FileAudioSource, LiveMicSource, list_input_devices
from indicator import RecordingIndicator
from sync import NotesWriter, fmt_time
from vision import SlideWatcher

IS_WINDOWS = platform.system() == "Windows"


def camera_backends():
    """Camera drivers to try, best first. Windows has two; some webcams only work with one of them."""
    if IS_WINDOWS:
        return [("DirectShow", cv2.CAP_DSHOW), ("Media Foundation", cv2.CAP_MSMF), ("Auto", cv2.CAP_ANY)]
    if platform.system() == "Darwin":
        return [("AVFoundation", cv2.CAP_AVFOUNDATION), ("Auto", cv2.CAP_ANY)]
    return [("Auto", cv2.CAP_ANY)]


_working_backend = {}   # camera number -> driver that worked last time (tried first next time)


def _try_open(index: int, api, warmup: float):
    cap = cv2.VideoCapture(index, api)
    if not cap.isOpened():
        cap.release()
        return None
    deadline = time.time() + warmup
    while time.time() < deadline:            # webcams can take 1-3 s to wake up
        ok, frame = cap.read()
        if ok and frame is not None and frame.size:
            return cap
        time.sleep(0.1)
    cap.release()
    return None


def open_camera(index: int, warmup: float = 4.0, verbose: bool = False):
    """Open a camera and check it really gives pictures. Returns the capture or None."""
    backends = camera_backends()
    if index in _working_backend:
        backends.sort(key=lambda b: b[1] != _working_backend[index])
    for name, api in backends:
        cap = _try_open(index, api, warmup)
        if cap is None:
            if verbose:
                print(f"[camera] camera {index}: no picture with {name}")
            continue
        # ask for HD; if the camera doesn't like it, reopen at its normal size
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        ok = any(cap.read()[0] for _ in range(10))
        if not ok:
            cap.release()
            cap = _try_open(index, api, warmup)
            if cap is None:
                continue
        _working_backend[index] = api
        if verbose:
            print(f"[camera] camera {index}: working with {name}")
        return cap
    return None


class App:
    def __init__(self, args):
        self.args = args
        self.phase = "setup"                # setup -> recording -> finishing -> done
        self.course = args.course
        self.indicator = RecordingIndicator()
        self.assistant = Assistant()
        self.writer = None
        self.vision = None
        self.files = {}
        self.status = ""
        self.asking = False
        self.ask_until = 0.0
        self.quitting = False
        self.running = False
        self.ended_at = None
        self._stt_lock = threading.Lock()
        self._stt_thread = None

        # speech model loads in the background so the dashboard appears right away
        self.transcriber = None
        self.model_status = "loading"
        threading.Thread(target=self._load_model, daemon=True).start()

        # camera
        self.cam_index = None if args.no_camera else args.camera
        self.camera_ok = False
        self.cameras = []
        self.scanning = False
        self.frame_id = 0
        self._jpeg = None
        self._frame_cond = threading.Condition()
        self._cam_settled = threading.Event()     # set after the preview has tried its camera
        threading.Thread(target=self._camera_loop, daemon=True).start()
        threading.Thread(target=self.scan_cameras, daemon=True).start()

        # microphone
        self.mics = list_input_devices()
        self.mic_index = args.mic
        self.audio_error = ""
        self.source = None
        self._open_audio()

    # ---------------- setup ----------------
    def _load_model(self):
        try:
            from transcriber import Transcriber
            self.transcriber = Transcriber(self.args.model)
            self.model_status = "ready"
        except Exception as e:
            self.model_status = f"error: {e}"
            print(f"[transcriber] {e}")

    def _open_audio(self):
        if self.source is not None:
            try:
                self.source.stop()
            except Exception:
                pass
        self.source, self.audio_error = None, ""
        try:
            if self.args.audio_file:
                self.source = FileAudioSource(self.args.audio_file, play_out_loud=not self.args.mute)
            else:
                self.source = LiveMicSource(self.mic_index)
                self.source.open_paused()
        except Exception as e:
            self.audio_error = str(e)
            print(f"[audio] {e}")

    def set_mic(self, index):
        if self.phase == "setup" and not self.args.audio_file:
            self.mic_index = index
            self._open_audio()

    def set_camera(self, index):
        self.cam_index = index

    def scan_cameras(self):
        """Find which camera numbers work (0 is usually the built-in webcam)."""
        if self.scanning:
            return
        self.scanning = True
        self._cam_settled.wait(timeout=15)   # never open the preview's camera at the same time
        found = []
        for i in range(4):
            if i == self.cam_index:
                if self.camera_ok:
                    found.append(i)      # the preview already has it open; Windows allows one user at a time
                continue
            cap = open_camera(i, warmup=2.5)
            if cap is not None:
                found.append(i)
                cap.release()
        self.cameras = found
        self.scanning = False
        print(f"[camera] cameras found: {found or 'none'}")

    # ---------------- camera thread ----------------
    def _camera_loop(self):
        while not self.quitting:            # if anything goes wrong, report it and keep going
            try:
                self._camera_loop_inner()
            except Exception as e:
                print(f"[camera] error: {e!r}, retrying")
                self.camera_ok = False
                self._cam_settled.set()
                time.sleep(1)

    def _camera_loop_inner(self):
        cap, opened, fails = None, "none", 0
        while not self.quitting:
            want = self.cam_index
            if want != opened:
                if cap is not None:
                    cap.release()
                cap, opened, fails = None, want, 0
                if want is not None:
                    cap = open_camera(want, verbose=True)
                    if cap is None:
                        print(f"[camera] couldn't get a picture from camera {want}")
                self.camera_ok = cap is not None
                self._cam_settled.set()
            if cap is None:
                with self._frame_cond:
                    self._jpeg = None
                time.sleep(0.2)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 40:
                    self.camera_ok = False
                time.sleep(0.05)
                continue
            fails = 0
            self.camera_ok = True

            if self.phase == "recording" and self.vision and not self.source.paused:
                self.vision.process(frame, time.time() - self.source.session_start)
                while not self.vision.results.empty():
                    st, path, text = self.vision.results.get()
                    self.writer.add_slide(st, path, text)
                    print(f"  {fmt_time(st)}  [slide] {text[:60].replace(chr(10), ' ')}")

            h, w = frame.shape[:2]
            if w > 960:
                frame = cv2.resize(frame, (960, int(h * 960 / w)))
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                with self._frame_cond:
                    self._jpeg = jpg.tobytes()
                    self.frame_id += 1
                    self._frame_cond.notify_all()
            time.sleep(0.03)
        if cap is not None:
            cap.release()

    def wait_frame(self, last_id, timeout=1.0):
        with self._frame_cond:
            if self.frame_id == last_id:
                self._frame_cond.wait(timeout)
            return self.frame_id, self._jpeg

    # ---------------- lecture ----------------
    def start(self, course: str):
        if self.phase != "setup" or self.model_status != "ready" or self.source is None:
            return False
        self.course = course.strip() or "Lecture"
        self.writer = NotesWriter(self.course)
        print(f"[notes] saving to: {self.writer.folder.resolve()}")
        self.vision = SlideWatcher(self.writer.folder) if self.cam_index is not None else None
        self.running = True
        self._stt_thread = threading.Thread(target=self._transcribe_loop, daemon=True)
        self._stt_thread.start()
        self.source.begin()
        self.indicator.set("REC")
        self.phase = "recording"
        self.status = ""
        speak("Third Eye is recording.")
        return True

    def _transcribe_loop(self):
        while self.running or not self.source.chunks.empty():
            try:
                t, audio = self.source.chunks.get(timeout=0.3)
            except queue.Empty:
                continue
            with self._stt_lock:
                text = self.transcriber.transcribe(audio)
            if text:
                self.writer.add_speech(t, text)
                print(f"  {fmt_time(t)}  {text}")

    def toggle_pause(self):
        if self.phase != "recording" or self.asking:
            return
        self.source.paused = not self.source.paused
        self.indicator.set("PAUSED" if self.source.paused else "REC")
        self.status = "Paused. Nothing is being recorded." if self.source.paused else ""

    def ask_voice(self):
        if self.phase != "recording" or self.asking:
            return
        threading.Thread(target=self._ask_voice, daemon=True).start()

    def _ask_voice(self):
        self.asking = True
        try:
            file_mode = isinstance(self.source, FileAudioSource)
            was_paused = self.source.paused
            if file_mode:
                self.source.paused = True
            self.indicator.set("ASK")
            self.ask_until = time.time() + config.QUESTION_SECONDS
            self.status = "Listening to your question..."
            audio = self.source.ask_question()
            self.ask_until = 0
            self.indicator.set("PAUSED" if was_paused else "REC")
            if file_mode:
                self.source.paused = was_paused
            self.status = "Thinking..."
            with self._stt_lock:
                question = self.transcriber.transcribe(audio, use_context=False)
            if not question:
                self.status = "Didn't catch that. Try again a bit louder."
                speak("Sorry, I didn't catch that.")
                return
            self._answer(question)
        except Exception as e:
            self.status = f"Assistant error: {e}"
            print(f"[assistant] {e}")
        finally:
            if self.indicator.mode == "ASK":
                self.indicator.set("REC")
            self.ask_until = 0
            self.asking = False

    def ask_text(self, question: str):
        question = question.strip()
        if not question or self.writer is None or self.asking:
            return

        def run():
            self.asking = True
            try:
                self.status = "Thinking..."
                self._answer(question, say=self.phase == "recording")
            except Exception as e:
                self.status = f"Assistant error: {e}"
            finally:
                self.asking = False
        threading.Thread(target=run, daemon=True).start()

    def _answer(self, question, say=True):
        recent = self.writer.transcript(last_seconds=config.CONTEXT_MINUTES * 60) \
            if self.phase == "recording" else self.writer.transcript()
        answer = self.assistant.answer(question, recent, self.writer.slide_text(last_only=True))
        t = time.time() - self.source.session_start if self.phase == "recording" else \
            (self.writer.entries[-1][0] if self.writer.entries else 0)
        self.writer.add_qa(t, question, answer)
        print(f"\n  YOU: {question}\n  AI:  {answer}\n")
        self.status = ""
        if say:
            speak(answer)

    def end(self):
        if self.phase != "recording":
            return
        self.phase = "finishing"
        self.ended_at = time.time()
        threading.Thread(target=self._finish, daemon=True).start()

    def _finish(self):
        print("\n[ending lecture] finishing transcription...")
        self.indicator.set("OFF")
        try:
            self.source.stop()
        except Exception:
            pass
        self.running = False
        if self._stt_thread:
            self._stt_thread.join()
        if self.vision:
            time.sleep(1.0)
            while not self.vision.results.empty():
                st, path, text = self.vision.results.get()
                self.writer.add_slide(st, path, text)
        self.status = "Building your study sheet..."
        print("[study sheet] building...")
        try:
            self.files = study_sheet.generate(self.writer)
        except Exception as e:
            print(f"[study sheet] error: {e}")
            self.files = {}
        self.status = ""
        self.phase = "done"
        print(f"\n=== Done! Files are in: {self.writer.folder.resolve()} ===")
        speak("Lecture saved. Your study sheet and reminders are ready.")

    def new_lecture(self):
        if self.phase != "done":
            return
        self.writer, self.vision, self.files, self.ended_at = None, None, {}, None
        self._open_audio()
        self.phase = "setup"

    def quit(self):
        self.quitting = True
        self.indicator.set("OFF")
        try:
            if self.source:
                self.source.stop()
        except Exception:
            pass

    # ---------------- dashboard state ----------------
    def elapsed(self):
        if self.phase in ("recording", "finishing", "done") and self.source:
            return (self.ended_at or time.time()) - self.source.session_start
        return 0

    def state(self, since_version: int):
        s = {
            "phase": self.phase, "mode": self.indicator.mode, "course": self.course,
            "elapsed": fmt_time(self.elapsed()), "model": self.model_status,
            "ai": self.assistant.provider or "offline",
            "status": self.status, "asking": self.asking,
            "ask_remaining": max(0.0, self.ask_until - time.time()),
            "camera": {"index": self.cam_index, "ok": self.camera_ok, "list": self.cameras,
                       "scanning": self.scanning},
            "mic": {"index": self.mic_index, "list": self.mics, "error": self.audio_error,
                    "level": round(self.source.level, 3) if self.source else 0,
                    "file": os.path.basename(self.args.audio_file) if self.args.audio_file else None},
            "paused": bool(self.source and self.source.paused),
            "slides": self.vision.count if self.vision else 0,
        }
        if self.writer:
            s["version"] = self.writer.version
            s["folder"] = str(self.writer.folder.resolve())
            if self.writer.version != since_version:
                s["entries"] = self.writer.structured()
        if self.phase == "done":
            s["files"] = {k: v.name for k, v in self.files.items()}
            sheet_json = self.writer.folder / "study_sheet.json"
            if sheet_json.exists():
                import json
                s["sheet"] = json.loads(sheet_json.read_text(encoding="utf-8"))
                s["reviews"] = [time.strftime("%a %b %d", time.localtime(time.time() + d * 86400))
                                for d in config.REVIEW_DAYS]
        return s


def main():
    p = argparse.ArgumentParser(description="Third Eye earpiece prototype (laptop demo)")
    p.add_argument("--course", default="", help='course name, e.g. "PSYC 1001" (you can also type it in the app)')
    p.add_argument("--audio-file", help="use a recorded lecture (mp3/wav/m4a/mp4) instead of the mic")
    p.add_argument("--mute", action="store_true", help="don't play the recorded lecture out loud")
    p.add_argument("--no-camera", action="store_true")
    p.add_argument("--camera", type=int, default=config.CAMERA_INDEX)
    p.add_argument("--mic", type=int, default=None, help="microphone device number")
    p.add_argument("--model", default=config.WHISPER_MODEL, help="whisper model: tiny.en / base.en / small.en")
    p.add_argument("--port", type=int, default=config.DASHBOARD_PORT)
    p.add_argument("--no-browser", action="store_true", help="don't open the dashboard automatically")
    args = p.parse_args()

    app = App(args)
    from ui_server import serve
    serve(app, args.port)
    url = f"http://localhost:{args.port}"
    print("\n=================================================")
    print(f"  Dashboard:  {url}")
    print("  Press Ctrl+C here to quit.")
    print("=================================================\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        while not app.quitting:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    app.quit()
    time.sleep(0.5)
    os._exit(0)


if __name__ == "__main__":
    main()
