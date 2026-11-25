"""
Tiny web server for the dashboard at http://localhost:8000 (no extra packages needed).
It only listens on this laptop, so nobody else on the Wi-Fi can open it.
"""
import http.server
import json
import threading
from pathlib import Path


WEB = Path(__file__).parent / "web"
CTYPES = {".md": "text/markdown; charset=utf-8", ".ics": "text/calendar; charset=utf-8",
          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          ".jpg": "image/jpeg", ".json": "application/json"}


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
            if path in ("/", "/index.html"):
                return self._send((WEB / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/state":
                since = int(query.split("v=")[1]) if "v=" in query else -1
                return self._json(app.state(since))
            if path == "/video":
                return self._stream_video()
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
