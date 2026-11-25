"""
Looks things up in earlier sessions, only when a question is about the past.
"""
import json
import re
from pathlib import Path

import config

PAST = re.compile(
    r"\b(last (time|week|class|lecture|meeting|session|monday|tuesday|wednesday|thursday|friday)|yesterday|"
    r"earlier (today|this week)|before|previous(ly)?|remember|recall|did (i|we|he|she|they)|"
    r"when (did|was)|what was (said|the)|on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\d+ (days|weeks) ago|other day)\b", re.I)


def about_the_past(question: str) -> bool:
    return bool(PAST.search(question))


def _words(text):
    from assistant import keywords
    return set(w for w in keywords(text) if len(w) > 3)


def search(question: str, skip_folder=None, limit=3) -> str:
    """Best matching lines from earlier sessions, as short dated snippets. Empty if nothing fits."""
    want = _words(question) - {"last", "time", "week", "yesterday", "earlier", "remember", "previous", "before",
                               "talk", "talked", "talking", "said", "tell", "told", "thing", "things", "what",
                               "that", "about", "session", "lecture", "class", "meeting", "recall", "today"}
    if not want:
        return ""
    root = Path(config.SYNC_FOLDER)
    hits = []
    for folder in sorted(root.glob("*_*"), reverse=True)[:60]:
        if not folder.is_dir() or (skip_folder and folder.resolve() == Path(skip_folder).resolve()):
            continue
        date = folder.name[:10]
        sheet = folder / "study_sheet.json"
        lines = []
        if sheet.exists():
            try:
                s = json.loads(sheet.read_text(encoding="utf-8"))
                lines += [s.get("tldr", "")] + s.get("key_points", []) + [t.get("task", "") for t in s.get("todos", [])]
            except (OSError, ValueError):
                pass
        notes = folder / "live_notes.md"
        if notes.exists():
            try:
                lines += re.split(r"(?<=[.!?])\s+", notes.read_text(encoding="utf-8"))
            except OSError:
                pass
        for line in lines:
            score = len(want & _words(line))
            if score >= 1:
                hits.append((score, date, re.sub(r"`[\d:]+`|\*\*|\s+", " ", line).strip()[:220]))
    hits.sort(key=lambda h: (-h[0], h[1]), reverse=False)
    seen, out = set(), []
    for _, date, line in hits:
        if line and line not in seen:
            seen.add(line)
            out.append(f"[{date}] {line}")
        if len(out) >= limit:
            break
    return "\n".join(out)
