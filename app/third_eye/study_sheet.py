"""
After a session: a short summary sheet + reminders. For a lecture it reads as a study sheet;
for a meeting or conversation the same sections hold the decisions, names and follow-ups.

Outputs (in the session's synced folder):
  study_sheet.md    - readable anywhere
  study_sheet.docx  - Word version (if python-docx is installed)
  reminders.ics     - tap on your phone to add review reminders + to-dos to your calendar
"""
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import config
from assistant import STOPWORDS, call_ai, keywords

SHEET_PROMPT = """You are making a one-page summary for a university student with ADHD/insomnia
who may have zoned out during parts of this session. Be concise, concrete and skimmable.
If it was a lecture, write a study sheet. If it was a meeting, call or conversation, key_terms holds
names, places and jargon, exam_questions holds questions worth following up on, and todos holds
commitments and decisions that need action.

Session: {course}
What it seemed to be: {context}
Date: {date}
Tasks already noted while listening: {tasks}

TRANSCRIPT (auto speech-to-text, may contain errors):
{transcript}

TEXT CAPTURED FROM SLIDES/WHITEBOARD (OCR, may contain errors):
{slides}

Return ONLY valid JSON with exactly these keys:
{{
 "title": "short name for the session",
 "tldr": "2-3 sentence summary of the whole session",
 "key_points": ["5-8 most important ideas, one short sentence each"],
 "key_terms": [{{"term": "...", "definition": "short definition as used here"}}],
 "exam_questions": ["3-5 self-test or follow-up questions"],
 "todos": [{{"task": "homework, deadlines, commitments and events mentioned", "due_in_days": 7}}],
 "confusing_parts": ["anything that sounded unclear or worth asking about later (can be empty)"]
}}
For todos, estimate due_in_days from what was said (e.g. 'next class' ~2, 'next week' 7). Use [] if none."""


# ---------------- AI version ----------------
def ai_sheet(course, transcript, slides, context="", tasks=""):
    raw = call_ai("You write accurate, skimmable summaries. Output JSON only.",
                      SHEET_PROMPT.format(course=course, context=context or "unknown", tasks=tasks or "none",
                                          date=datetime.now().strftime("%Y-%m-%d"),
                                          transcript=transcript[-60000:] or "(empty)",
                                          slides=slides[-15000:] or "(none)"),
                      max_tokens=2000)
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(match.group(0) if match else raw)


# ---------------- Offline version (no API key) ----------------
FILLER = set("""one two three four five six seven eight nine ten first second third next last
today talk talking going called happens make makes made thing things something stuff right basically
actually kind sort lot people into onto over under want need look see said says say good great example mean means let""".split())
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
TODO_WORDS = re.compile(r"\b(due|homework|assignment|problem set|quiz|exam|midterm|read(ing)?|"
                        r"chapter|submit|deadline|lab report|essay|project|final exam)\b", re.I)


def _guess_due_days(sentence: str) -> int:
    s = sentence.lower()
    if "tomorrow" in s:
        return 1
    if "next class" in s or "next lecture" in s:
        return 2
    if "next week" in s:
        return 7
    if "two weeks" in s:
        return 14
    for i, day in enumerate(WEEKDAYS):
        if day in s:
            return (i - datetime.now().weekday()) % 7 or 7
    return 3


def offline_sheet(course, transcript, slides):
    text = transcript + " " + slides
    sentences = list(dict.fromkeys(s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript)
                                   if len(s.split()) >= 6))   # no repeats
    words = keywords(text)
    freq = Counter(words)
    # candidate terms: no number words / filler, no contractions
    def good(w):
        return "'" not in w and w not in FILLER and len(w) > 3
    # two-word phrases are usually better "terms" than single words
    bigrams = Counter(f"{a} {b}" for a, b in zip(words, words[1:]) if a != b and good(a) and good(b))
    terms, used = [], set()
    for b, c in bigrams.most_common(15):
        if c >= 2 and not (set(b.split()) & used) and len(terms) < 4:
            terms.append(b)
            used |= set(b.split())
    for w, c in freq.most_common(40):
        if len(terms) >= 8 or c < 2:
            break
        if good(w) and w not in used:
            terms.append(w)
            used.add(w)

    def score(s):
        kws = keywords(s)
        return sum(freq[w] for w in kws) / (len(kws) + 3)

    top = sorted(sentences, key=score, reverse=True)[:7]
    key_points = [s for s in sentences if s in top]        # keep lecture order

    def define(term):
        for s in sentences:
            if term in s.lower():
                return s
        return "(mentioned on slides)"

    todo_sents = dict.fromkeys(s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript)
                               if TODO_WORDS.search(s) and len(s.split()) >= 4)
    todos = [{"task": s, "due_in_days": _guess_due_days(s)} for s in todo_sents]
    return {
        "title": course,
        "tldr": " ".join(key_points[:2]) or "No speech was captured.",
        "key_points": key_points,
        "key_terms": [{"term": t, "definition": define(t)} for t in terms],
        "exam_questions": [f"Explain '{t}' in your own words and give an example." for t in terms[:4]],
        "todos": todos[:8],
        "confusing_parts": [],
        "_note": "Made offline (no AI key). Add a free Gemini key or a Claude key for a much better AI-written sheet.",
    }


# ---------------- Writers ----------------
def to_markdown(sheet, course, date):
    md = [f"# Study sheet: {sheet.get('title') or course}",
          f"*{course} - {date.strftime('%A %B %d, %Y')}*", ""]
    if sheet.get("_note"):
        md += [f"> {sheet['_note']}", ""]
    md += ["## TL;DR", sheet.get("tldr", ""), "", "## Key points"]
    md += [f"- {p}" for p in sheet.get("key_points", [])]
    md += ["", "## Key terms"]
    md += [f"- **{t['term']}**: {t['definition']}" for t in sheet.get("key_terms", [])]
    md += ["", "## Test yourself"]
    md += [f"{i}. {q}" for i, q in enumerate(sheet.get("exam_questions", []), 1)]
    if sheet.get("todos"):
        md += ["", "## To-do"]
        md += [f"- [ ] {t['task']} *(due in ~{t.get('due_in_days', 3)} days)*" for t in sheet["todos"]]
    if sheet.get("confusing_parts"):
        md += ["", "## Ask the professor / review"]
        md += [f"- {c}" for c in sheet["confusing_parts"]]
    md += ["", "## Review schedule",
           ", ".join((date + timedelta(days=d)).strftime("%a %b %d") for d in config.REVIEW_DAYS)]
    return "\n".join(md) + "\n"


def to_docx(sheet, course, date, path):
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError:
        return None
    doc = Document()
    doc.styles["Normal"].font.size = Pt(11)
    doc.add_heading(f"Study sheet: {sheet.get('title') or course}", 0)
    doc.add_paragraph().add_run(f"{course} - {date.strftime('%A %B %d, %Y')}").italic = True
    if sheet.get("_note"):
        doc.add_paragraph(sheet["_note"]).runs[0].italic = True
    doc.add_heading("TL;DR", 1)
    doc.add_paragraph(sheet.get("tldr", ""))
    doc.add_heading("Key points", 1)
    for p in sheet.get("key_points", []):
        doc.add_paragraph(p, style="List Bullet")
    doc.add_heading("Key terms", 1)
    for t in sheet.get("key_terms", []):
        para = doc.add_paragraph(style="List Bullet")
        para.add_run(t["term"] + ": ").bold = True
        para.add_run(t["definition"])
    doc.add_heading("Test yourself", 1)
    for q in sheet.get("exam_questions", []):
        doc.add_paragraph(q, style="List Number")
    if sheet.get("todos"):
        doc.add_heading("To-do", 1)
        for t in sheet["todos"]:
            doc.add_paragraph(f"☐ {t['task']} (due in ~{t.get('due_in_days', 3)} days)")
    if sheet.get("confusing_parts"):
        doc.add_heading("Ask the professor / review", 1)
        for c in sheet["confusing_parts"]:
            doc.add_paragraph(c, style="List Bullet")
    doc.save(path)
    return path


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(sheet, course, date, path):
    title = sheet.get("title") or course
    events = []
    for d in config.REVIEW_DAYS:
        events.append((date + timedelta(days=d), f"Review: {title}",
                       f"Spaced review #{config.REVIEW_DAYS.index(d) + 1}. Open your study sheet and "
                       f"answer the 'Test yourself' questions without looking.", 30))
    for t in sheet.get("todos", []):
        due = date + timedelta(days=int(t.get("due_in_days", 3) or 3))
        events.append((due - timedelta(days=1), f"Due soon ({course}): {t['task'][:60]}", t["task"], 60))
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ThirdEye//Earpiece Prototype//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for day, summary, desc, minutes in events:
        start = day.replace(hour=config.REMINDER_HOUR, minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=minutes)
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@thirdeye", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{_ics_escape(summary)}", f"DESCRIPTION:{_ics_escape(desc)}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(summary)}",
                  "TRIGGER:-PT10M", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    Path(path).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def generate(writer, brain=None) -> dict:
    """Build the summary for a finished session (writer = sync.NotesWriter, brain = brain.Brain)."""
    transcript = writer.timed_transcript()
    slides = writer.slide_text()
    tasks = brain.task_list() if brain else []
    context = ", ".join(x for x in ((brain.context, brain.topic) if brain else ()) if x and x != "listening")
    sheet = None
    if config.ai_provider():
        try:
            print(f"[summary] asking {config.ai_provider()} to write the summary...")
            sheet = ai_sheet(writer.course, transcript, slides, context,
                             "; ".join(t["task"] for t in tasks))
        except Exception as e:
            print(f"[summary] AI failed ({e}); using offline version")
    if sheet is None:
        sheet = offline_sheet(writer.course, writer.transcript(), slides)

    date = writer.started
    known = {re.sub(r"[^a-z0-9]", "", t["task"].lower()) for t in sheet.get("todos", [])}
    for t in tasks:
        if t.get("done") or re.sub(r"[^a-z0-9]", "", t["task"].lower()) in known:
            continue
        days = 3
        if t.get("due"):
            try:
                days = max(0, (datetime.strptime(t["due"][:10], "%Y-%m-%d") - date).days + 1)
            except ValueError:
                pass
        sheet.setdefault("todos", []).append({"task": t["task"], "due_in_days": days})
    if context:
        sheet["context"] = context

    out = {"md": writer.folder / "study_sheet.md", "ics": writer.folder / "reminders.ics"}
    out["md"].write_text(to_markdown(sheet, writer.course, date), encoding="utf-8")
    to_ics(sheet, writer.course, date, out["ics"])
    if to_docx(sheet, writer.course, date, writer.folder / "study_sheet.docx"):
        out["docx"] = writer.folder / "study_sheet.docx"
    (writer.folder / "study_sheet.json").write_text(json.dumps(sheet, indent=2), encoding="utf-8")
    if brain:
        brain.write_files()
        out["tasks_md"] = writer.folder / "tasks.md"
        out["tasks_ics"] = writer.folder / "tasks.ics"
    try:
        import obsidian
        if config.ASK_BEFORE_OBSIDIAN:
            writer.obsidian_proposal = obsidian.propose(writer, sheet, tasks, context)
        else:
            writer.obsidian_note = obsidian.export(writer, sheet, tasks, context)
    except Exception as e:
        print(f"[obsidian] could not save: {e}")
    return out
