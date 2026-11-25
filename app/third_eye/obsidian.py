"""
Writes each finished session into an Obsidian vault as a normal note.

The vault is found in this order:
  1. OBSIDIAN_VAULT environment variable (a folder path)
  2. the vault Obsidian last had open (read from Obsidian's own obsidian.json)
  3. Documents/Third Eye Vault, created if needed (open it in Obsidian with "Open folder as vault")

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
DEFAULT_VAULT = Path.home() / "Documents" / "Third Eye Vault"


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
    p = DEFAULT_VAULT
    (p / ".obsidian").mkdir(parents=True, exist_ok=True)
    return p


def obsidian_installed():
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Obsidian/Obsidian.exe"
        return local.exists() or any(c.exists() for c in _config_paths())
    if platform.system() == "Darwin":
        return Path("/Applications/Obsidian.app").exists()
    return shutil.which("obsidian") is not None or any(c.exists() for c in _config_paths())


def notes():
    """Session notes in the vault, newest first."""
    vault = find_vault()
    base = vault / FOLDER
    if not base.is_dir():
        return vault, []
    files = [f for f in base.glob("*.md")]
    files.sort(key=lambda f: (f.name != "Tasks.md", -f.stat().st_mtime))
    return vault, [{"name": f.stem, "modified": f.stat().st_mtime, "size": f.stat().st_size} for f in files]


def read_note(name):
    f = find_vault() / FOLDER / (Path(name).name + ".md")
    return f.read_text(encoding="utf-8") if f.is_file() else None


def open_in_obsidian(name=""):
    """Open a note (or the vault) in Obsidian, or the folder if Obsidian isn't installed."""
    import subprocess
    import urllib.parse
    vault = find_vault()
    target = vault / FOLDER / (Path(name).name + ".md") if name else vault
    if obsidian_installed():
        url = "obsidian://open?path=" + urllib.parse.quote(str(target))
    else:
        url = str(target.parent if name else vault)
    if platform.system() == "Windows":
        os.startfile(url)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def _safe(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip()[:80] or "Session"


def _due(task):
    m = re.match(r"\d{4}-\d{2}-\d{2}", task.get("due") or "")
    return f" 📅 {m.group(0)}" if m else ""


def _related(base, title, topic, skip):
    """Existing session notes with the same title or topic."""
    if not base.is_dir():
        return []
    want = _safe(title).lower()
    found = []
    for f in base.glob("*.md"):
        if f.name == "Tasks.md" or f.name == skip:
            continue
        name = re.sub(r"^\d{4}-\d{2}-\d{2} \d{4} ", "", f.stem).lower()
        same_topic = False
        if topic:
            try:
                head = f.read_text(encoding="utf-8")[:600]
            except OSError:
                continue
            same_topic = f'topic: "{topic}"' in head
        if name == want or same_topic:
            found.append(f)
    return sorted(found)


def propose(writer, sheet, tasks, context=""):
    """Work out what export() would change in the vault, without writing anything.

    Returns a change set for apply(): the new note, task lines for Tasks.md, links to add to
    related notes, and pictures to copy, plus "changes" as short lines to show the user.
    """
    vault = find_vault()
    base = vault / FOLDER
    att = base / "attachments" / writer.folder.name

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
    copies = []
    if slides:
        md.append("## Pictures")
        for s in slides:
            copies.append((str(s), str(att / s.name)))
            md.append(f"![[{FOLDER}/attachments/{writer.folder.name}/{s.name}]]")
        md.append("")

    related = _related(base, title, context, note.name)
    if related:
        md += ["## Related"] + [f"- [[{f.stem}]]" for f in related] + [""]

    md += ["## Transcript", "", writer.timed_transcript() or "(nothing was transcribed)", ""]

    task_file = base / "Tasks.md"
    existing = task_file.read_text(encoding="utf-8") if task_file.exists() else ""
    link = f"[[{note.stem}]]"
    task_lines = [f"- [ ] {t['task']}{_due(t)} ({link})" for t in open_tasks if t["task"] not in existing]

    changes = [f"New note: {FOLDER}/{note.name}"]
    changes += [f"Tasks.md: add {line[6:]}" for line in task_lines]
    changes += [f"Link from {f.name}" for f in related]
    if copies:
        changes.append(f"Copy {len(copies)} picture{'s' if len(copies) != 1 else ''} to attachments")
    return {"title": title, "note": str(note), "text": "\n".join(md), "tasks_file": str(task_file),
            "task_lines": task_lines, "links": [str(f) for f in related], "copies": copies, "changes": changes}


def apply(change):
    """Make the changes from propose(). Returns the note path."""
    note = Path(change["note"])
    note.parent.mkdir(parents=True, exist_ok=True)
    for src, dst in change["copies"]:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        if Path(src).exists():
            shutil.copy2(src, dst)
    note.write_text(change["text"], encoding="utf-8")

    task_file = Path(change["tasks_file"])
    existing = task_file.read_text(encoding="utf-8") if task_file.exists() else "# Third Eye tasks\n\n"
    new = [line for line in change["task_lines"] if line not in existing]
    if new:
        task_file.write_text(existing.rstrip("\n") + "\n" + "\n".join(new) + "\n", encoding="utf-8")

    for path in change["links"]:
        f = Path(path)
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        line = f"- [[{note.stem}]]"
        if line in text:
            continue
        if "\n## Related\n" in text:
            text = text.replace("\n## Related\n", f"\n## Related\n{line}\n", 1)
        else:
            text = text.rstrip("\n") + f"\n\n## Related\n{line}\n"
        f.write_text(text, encoding="utf-8")
    print(f"[obsidian] saved to {note}")
    return note


def export(writer, sheet, tasks, context=""):
    """Write the session into the vault straight away. Returns the note path."""
    return apply(propose(writer, sheet, tasks, context))
