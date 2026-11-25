"""
Camera -> slide / whiteboard snapshots + OCR text  (the Third Eye camera).

Idea: compare each frame to the last saved slide. When the view changes a lot (new slide,
new whiteboard writing) AND then holds still for a moment, save a snapshot and read its text.
"""
import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import config

try:
    import pytesseract
    pytesseract.get_tesseract_version()   # checks the Tesseract program is installed too
    _OCR = "tesseract"
except Exception:
    try:
        import easyocr  # type: ignore
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        _OCR = "easyocr"
    except Exception:
        _OCR = None


def ocr_image(img) -> str:
    if _OCR == "tesseract":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
        text = pytesseract.image_to_string(gray)
    elif _OCR == "easyocr":
        text = "\n".join(_reader.readtext(img, detail=0))
    else:
        return ""
    # keep lines that look like real words, drop OCR noise
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 3 and sum(c.isalpha() for c in ln) >= 0.5 * len(ln)]
    return "\n".join(lines)


def change_percent(a, b) -> float:
    """% of pixels that clearly changed between two small gray frames.
    Works better than an average difference for slides, where only the text changes."""
    return 100.0 * float(np.mean(cv2.absdiff(a, b) > 30))


def _small_gray(frame):
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (160, 90))
    return cv2.GaussianBlur(g, (5, 5), 0)


class SlideWatcher:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.results: "queue.Queue[tuple[float, str, str]]" = queue.Queue()  # (t, image_path, text)
        self._last_saved = None
        self._prev = None
        self._stable = 0
        self._last_time = -1e9
        self.count = 0
        if _OCR is None:
            print("[vision] no OCR engine found - slides will be saved as images without text. "
                  "Install Tesseract to read slide text.")
        else:
            print(f"[vision] OCR ready ({_OCR})")

    def process(self, frame, t: float):
        """Call once per camera frame. t = seconds since the lecture started."""
        g = _small_gray(frame)
        if self._prev is None:
            self._prev = g
            self._last_saved = None
        moving = change_percent(g, self._prev) > 1.0   # camera/scene still moving?
        self._prev = g
        self._stable = 0 if moving else self._stable + 1

        changed = self._last_saved is None or \
            change_percent(g, self._last_saved) > config.SLIDE_CHANGE_THRESHOLD
        if changed and self._stable >= config.SLIDE_STABLE_FRAMES and \
                time.time() - self._last_time >= config.MIN_SECONDS_BETWEEN_SLIDES:
            self._last_saved = g
            self._last_time = time.time()
            self.count += 1
            path = self.out_dir / f"slide_{self.count:03d}.jpg"
            cv2.imwrite(str(path), frame)
            # OCR is slow, so do it in the background so the video never freezes
            threading.Thread(target=self._ocr, args=(frame.copy(), t, str(path)), daemon=True).start()

    def _ocr(self, frame, t, path):
        self.results.put((t, path, ocr_image(frame)))
