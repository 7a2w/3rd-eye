"""Drive a running Third Eye app through the dashboard's HTTP API, like a user clicking through it.

usage: python drive.py APP_DIR PYTHON OUT_DIR [extra main.py args...]

env:
  TE_PORT              dashboard port (default 8010)
  TE_RECORD_SECONDS    record this long after the voice question, then go on (default: until the notes stop changing)
  TE_SKIP_VOICE_ASK=1  skip POST /api/ask (with no mic, the original app leaves an audio-file lecture paused)
  TE_SKIP_END=1        stop after the typed question and leave the app running (for screenshots)
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP, PY, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
EXTRA = sys.argv[4:]
PORT = int(os.environ.get("TE_PORT", "8010"))
BASE = f"http://127.0.0.1:{PORT}"
STOP_AFTER = float(os.environ.get("TE_RECORD_SECONDS", "0"))   # 0 = wait for the audio file to finish
SKIP_END = os.environ.get("TE_SKIP_END") == "1"
SKIP_VOICE = os.environ.get("TE_SKIP_VOICE_ASK") == "1"
QUIET_SECONDS = 25          # no new notes for this long = the recorded lecture has finished
MAX_LECTURE_SECONDS = 900

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
notes = OUT / "notes"
env = dict(os.environ, THIRD_EYE_SYNC=str(notes), PYTHONUNBUFFERED="1")
log = open(OUT / "app.log", "w")
proc = subprocess.Popen([PY, "main.py", "--no-browser", "--port", str(PORT), *EXTRA], cwd=APP, env=env,
                        stdout=log, stderr=subprocess.STDOUT)
events = []


def note(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    events.append(line)


def get(path, raw=False, timeout=10):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        data = r.read()
        return (data, r.headers) if raw else json.loads(data)


def post(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read() or b"{}")


def wait_for(cond, timeout, what, every=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise SystemExit(f"app exited early with code {proc.returncode} while waiting for {what}")
        try:
            s = get("/state?v=-1")
            if cond(s):
                return s
        except Exception:
            pass
        time.sleep(every)
    raise SystemExit(f"timed out waiting for {what}")


try:
    s = wait_for(lambda s: True, 60, "dashboard server")
    note(f"server up: phase={s['phase']} model={s['model']} ai={s['ai']} mic={s['mic']} camera={s['camera']}")
    html, hdrs = get("/", raw=True)
    note(f"GET / -> {len(html)} bytes, {hdrs['Content-Type']}")
    s = wait_for(lambda s: s["model"] != "loading", 600, "speech model")
    note(f"model: {s['model']}")
    (OUT / "state_setup.json").write_text(json.dumps(s, indent=1))
    if s["model"] != "ready":
        raise SystemExit("speech model failed to load")

    note(f"POST /api/start -> {post('/api/start', {'course': 'BIOL 1010'})}")
    s = wait_for(lambda s: s["phase"] == "recording", 10, "recording phase")
    note(f"recording: mode={s['mode']} folder={s.get('folder')}")

    time.sleep(20)
    note(f"POST /api/pause -> {post('/api/pause')}")
    s = get("/state?v=-1")
    note(f"paused={s['paused']} mode={s['mode']} status={s['status']!r}")
    time.sleep(3)
    note(f"POST /api/pause (resume) -> {post('/api/pause')}")
    s = get("/state?v=-1")
    note(f"paused={s['paused']} mode={s['mode']}")

    if not SKIP_VOICE:
        note(f"POST /api/ask (voice) -> {post('/api/ask')}")
        s = wait_for(lambda s: not s["asking"], 40, "voice question to finish", every=0.3)
        note(f"after voice ask: status={s['status']!r} mode={s['mode']} paused={s['paused']}")
        if s["paused"] and s["mode"] == "REC":
            note("BUG: lecture is paused but the indicator says REC")

    if STOP_AFTER:
        time.sleep(STOP_AFTER)
    else:
        last_v, still, t0 = -1, 0, time.time()
        while still < QUIET_SECONDS and time.time() - t0 < MAX_LECTURE_SECONDS:
            time.sleep(1)
            s = get("/state?v=-1")
            if s["version"] == last_v:
                still += 1
            else:
                still, last_v = 0, s["version"]
    s = get("/state?v=-1")
    note(f"lecture fed: {sum(e['kind'] == 'speech' for e in s['entries'])} speech, "
         f"{sum(e['kind'] == 'slide' for e in s['entries'])} slides, elapsed={s['elapsed']}")

    note(f"POST /api/ask_text -> {post('/api/ask_text', {'q': 'What is the final electron acceptor?'})}")
    s = wait_for(lambda s: not s["asking"] and any(e["kind"] == "qa" for e in s.get("entries", [])), 90, "typed answer")
    qa = [e for e in s["entries"] if e["kind"] == "qa"][-1]
    note(f"Q: {qa['q']}\n    A: {qa['a']}")
    (OUT / "state_recording.json").write_text(json.dumps(s, indent=1))
    try:
        frame, h = get("/video", raw=True, timeout=3)
    except Exception as e:
        note(f"/video: {type(e).__name__} (expected for a streaming endpoint)")

    for e in s["entries"]:
        if e["kind"] == "slide":
            data, h = get("/img/" + e["img"], raw=True)
            note(f"GET /img/{e['img']} -> {len(data)} bytes {h['Content-Type']}")
            break

    if SKIP_END:
        note("TE_SKIP_END set, leaving the app running")
        print(json.dumps({"pid": proc.pid}))
        sys.exit(0)

    note(f"POST /api/end -> {post('/api/end')}")
    s = wait_for(lambda s: s["phase"] == "done", 300, "study sheet")
    note(f"done: files={s.get('files')} reviews={s.get('reviews')}")
    (OUT / "state_done.json").write_text(json.dumps(s, indent=1))
    sheet = s.get("sheet") or {}
    note(f"sheet title={sheet.get('title')!r} points={len(sheet.get('key_points', []))} terms={len(sheet.get('key_terms', []))} "
         f"todos={len(sheet.get('todos', []))} note={sheet.get('_note')!r}")
    for key, name in (s.get("files") or {}).items():
        data, h = get("/files/" + name, raw=True)
        note(f"GET /files/{name} -> {len(data)} bytes {h['Content-Type']} {h.get('Content-Disposition')}")
    data, h = get("/files/live_notes.md", raw=True)
    note(f"GET /files/live_notes.md -> {len(data)} bytes")

    note(f"POST /api/ask_text (after lecture) -> {post('/api/ask_text', {'q': 'When is problem set four due?'})}")
    s = wait_for(lambda s: not s["asking"] and sum(e["kind"] == "qa" for e in s.get("entries", [])) >= 2, 90, "second answer")
    qa = [e for e in s["entries"] if e["kind"] == "qa"][-1]
    note(f"Q: {qa['q']}\n    A: {qa['a']}")
    (OUT / "state_done.json").write_text(json.dumps(s, indent=1))

    note(f"POST /api/new -> {post('/api/new')}")
    s = wait_for(lambda s: s["phase"] == "setup", 10, "setup phase")
    note(f"back to setup: version={s.get('version')} mic.error={s['mic']['error']!r}")
    note(f"POST /api/rescan -> {post('/api/rescan')}")
    note(f"POST /api/camera off -> {post('/api/camera', {'index': 'off'})}")
    note(f"POST /api/mic default -> {post('/api/mic', {'index': 'default'})}")
    note(f"POST /api/quit -> {post('/api/quit')}")
    proc.wait(timeout=15)
    note(f"app exited with code {proc.returncode}")
finally:
    if proc.poll() is None and not SKIP_END:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    (OUT / "events.txt").write_text("\n".join(events) + "\n")
