"""
Tiny web server for the dashboard at http://localhost:8000 (no extra packages needed).
It only listens on this laptop, so nobody else on the Wi-Fi can open it.
"""
import http.server
import json
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path

import config
import settings_store


WEB = Path(__file__).parent / "web"
CTYPES = {".md": "text/markdown; charset=utf-8", ".ics": "text/calendar; charset=utf-8",
          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          ".jpg": "image/jpeg", ".json": "application/json"}
TEST_LINE = "Hi, I'm Third Eye. This is how I'll sound."


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _session_dir(sid):
    name = Path(sid or "").name
    folder = Path(config.SYNC_FOLDER) / name
    return folder if name and name not in (".", "..") and folder.is_dir() else None


def _started(folder):
    try:
        return datetime.strptime(folder.name[:15], "%Y-%m-%d_%H%M")
    except ValueError:
        return datetime.fromtimestamp(folder.stat().st_mtime)


def sessions():
    base = Path(config.SYNC_FOLDER)
    out = []
    for f in (base.iterdir() if base.is_dir() else []):
        if not f.is_dir():
            continue
        sheet = _read_json(f / "study_sheet.json", {})
        out.append({"id": f.name, "title": sheet.get("title") or f.name, "started": _started(f).isoformat(timespec="minutes"),
                    "has_summary": bool(sheet), "tasks": len(_read_json(f / "tasks.json", []))})
    return sorted(out, key=lambda s: (s["started"], s["id"]), reverse=True)


def session(folder):
    import obsidian
    sheet = _read_json(folder / "study_sheet.json", {})
    notes = folder / "live_notes.md"
    note = f"{_started(folder).strftime('%Y-%m-%d %H%M')} {obsidian._safe(sheet.get('title') or folder.name.split('_', 2)[-1])}"
    try:
        has_note = obsidian.read_note(note) is not None
    except Exception:
        has_note = False
    return {"id": folder.name, "sheet": sheet, "tasks": _read_json(folder / "tasks.json", []),
            "notes": notes.read_text(encoding="utf-8") if notes.exists() else "",
            "files": sorted(p.name for p in folder.iterdir() if p.suffix in (".md", ".ics", ".docx")),
            "obsidian_note": note if has_note else ""}


def serve(app, port: int):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, data: bytes, ctype: str, code: int = 200, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj).encode(), "application/json", code)

        def _file_from_lecture(self, name: str, download=False):
            if app.writer is None:
                return self.send_error(404)
            f = app.writer.folder / Path(name).name          # no ../ tricks
            if not f.exists() or f.suffix not in CTYPES:
                return self.send_error(404)
            extra = {"Content-Disposition": f'attachment; filename="{f.name}"'} if download else None
            self._send(f.read_bytes(), CTYPES[f.suffix], extra=extra)

        # ---------- GET ----------
        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path.startswith("/img/"):
                return self._file_from_lecture(path[5:])
            if path.startswith("/files/"):
                return self._file_from_lecture(path[7:], download=True)
            if path == "/vault":
                return self._send((WEB / "vault.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/api/vault"):
                import vault_api
                return vault_api.get(self, path, query)
            if path in ("/", "/index.html"):
                return self._send((WEB / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/state":
                since = int(query.split("v=")[1]) if "v=" in query else -1
                return self._json(app.state(since))
            if path == "/video":
                return self._stream_video()
            if path == "/api/obsidian":
                import obsidian
                vault, items = obsidian.notes()
                return self._json({"vault": str(vault), "folder": obsidian.FOLDER,
                                   "installed": obsidian.obsidian_installed(), "notes": items})
            if path == "/api/settings":
                return self._json({"values": settings_store.current(),
                                   "options": {"voices": settings_store.VOICES}})
            if path == "/api/sessions":
                return self._json(sessions())
            if path in ("/api/session", "/api/session_file"):
                q = urllib.parse.parse_qs(query)
                folder = _session_dir(q.get("id", [""])[0])
                if folder is None:
                    return self.send_error(404)
                if path == "/api/session":
                    return self._json(session(folder))
                f = folder / Path(q.get("name", [""])[0]).name
                if not f.is_file() or f.suffix not in CTYPES:
                    return self.send_error(404)
                return self._send(f.read_bytes(), CTYPES[f.suffix],
                                  extra={"Content-Disposition": f'attachment; filename="{f.name}"'})
            if path == "/api/obsidian/note":
                import obsidian
                name = urllib.parse.parse_qs(query).get("name", [""])[0]
                text = obsidian.read_note(name)
                if text is None:
                    return self.send_error(404)
                return self._send(text.encode("utf-8"), "text/plain; charset=utf-8")
            self.send_error(404)

        def _stream_video(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            last = -1
            try:
                while not app.quitting:
                    last, jpg = app.wait_frame(last)
                    if jpg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            self.close_connection = True

        # ---------- POST (controls) ----------
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = {}
            path = self.path
            if path.startswith("/api/vault"):
                import vault_api
                return vault_api.post(self, path, body)
            if path == "/api/button":
                app.button(str(body.get("button", "")), str(body.get("press", "short")))
                return self._json({"ok": True})
            if path == "/api/approve":
                app.approve(str(body.get("id", "")), bool(body.get("yes")))
                return self._json({"ok": True})
            if path == "/api/start":
                ok = app.start(str(body.get("course", "")))
                return self._json({"ok": ok})
            actions = {
                "/api/pause": app.toggle_pause,
                "/api/ask": app.ask_voice,
                "/api/end": app.end,
                "/api/new": app.new_lecture,
                "/api/rescan": lambda: threading.Thread(target=app.scan_cameras, daemon=True).start(),
                "/api/quit": app.quit,
                "/api/hold": app.hold,
            }
            if path in actions:
                actions[path]()
            elif path == "/api/obsidian/open":
                import obsidian
                obsidian.open_in_obsidian(str(body.get("name", "")))
            elif path == "/api/settings":
                return self._json(settings_store.save(body if isinstance(body, dict) else {}))
            elif path == "/api/voice_test":
                import assistant
                keep = {"voice": config.VOICE, "voice_rate": config.VOICE_RATE}
                settings_store.apply({"voice": body.get("voice", config.VOICE), "voice_rate": body.get("rate", config.VOICE_RATE)})
                assistant.speak(TEST_LINE)
                threading.Timer(6, settings_store.apply, args=(keep,)).start()
            elif path == "/api/key":
                return self._json(app.set_key(str(body.get("provider", "")), str(body.get("key", ""))))
            elif path == "/api/task":
                app.set_task(str(body.get("id", "")), bool(body.get("done")))
            elif path == "/api/ask_text":
                app.ask_text(str(body.get("q", "")))
            elif path == "/api/camera":
                idx = body.get("index")
                app.set_camera(None if idx in (None, "", "off") else int(idx))
            elif path == "/api/mic":
                idx = body.get("index")
                app.set_mic(None if idx in (None, "", "default") else int(idx))
            else:
                return self.send_error(404)
            self._json({"ok": True})

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
