"""
The assistant's background thinking. While Third Eye listens, this:
  - works out what is going on (lecture, meeting, conversation, studying...) and the topic
  - pulls out tasks, deadlines and events and keeps a live reminders.ics
  - explains things in your ear when it hears a question or a term you may not know
  - answers when you say "Hey Third Eye, ..."
  - ends the session by itself after a long silence

With an AI key (Gemini free tier or Claude) it uses the AI. Without one it falls back to simple rules.
"""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta

import config
from assistant import call_ai, speak

WAKE = re.compile(r"\b(?:hey|hi|ok|okay|yo)?[\s,]*(?:third|3rd)[\s-]?(?:eye|i|ai)\b[\s,.:!?-]*(.*)", re.I)

CONTEXT_WORDS = {
    "lecture": "professor class lecture chapter exam midterm quiz slide homework students textbook syllabus "
               "today we're going to cover equation theory".split(),
    "meeting": "agenda meeting action item items deadline project team client sprint quarter budget "
               "stakeholder deliverable roadmap update sync standup".split(),
    "studying": "flashcard practice problem review notes studying memorize answer solution".split(),
    "phone call": "hello calling call hear speaking bye phone".split(),
    "media": "subscribe episode channel video watch season trailer".split(),
}

TASK_HINT = re.compile(
    r"\b(due|homework|assignment|problem set|quiz|exam|midterm|deadline|submit|hand in|turn in|read(ing)? chapter|"
    r"remind me|don't forget|do not forget|remember to|i need to|i have to|we need to|we have to|you need to|"
    r"make sure|appointment|meeting (on|at)|call (him|her|them|back)|email|send|book|schedule|pick up|buy)\b", re.I)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

THINK_PROMPT = """You are the background mind of Third Eye, an AI earpiece. It hears everything around the user
and must work out on its own what is happening and what the user would want done, without being asked.

Now: {now}
What you decided last time: context={context!r}, topic={topic!r}
Tasks already noted (do not repeat): {known}

EARLIER (for context):
{earlier}

NEW SINCE LAST TIME:
{new}

Return ONLY JSON:
{{
 "context": "one of: lecture, meeting, conversation, studying, phone call, media, quiet, other",
 "topic": "short topic, 2-6 words",
 "title": "short name for this session, e.g. 'BIOL 1010: cellular respiration' or 'Team sync with Sam'",
 "tasks": [{{"task": "clear action for the user", "kind": "task|deadline|event", "due": "YYYY-MM-DD HH:MM or YYYY-MM-DD or null"}}],
 "explain": [{{"about": "the question or term", "say": "1-2 short spoken sentences"}}]
}}
Rules:
- Infer. Resolve relative dates ("next Friday", "in two weeks", "tomorrow at 3") against Now.
- tasks: only real things the user should do or attend, from the NEW text. [] if none.
- explain: only when the NEW text has a question nobody answered, or a technical term a student or
  newcomer would likely not know. At most 1 item, and [] most of the time. Never explain small talk."""


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def guess_due(sentence: str, now: datetime):
    s = sentence.lower()
    if "two weeks" in s:
        return (now + timedelta(days=14)).replace(hour=9, minute=0)
    if "next week" in s:
        return (now + timedelta(days=7)).replace(hour=9, minute=0)
    if "tomorrow" in s:
        return (now + timedelta(days=1)).replace(hour=9, minute=0)
    if "next class" in s or "next lecture" in s:
        return (now + timedelta(days=2)).replace(hour=9, minute=0)
    for i, day in enumerate(WEEKDAYS):
        if day in s:
            ahead = (i - now.weekday()) % 7 or 7
            return (now + timedelta(days=ahead)).replace(hour=9, minute=0)
    if "tonight" in s or "today" in s:
        return now.replace(hour=20, minute=0)
    return None


def offline_context(text: str):
    words = re.findall(r"[a-z']+", text.lower())
    scores = {c: sum(words.count(w) for w in ws) for c, ws in CONTEXT_WORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return "conversation" if len(words) > 30 else "quiet"


def offline_topic(text: str):
    from assistant import keywords
    freq = {}
    for w in keywords(text):
        if len(w) > 4:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=freq.get, reverse=True)[:3]
    return " ".join(top)


class Brain:
    def __init__(self, app):
        self.app = app
        self.context = "listening"
        self.topic = ""
        self.title = ""
        self.tasks = []              # {"id","task","kind","due","t","done"}
        self.thinking = False
        self.last_think = 0.0
        self.last_speech = time.time()
        self._done_upto = 0          # how many speech entries have been thought about
        self._last_spoken = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ---------- lifecycle ----------
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(2):
            app = self.app
            if app.phase != "recording" or app.source.paused:
                continue
            if time.time() - self.last_think >= config.THINK_SECONDS:
                self.think()
            silent_min = (time.time() - self.last_speech) / 60
            if config.AUTO_END_MINUTES and silent_min >= config.AUTO_END_MINUTES and self._speech_entries():
                print(f"[brain] {config.AUTO_END_MINUTES} minutes of quiet, wrapping up this session")
                app.end(auto=True)
                return

    # ---------- hearing ----------
    def on_speech(self, t, text):
        """Called for every new line of transcript. Handles the wake word."""
        self.last_speech = time.time()
        m = WAKE.search(text)
        if not m:
            return
        question = m.group(1).strip()
        if len(question.split()) >= 2:
            print(f"[brain] wake word, question: {question}")
            self.app.ask_text(question, spoken=True)
        else:
            print("[brain] wake word, listening for the question")
            speak("Yes?")
            time.sleep(0.6)
            self.app.ask_voice()

    def _speech_entries(self):
        return [e for e in self.app.writer.structured() if e["kind"] == "speech"]

    # ---------- thinking ----------
    def think(self, final=False):
        if self.thinking:
            return
        speech = self._speech_entries()
        new = speech[self._done_upto:]
        new_text = " ".join(e["text"] for e in new)
        if not final and len(new_text.split()) < config.THINK_MIN_WORDS:
            self.last_think = time.time()
            return
        if not new:
            return
        self.thinking = True
        self.last_think = time.time()
        upto = len(speech)
        try:
            earlier = " ".join(e["text"] for e in speech[max(0, self._done_upto - 20):self._done_upto])
            result = None
            if config.ai_provider():
                try:
                    result = self._ai_think(earlier, new_text)
                except Exception as e:
                    print(f"[brain] AI failed, using simple rules: {e}")
            if result is None:
                result = self._offline_think(" ".join(e["text"] for e in speech[-40:]), new)
            self._apply(result, new[-1]["t"], final)
            self._done_upto = upto
        finally:
            self.thinking = False

    def _ai_think(self, earlier, new_text):
        with self._lock:
            known = [t["task"] for t in self.tasks][-15:]
        prompt = THINK_PROMPT.format(now=datetime.now().strftime("%A %Y-%m-%d %H:%M"), context=self.context,
                                     topic=self.topic, known=json.dumps(known), earlier=earlier[-4000:] or "(none)",
                                     new=new_text[-6000:])
        raw = call_ai("You infer context and tasks from overheard speech. Output JSON only.", prompt,
                      max_tokens=700, fast=True)
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0) if m else raw)

    def _offline_think(self, recent_text, new_entries):
        now = datetime.now()
        tasks = []
        for e in new_entries:
            for s in re.split(r"(?<=[.!?])\s+", e["text"]):
                if TASK_HINT.search(s) and len(s.split()) >= 4 and not WAKE.search(s):
                    due = guess_due(s, now)
                    kind = "deadline" if re.search(r"\b(due|deadline|submit|exam|quiz|midterm)\b", s, re.I) else "task"
                    tasks.append({"task": s.strip(), "kind": kind, "due": due.strftime("%Y-%m-%d %H:%M") if due else None})
        context = offline_context(recent_text)
        topic = offline_topic(recent_text)
        return {"context": context, "topic": topic, "title": "", "tasks": tasks, "explain": []}

    def _apply(self, r, t, final):
        w = self.app.writer
        ctx = (r.get("context") or "").strip().lower() or self.context
        if ctx != self.context and ctx not in ("quiet",):
            if self.context != "listening":
                print(f"[brain] context changed: {self.context} -> {ctx}")
            w.add_context(t, ctx, r.get("topic") or "")
        if ctx != "quiet":
            self.context = ctx
        self.topic = (r.get("topic") or self.topic or "").strip()
        title = (r.get("title") or "").strip()
        if title and not self.app.course_given:
            self.title = title
            w.course = title
        added = []
        with self._lock:
            seen = {_norm(x["task"]) for x in self.tasks}
            for x in r.get("tasks") or []:
                task = (x.get("task") or "").strip()
                if not task or _norm(task) in seen:
                    continue
                seen.add(_norm(task))
                item = {"id": uuid.uuid4().hex[:8], "task": task, "kind": x.get("kind") or "task",
                        "due": x.get("due"), "t": t, "done": False}
                self.tasks.append(item)
                added.append(item)
        for item in added:
            print(f"[brain] noted {item['kind']}: {item['task']} (due {item['due'] or '?'})")
            w.add_task(item["t"], item["task"], item["due"])
        if added:
            self.write_files()
        for x in (r.get("explain") or [])[:1]:
            say = (x.get("say") or "").strip()
            if not say:
                continue
            w.add_insight(t, x.get("about") or "", say)
            print(f"[brain] explaining: {say}")
            if config.AUTO_SPEAK and not final and time.time() - self._last_spoken > config.AUTO_SPEAK_GAP:
                self._last_spoken = time.time()
                speak(say)
        if added and not final and config.AUTO_SPEAK and time.time() - self._last_spoken > config.AUTO_SPEAK_GAP:
            self._last_spoken = time.time()
            speak("Noted: " + added[0]["task"][:120])

    # ---------- tasks ----------
    def set_done(self, task_id, done=True):
        with self._lock:
            for x in self.tasks:
                if x["id"] == task_id:
                    x["done"] = bool(done)
        self.write_files()

    def task_list(self):
        with self._lock:
            return [dict(x) for x in self.tasks]

    def write_files(self):
        folder = self.app.writer.folder
        tasks = self.task_list()
        lines = [f"# Tasks from {self.app.writer.course}", ""]
        lines += [f"- [{'x' if x['done'] else ' '}] {x['task']}" + (f" (due {x['due']})" if x["due"] else "") for x in tasks]
        (folder / "tasks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (folder / "tasks.json").write_text(json.dumps(tasks, indent=2), encoding="utf-8")
        write_task_ics(tasks, folder / "tasks.ics")


def _parse_due(due):
    if not due:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(due.strip(), fmt)
            return d.replace(hour=9) if fmt == "%Y-%m-%d" else d
        except ValueError:
            continue
    return None


def write_task_ics(tasks, path):
    esc = lambda s: s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ThirdEye//Assistant//EN", "CALSCALE:GREGORIAN"]
    for x in tasks:
        due = _parse_due(x.get("due"))
        if not due or x.get("done"):
            continue
        start = due if x.get("kind") == "event" else due - timedelta(hours=1)
        out += ["BEGIN:VEVENT", f"UID:{x['id']}@thirdeye", f"DTSTAMP:{stamp}",
                f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{(start + timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{esc(x['task'][:90])}", f"DESCRIPTION:{esc(x['task'])}",
                "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(x['task'][:90])}", "TRIGGER:-PT30M", "END:VALARM",
                "END:VEVENT"]
    out.append("END:VCALENDAR")
    path.write_text("\r\n".join(out) + "\r\n", encoding="utf-8")
