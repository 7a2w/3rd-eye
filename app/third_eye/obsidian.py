"""
Writes each finished session into an Obsidian vault as a normal note.

The vault is found in this order:
  1. OBSIDIAN_VAULT environment variable (a folder path)
  2. the vault Obsidian last had open (read from Obsidian's own obsidian.json)
If neither exists, nothing is written.

Inside the vault, notes go to "Third Eye/":
  Third Eye/2026-11-25 1432 Team sync with Sam.md   summary, tasks, transcript link
  Third Eye/Tasks.md                                 every open task, in Obsidian Tasks format
  Third Eye/attachments/...                          slide pictures
Tasks use the "- [ ] task 📅 2026-11-28" form, so the Tasks plugin and Dataview pick them up.
"""
import json
import os
import platform
import re
import shutil
from datetime import datetime
from pathlib import Path

FOLDER = "Third Eye"


def _config_paths():
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return [Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "obsidian/obsidian.json"]
    if system == "Darwin":
        return [home / "Library/Application Support/obsidian/obsidian.json"]
    return [home / ".config/obsidian/obsidian.json",
            home / ".var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"]


def find_vault():
    env = os.environ.get("OBSIDIAN_VAULT", "").strip()
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None
    for cfg in _config_paths():
        try:
            vaults = json.loads(cfg.read_text(encoding="utf-8")).get("vaults", {})
        except (OSError, ValueError):
            continue
        ranked = sorted(vaults.values(), key=lambda v: (bool(v.get("open")), v.get("ts", 0)), reverse=True)
        for v in ranked:
            p = Path(v.get("path", ""))
            if p.is_dir():
                return p
    return None


def _safe(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip()[:80] or "Session"


def _due(task):
    m = re.match(r"\d{4}-\d{2}-\d{2}", task.get("due") or "")
    return f" 📅 {m.group(0)}" if m else ""


def export(writer, sheet, tasks, context=""):
    """Write the session into the vault. Returns the note path, or None if there is no vault."""
    vault = find_vault()
    if vault is None:
        return None
    base = vault / FOLDER
    att = base / "attachments" / writer.folder.name
    base.mkdir(parents=True, exist_ok=True)

    title = sheet.get("title") or writer.course
    note = base / f"{writer.started.strftime('%Y-%m-%d %H%M')} {_safe(title)}.md"
    kind = (context.split(",")[0].strip() or "session").replace(" ", "-")

    md = ["---", f"date: {writer.started.strftime('%Y-%m-%d')}", f"time: {writer.started.strftime('%H:%M')}",
          f"type: {kind}", f"topic: \"{context}\"", "tags: [third-eye, " + kind + "]", "---", "",
          f"# {title}", "", sheet.get("tldr", ""), ""]
    if sheet.get("key_points"):
        md += ["## Key points"] + [f"- {p}" for p in sheet["key_points"]] + [""]
    if sheet.get("key_terms"):
        md += ["## Terms and names"] + [f"- **{t['term']}**: {t['definition']}" for t in sheet["key_terms"]] + [""]
    open_tasks = [t for t in tasks if not t.get("done")]
    todos = [{"task": t["task"], "due": None} for t in sheet.get("todos", [])
             if not any(t["task"] == x["task"] for x in open_tasks)]
    if open_tasks or todos:
        md += ["## Tasks"] + [f"- [ ] {t['task']}{_due(t)}" for t in open_tasks + todos] + [""]
    if sheet.get("exam_questions"):
        md += ["## Questions"] + [f"- {q}" for q in sheet["exam_questions"]] + [""]
    if sheet.get("confusing_parts"):
        md += ["## Follow up on"] + [f"- {c}" for c in sheet["confusing_parts"]] + [""]

    slides = sorted(writer.folder.glob("slide_*.jpg"))
    if slides:
        att.mkdir(parents=True, exist_ok=True)
        md.append("## Pictures")
        for s in slides:
            shutil.copy2(s, att / s.name)
            md.append(f"![[{FOLDER}/attachments/{writer.folder.name}/{s.name}]]")
        md.append("")

    md += ["## Transcript", "", writer.timed_transcript() or "(nothing was transcribed)", ""]
    note.write_text("\n".join(md), encoding="utf-8")

    task_file = base / "Tasks.md"
    existing = task_file.read_text(encoding="utf-8") if task_file.exists() else "# Third Eye tasks\n\n"
    link = f"[[{note.stem}]]"
    new = [f"- [ ] {t['task']}{_due(t)} ({link})" for t in open_tasks if t["task"] not in existing]
    if new:
        task_file.write_text(existing.rstrip("\n") + "\n" + "\n".join(new) + "\n", encoding="utf-8")
    print(f"[obsidian] saved to {note}")
    return note
