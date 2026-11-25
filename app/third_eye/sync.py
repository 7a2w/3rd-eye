"""
Saves the lecture notes.

Writes the live notes as a Markdown file into SYNC_FOLDER. Point that folder at Google Drive,
Dropbox, OneDrive or iCloud Drive and the notes, slide pictures and study sheet appear on your phone.
"""
import threading
from datetime import datetime
from pathlib import Path

import config


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def short_time(seconds: float) -> str:
    """0:07, 12:31, 1:02:09 (how times read on the dashboard and phone)."""
    seconds = int(seconds)
    h, m, sec = seconds // 3600, seconds % 3600 // 60, seconds % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class NotesWriter:
    def __init__(self, course: str, sync_folder: Path = config.SYNC_FOLDER):
        self.started = datetime.now()
        stamp = self.started.strftime("%Y-%m-%d_%H%M")
        safe_course = "".join(c if c.isalnum() or c in "-_ " else "_" for c in course).strip() or "Lecture"
        self.folder = Path(sync_folder).expanduser() / f"{stamp}_{safe_course.replace(' ', '_')}"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.course = course
        self.notes_path = self.folder / "live_notes.md"
        self.entries = []          # (seconds, kind, text)  kind = "speech" | "slide" | "qa"
        self._lock = threading.Lock()
        self.version = 0           # goes up on every change, so the dashboard knows when to refresh
        self._write()

    # ----- adding content -----
    def add_speech(self, t: float, text: str):
        self._add(t, "speech", text)

    def add_slide(self, t: float, image_path: str, text: str):
        rel = Path(image_path).name
        self._add(t, "slide", f"![slide]({rel})\n\n" + (f"> " + text.replace("\n", "\n> ") if text else ""))

    def add_qa(self, t: float, question: str, answer: str):
        self._add(t, "qa", f"**You asked:** {question}\n\n**Assistant:** {answer}")

    def add_insight(self, t: float, about: str, text: str):
        self._add(t, "insight", f"**{about}:** {text}" if about else text)

    def add_task(self, t: float, task: str, due=None):
        self._add(t, "task", task + (f" (due {due})" if due else ""))

    def add_context(self, t: float, context: str, topic: str = ""):
        self._add(t, "context", context + (f": {topic}" if topic else ""))

    def _add(self, t, kind, text):
        with self._lock:
            self.entries.append((t, kind, text))
            self.entries.sort(key=lambda e: e[0])   # transcription can lag, so keep time order
            self.version += 1
            self._write()

    def structured(self):
        """Entries as simple dicts for the dashboard."""
        with self._lock:
            entries = list(self.entries)
        out = []
        for t, kind, text in entries:
            if kind == "speech":
                out.append({"t": t, "kind": kind, "text": text})
            elif kind == "slide":
                img = text.split("](", 1)[1].split(")", 1)[0] if "](" in text else ""
                words = text.split("\n\n", 1)[1].replace("> ", "") if "\n\n" in text else ""
                out.append({"t": t, "kind": kind, "img": img, "text": words})
            elif kind == "insight":
                about, sep, said = text.partition(":** ")
                out.append({"t": t, "kind": kind, "q": about.strip("*") if sep else "", "a": said if sep else text})
            elif kind == "task":
                task, sep, due = text.rpartition(" (due ")
                out.append({"t": t, "kind": kind, "text": task if sep else text, "due": due.rstrip(")") if sep else None})
            elif kind == "context":
                ctx, _, topic = text.partition(": ")
                out.append({"t": t, "kind": kind, "text": ctx, "topic": topic})
            else:
                q, _, a = text.partition("\n\n")
                out.append({"t": t, "kind": kind, "q": q.replace("**You asked:** ", ""),
                            "a": a.replace("**Assistant:** ", "")})
        return out

    # ----- reading content back -----
    def transcript(self, last_seconds: float = None) -> str:
        with self._lock:
            entries = list(self.entries)
        if last_seconds is not None and entries:
            cutoff = entries[-1][0] - last_seconds
            entries = [e for e in entries if e[0] >= cutoff]
        return " ".join(text for _, kind, text in entries if kind == "speech")

    def slide_text(self, last_only: bool = False) -> str:
        with self._lock:
            slides = [text for _, kind, text in self.entries if kind == "slide"]
        if last_only:
            slides = slides[-1:]
        return "\n".join(s.split("\n\n", 1)[-1].replace("> ", "") for s in slides)

    def timed_transcript(self) -> str:
        with self._lock:
            return "\n".join(f"[{fmt_time(t)}] {text}" for t, kind, text in self.entries if kind == "speech")

    # ----- file output -----
    def _render_md(self) -> str:
        out = [f"# {self.course} - live notes",
               f"*Started {self.started.strftime('%A %B %d, %Y at %I:%M %p')}*", ""]
        for t, kind, text in self.entries:
            if kind == "speech":
                out.append(f"`{fmt_time(t)}` {text}  ")
            elif kind == "slide":
                out += ["", f"### Slide captured at {fmt_time(t)}", text, ""]
            elif kind == "insight":
                out += ["", f"> `{fmt_time(t)}` Third Eye: {text}", ""]
            elif kind == "task":
                out.append(f"`{fmt_time(t)}` **Task:** {text}  ")
            elif kind == "context":
                out += ["", f"## {text.capitalize()} ({fmt_time(t)})", ""]
            else:
                out += ["", f"#### Question at {fmt_time(t)}", text, ""]
        return "\n".join(out) + "\n"

    def _write(self):
        tmp = self.notes_path.with_suffix(".tmp")
        tmp.write_text(self._render_md(), encoding="utf-8")
        tmp.replace(self.notes_path)   # atomic, so cloud sync never grabs a half-written file
