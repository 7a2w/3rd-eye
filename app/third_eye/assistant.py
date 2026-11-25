"""
Live assistant: you ask out loud (or say "Hey Third Eye"), it answers out loud.

Uses Claude (ANTHROPIC_API_KEY) or Google Gemini (GEMINI_API_KEY, which has a free tier).
Without a key it falls back to searching what it heard for the most relevant sentences,
so the demo still works offline.
"""
import json
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

import config

STOPWORDS = set("""a an the and or but if of to in on at for from by with about as is are was were be been
being it its this that these those what which who whom whose when where why how do does did can could
would should will shall may might must i you he she we they me him her us them my your our their just
so than then there here not no yes also very really okay ok um uh like going gonna know""".split())


def call_claude(system: str, user: str, max_tokens: int = 600) -> str:
    """Minimal Anthropic Messages API call using only the standard library."""
    body = json.dumps({
        "model": config.AI_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return "".join(block.get("text", "") for block in data.get("content", [])).strip()


# Live questions use the fast "Lite" models (thinking is off by default, so answers come back quickly).
# Study sheets use the smarter Flash models. All of these have a free tier.
GEMINI_FAST = ["gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
GEMINI_SMART = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
_last_good = {}            # "fast"/"smart" -> model that answered last time (tried first next time)
_no_thinking_cfg = set()   # models that rejected the thinking setting


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VERTEX_API = "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"
_endpoint = {}             # key -> the address that accepted it


def gemini_url(model, key):
    """Gemini API keys work on the Gemini API; Google Cloud express keys only on Vertex AI."""
    return _endpoint.get(key, GEMINI_API).format(model=model)


def _version(name):
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def _pick_models(names):
    """Newest stable Flash and Flash-Lite models the key can use."""
    skip = ("preview", "exp", "tts", "image", "live", "audio", "embedding", "thinking", "learnlm", "-latest")
    usable = sorted({n for n in names if "flash" in n and not any(x in n for x in skip)},
                    key=_version, reverse=True)
    lite = [n for n in usable if "lite" in n]
    flash = [n for n in usable if "lite" not in n]
    if lite or flash:
        GEMINI_FAST[:] = (lite[:2] + flash[:2]) or GEMINI_FAST
        GEMINI_SMART[:] = (flash[:2] + lite[:1]) or GEMINI_SMART
        print(f"[assistant] Gemini models: fast {GEMINI_FAST[0]}, smart {GEMINI_SMART[0]}")


def _google_reason(e):
    try:
        return json.loads(e.read().decode("utf-8", "replace"))["error"]["message"]
    except Exception:
        return f"HTTP {e.code}"


def check_gemini_key(key: str) -> str:
    """Find which Google address accepts the key and which models it can use. Returns "" if it works."""
    reasons = []
    try:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                     headers={"x-goog-api-key": key})
        data = json.load(urllib.request.urlopen(req, timeout=8))
        _endpoint[key] = GEMINI_API
        _pick_models([m["name"].split("/")[-1] for m in data.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", [])])
        return ""
    except urllib.error.HTTPError as e:
        reasons.append("Gemini API: " + _google_reason(e))
    except Exception as e:
        reasons.append(f"Gemini API: {e}")
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": "Say OK."}]}],
                       "generationConfig": {"maxOutputTokens": 5}}).encode()
    for model in GEMINI_SMART + GEMINI_FAST:
        req = urllib.request.Request(VERTEX_API.format(model=model), data=body, method="POST",
                                     headers={"x-goog-api-key": key, "content-type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=8).read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 429):          # the key was accepted; this model just isn't offered or is busy
                _endpoint[key] = VERTEX_API
                return ""
            reasons.append("Vertex AI: " + _google_reason(e))
            break
        except Exception as e:
            reasons.append(f"Vertex AI: {e}")
            break
        _endpoint[key] = VERTEX_API
        return ""
    print("[assistant] Gemini key rejected: " + " | ".join(reasons))
    return reasons[0] if reasons else "no answer from Google"


def _gemini_request(model, system, user, max_tokens, timeout):
    gen = {"maxOutputTokens": max_tokens * 4 + 1024, "temperature": 0.4}
    # Thinking makes answers slower; switch it off where the model allows.
    if model.startswith("gemini-2.5-flash") and model not in _no_thinking_cfg:
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen}
    req = urllib.request.Request(
        gemini_url(model, config.GEMINI_API_KEY),
        data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def call_gemini(system: str, user: str, max_tokens: int = 600, fast: bool = False) -> str:
    """Google Gemini API (free tier available), standard library only."""
    if config.GEMINI_API_KEY not in _endpoint:
        check_gemini_key(config.GEMINI_API_KEY)
    mode = "fast" if fast else "smart"
    models = [config.GEMINI_MODEL] if config.GEMINI_MODEL and not fast else []
    models = list(dict.fromkeys(([_last_good[mode]] if mode in _last_good else []) + models
                                + (GEMINI_FAST if fast else GEMINI_SMART)))
    timeout = 20 if fast else 90
    last_error = None
    for attempt in range(2):                  # two rounds through the models, with a short pause between
        for model in models:
            try:
                try:
                    data = _gemini_request(model, system, user, max_tokens, timeout)
                except urllib.error.HTTPError as e:
                    if e.code == 400 and model not in _no_thinking_cfg:
                        _no_thinking_cfg.add(model)   # model didn't accept the thinking setting: retry without
                        data = _gemini_request(model, system, user, max_tokens, timeout)
                    else:
                        raise
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="ignore")[:300]
                if e.code in (404, 500, 503, 504):  # model missing or busy: try the next one
                    last_error = f"{model}: {'not available' if e.code == 404 else 'busy right now'}"
                    continue
                if e.code == 429:                     # limit for this model: another model has its own limit
                    last_error = "Gemini free-tier limit reached; wait a minute and try again"
                    continue
                raise RuntimeError(f"Gemini error {e.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = f"couldn't reach {model} ({e})"
                continue
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if text:
                _last_good[mode] = model
                return text
            last_error = f"{model} returned an empty answer"
        time.sleep(1)
    raise RuntimeError(last_error or "Gemini didn't answer")


def call_ai(system: str, user: str, max_tokens: int = 600, fast: bool = False) -> str:
    """Use whichever AI has a key: Claude first, then Gemini. fast=True for live questions."""
    if config.ANTHROPIC_API_KEY:
        return call_claude(system, user, max_tokens)
    if config.GEMINI_API_KEY:
        return call_gemini(system, user, max_tokens, fast=fast)
    raise RuntimeError("no AI key set")


def keywords(text: str):
    return [w for w in re.findall(r"[a-z][a-z'-]+", text.lower()) if w not in STOPWORDS and len(w) > 2]


def offline_answer(question: str, transcript: str) -> str:
    q = set(keywords(question))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript)
                 if len(s.split()) > 3 and not re.search(r"\b(third|3rd)[\s-]?(eye|i)\b", s, re.I)]
    if not q or not sentences:
        return "I haven't heard enough yet to answer that. Add an AI key for general questions."
    scored = sorted(sentences, key=lambda s: len(q & set(keywords(s))), reverse=True)
    best = [s for s in scored[:2] if q & set(keywords(s))]
    if not best:
        return "That hasn't come up yet. Add an AI key for general questions."
    return "From what I heard: " + " ".join(best)


class Assistant:
    SYSTEM = ("You are Third Eye, a discreet AI assistant in the user's earpiece. You can hear what is "
              "happening around them. The user may have ADHD or be tired, so answer in 1-3 short, clear "
              "spoken sentences. No lists, no markdown. Use what you heard when it is relevant, otherwise "
              "answer from general knowledge.")

    def __init__(self):
        self.provider = config.ai_provider()
        self.online = bool(self.provider)
        print(f"[assistant] {self.provider + ' API' if self.online else 'offline mode (no AI key set)'}")

    def answer(self, question: str, recent_transcript: str, slide_text: str = "", situation: str = "",
               tasks=None) -> str:
        quick = quick_answer(question, recent_transcript, tasks)
        if quick:
            return quick
        if self.online:
            try:
                task_lines = "\n".join(f"- {t['task']}" + (f" (due {t['due']})" if t.get("due") else "")
                                        for t in (tasks or []) if not t.get("done")) or "(none)"
                prompt = (f"Situation: {situation or 'unknown'}\n"
                          f"Now: {time.strftime('%A %Y-%m-%d %H:%M')}\n\n"
                          f"What you heard recently:\n{recent_transcript or '(nothing yet)'}\n\n"
                          f"Text on the screen or board:\n{slide_text or '(none)'}\n\n"
                          f"The user's open tasks:\n{task_lines}\n\n"
                          f"User: {question}")
                t0 = time.time()
                answer = call_ai(self.SYSTEM, prompt, max_tokens=200, fast=True)
                print(f"[assistant] answered in {time.time() - t0:.1f}s")
                return answer
            except Exception as e:
                print(f"[assistant] API error, using offline answer: {e}")
        return offline_answer(question, recent_transcript)


def quick_answer(question: str, transcript: str, tasks=None) -> str:
    """Things it can answer without an AI: time, date, tasks, a recap."""
    q = question.lower()
    if re.search(r"\bwhat time\b|\bthe time\b", q):
        return time.strftime("It's %I:%M %p.").replace(" 0", " ")
    if re.search(r"\b(what('s| is) the date|what day|today's date)\b", q):
        return time.strftime("It's %A, %B %d.").replace(" 0", " ")
    if re.search(r"\b(my tasks|to ?do|what do i (need|have) to do|deadlines?|reminders?)\b", q):
        open_tasks = [t for t in (tasks or []) if not t.get("done")]
        if not open_tasks:
            return "You have no open tasks from this session."
        items = "; ".join(t["task"] + (f", due {t['due']}" if t.get("due") else "") for t in open_tasks[:4])
        return f"You have {len(open_tasks)} open: {items}."
    if re.search(r"\b(what did i miss|catch me up|recap|summari[sz]e|what (was|were) (they|we|he|she) (saying|talking about))\b", q):
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", transcript) if len(s.split()) > 4]
        return ("Lately: " + " ".join(sentences[-3:])) if sentences else "Nothing much has been said yet."
    return ""


# ---------- Text to speech (the earpiece "voice") ----------
_speak_lock = threading.Lock()


def _neural_voice(text: str) -> bool:
    """Speak with a Microsoft neural voice through edge-tts. Needs internet; returns False if it can't."""
    if not config.VOICE:
        return False
    try:
        import asyncio
        import io

        import av
        import edge_tts
        import numpy as np
        import sounddevice as sd
    except ImportError:
        return False
    try:
        async def fetch():
            buf = bytearray()
            tts = edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE, pitch=config.VOICE_PITCH)
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            return bytes(buf)
        mp3 = asyncio.run(fetch())
        if not mp3:
            return False
        with av.open(io.BytesIO(mp3)) as f:
            stream = f.streams.audio[0]
            rate = stream.rate
            pcm = np.concatenate([fr.to_ndarray().reshape(-1) for fr in f.decode(stream)]).astype(np.float32)
        if pcm.dtype != np.float32 or np.abs(pcm).max() > 1.5:
            pcm = pcm / 32768.0
        sd.play(pcm, rate)
        sd.wait()
        return True
    except Exception as e:
        print(f"[speak] neural voice unavailable ({e}), using the system voice")
        return False


def speak(text: str):
    """Say text out loud without freezing the app. Neural voice first, then the OS voice."""
    def _run():
        with _speak_lock:
            if text.strip() and _neural_voice(text):
                return
            system = platform.system()
            try:
                if system == "Darwin":
                    subprocess.run(["say", text], check=False)
                    return
                if system == "Linux" and shutil.which("espeak"):
                    subprocess.run(["espeak", text], check=False)
                    return
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.say(text)
                    engine.runAndWait()
                except ImportError:
                    if system != "Windows":
                        raise
                    # Windows built-in voice, no install needed
                    safe = text.replace("'", "''")
                    subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "Add-Type -AssemblyName System.Speech; "
                                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"],
                                   check=False)
            except Exception as e:
                print(f"[speak] (no voice available: {e}) -> {text}")
    threading.Thread(target=_run, daemon=True).start()
