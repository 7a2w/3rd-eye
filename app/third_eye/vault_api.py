"""Vault browser API for web/vault.html. Paths are vault-relative, posix style."""
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path

import obsidian

IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
LINK = re.compile(r"!?\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")


class Bad(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def _root():
    v = obsidian.find_vault()
    if v is None:
        raise Bad(503, "no vault")
    return Path(v).resolve()


def _hidden(rel):
    return any(p.startswith(".") for p in Path(rel).parts)


def _resolve(rel, root=None):
    root = root or _root()
    rel = str(rel or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        raise Bad(400, "bad path")
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts) or parts[0] == ".obsidian":
        raise Bad(400, "bad path")
    p = (root / rel).resolve()
    try:
        inside = p.relative_to(root)
    except ValueError:
        raise Bad(400, "outside vault")
    if inside.parts and inside.parts[0] == ".obsidian":
        raise Bad(400, "bad path")
    return p


def _rel(p, root):
    return p.relative_to(root).as_posix()


def _notes(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("."):
                out.append(Path(dirpath) / f)
    return out


def _tree(root, d):
    items = []
    try:
        entries = sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except OSError:
        return items
    for e in entries:
        if e.name.startswith("."):
            continue
        if e.is_dir():
            items.append({"type": "folder", "name": e.name, "path": _rel(e, root), "children": _tree(root, e)})
        elif e.suffix.lower() == ".md" or e.suffix.lower() in IMAGES:
            st = e.stat()
            items.append({"type": "file", "name": e.name, "path": _rel(e, root),
                          "mtime": st.st_mtime, "size": st.st_size})
    return items


def _read(p):
    return p.read_text(encoding="utf-8", errors="replace")


def _resolve_name(root, name):
    name = name.strip().replace("\\", "/")
    if name.lower().endswith(".md"):
        name = name[:-3]
    if not name:
        return None
    low = name.lower()
    hits = []
    for f in _notes(root):
        rel = _rel(f, root)[:-3]
        if rel.lower() == low or f.stem.lower() == low or rel.lower().endswith("/" + low):
            hits.append(rel + ".md")
    if not hits:
        for f in root.rglob("*"):
            if f.is_file() and f.suffix.lower() in IMAGES and not _hidden(_rel(f, root)):
                rel = _rel(f, root)
                if f.name.lower() == low or rel.lower() == low or rel.lower().endswith("/" + low):
                    hits.append(rel)
    hits.sort(key=lambda r: (r.count("/"), len(r)))
    return hits[0] if hits else None


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".md", dir=p.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        for i in range(6):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                if i == 5:
                    raise
                time.sleep(0.15 * (i + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _md(path):
    path = str(path or "").strip()
    return path if path.lower().endswith(".md") else path + ".md"


def get(h, path, query):
    q = {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}
    try:
        root = _root()
        if path == "/api/vault/tree":
            return h._json({"vault": root.name, "root": str(root), "tree": _tree(root, root)})
        if path == "/api/vault/file":
            p = _resolve(q.get("path"), root)
            if not p.is_file():
                raise Bad(404, "not found")
            ext = p.suffix.lower()
            if ext == ".md":
                return h._send(p.read_bytes(), "text/plain; charset=utf-8")
            if ext in IMAGES:
                return h._send(p.read_bytes(), IMAGES[ext])
            raise Bad(415, "unsupported type")
        if path == "/api/vault/search":
            needle = q.get("q", "").strip().lower()
            out = []
            if needle:
                for f in sorted(_notes(root), key=lambda f: -f.stat().st_mtime):
                    rel = _rel(f, root)
                    if needle in f.stem.lower():
                        out.append({"path": rel, "line": 0, "text": f.stem})
                    for i, line in enumerate(_read(f).splitlines(), 1):
                        if needle in line.lower():
                            out.append({"path": rel, "line": i, "text": line.strip()[:240]})
                            if len(out) >= 100:
                                break
                    if len(out) >= 100:
                        break
            return h._json(out[:100])
        if path == "/api/vault/backlinks":
            target = _resolve(q.get("path"), root)
            trel = _rel(target, root)
            out, seen = [], {}
            stem = target.stem.lower()
            for f in _notes(root):
                if f == target:
                    continue
                for i, line in enumerate(_read(f).splitlines(), 1):
                    hit = False
                    for m in LINK.finditer(line):
                        name = m.group(1).strip()
                        key = name.lower().removesuffix(".md")
                        if key.rsplit("/", 1)[-1] != stem:
                            continue
                        if key not in seen:
                            seen[key] = _resolve_name(root, name)
                        if seen[key] == trel:
                            hit = True
                            break
                    if hit:
                        out.append({"path": _rel(f, root), "line": i, "text": line.strip()[:240]})
            out.sort(key=lambda r: (r["path"].lower(), r["line"]))
            return h._json(out)
        if path == "/api/vault/resolve":
            hit = _resolve_name(root, q.get("name", ""))
            if not hit:
                raise Bad(404, "no such note")
            return h._json({"path": hit})
        if path == "/api/vault/graph":
            notes = _notes(root)
            stems = {}
            for f in notes:
                stems.setdefault(f.stem.lower(), []).append(_rel(f, root))
            for v in stems.values():
                v.sort(key=lambda r: (r.count("/"), len(r)))
            nodes, edges = [], set()
            for f in notes:
                rel = _rel(f, root)
                nodes.append({"path": rel, "name": f.stem})
                for m in LINK.finditer(_read(f)):
                    name = m.group(1).strip().lower()
                    if name.endswith(".md"):
                        name = name[:-3]
                    cands = stems.get(name.rsplit("/", 1)[-1], [])
                    if "/" in name:
                        cands = [c for c in cands if c.lower()[:-3].endswith(name)] or cands
                    if cands and cands[0] != rel:
                        edges.add((rel, cands[0]))
            return h._json({"nodes": nodes, "edges": [list(e) for e in sorted(edges)]})
        raise Bad(404, "unknown endpoint")
    except Bad as e:
        return h._json({"error": str(e)}, e.code)


def post(h, path, body):
    body = body if isinstance(body, dict) else {}
    try:
        root = _root()
        if path == "/api/vault/save":
            p = _resolve(body.get("path"), root)
            if p.suffix.lower() != ".md":
                raise Bad(400, "only .md")
            text = body.get("text")
            if not isinstance(text, str):
                raise Bad(400, "text required")
            _write(p, text)
            return h._json({"ok": True, "path": _rel(p, root), "mtime": p.stat().st_mtime})
        if path == "/api/vault/new":
            p = _resolve(_md(body.get("path")), root)
            if p.exists():
                raise Bad(409, "exists")
            _write(p, str(body.get("text") or ""))
            return h._json({"ok": True, "path": _rel(p, root)})
        if path == "/api/vault/rename":
            src = _resolve(body.get("path"), root)
            to = str(body.get("to") or "")
            dst = _resolve(_md(to) if src.suffix.lower() == ".md" and src.is_file() else to, root)
            if not src.exists():
                raise Bad(404, "not found")
            if dst.exists():
                raise Bad(409, "exists")
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            return h._json({"ok": True, "path": _rel(dst, root)})
        if path == "/api/vault/delete":
            p = _resolve(body.get("path"), root)
            if not p.exists():
                raise Bad(404, "not found")
            trash = root / ".trash"
            trash.mkdir(exist_ok=True)
            dst = trash / p.name
            n = 1
            while dst.exists():
                dst = trash / f"{p.stem} {n}{p.suffix}"
                n += 1
            shutil.move(str(p), str(dst))
            return h._json({"ok": True, "trash": _rel(dst, root)})
        if path == "/api/vault/open":
            p = _resolve(body.get("path"), root) if body.get("path") else root
            url = "obsidian://open?path=" + urllib.parse.quote(str(p))
            try:
                if platform.system() == "Windows":
                    os.startfile(url)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", url])
                else:
                    subprocess.Popen(["xdg-open", url])
            except OSError as e:
                return h._json({"ok": False, "error": str(e)})
            return h._json({"ok": True, "url": url})
        raise Bad(404, "unknown endpoint")
    except Bad as e:
        return h._json({"error": str(e)}, e.code)
    except OSError as e:
        return h._json({"error": str(e)}, 500)
