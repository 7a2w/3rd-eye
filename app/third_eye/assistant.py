"""
Live assistant: you ask a question out loud, it answers out loud.

Uses Claude (ANTHROPIC_API_KEY) or Google Gemini (GEMINI_API_KEY, which has a free tier).
Without a key it falls back to searching the lecture transcript for the most relevant sentences,
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
GEMINI_FAST = ["gemini-2.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash"]
GEMINI_SMART = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
_last_good = {}            # "fast"/"smart" -> model that answered last time (tried first next time)
_no_thinking_cfg = set()   # models that rejected the thinking setting


def _gemini_request(model, system, user, max_tokens, timeout):
    gen = {"maxOutputTokens": max_tokens * 4 + 1024, "temperature": 0.4}
    # Thinking makes answers slower. 2.5 Flash-Lite already has it off; ask the others to keep it low.
    if model != "gemini-2.5-flash-lite" and model not in _no_thinking_cfg:
        gen["thinkingConfig"] = {"thinkingLevel": "low"}
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def call_gemini(system: str, user: str, max_tokens: int = 600, fast: bool = False) -> str:
    """Google Gemini API (free tier available), standard library only."""
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
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript) if len(s.split()) > 3]
    if not q or not sentences:
        return "I don't have enough from the lecture yet to answer that."
    scored = sorted(sentences, key=lambda s: len(q & set(keywords(s))), reverse=True)
    best = [s for s in scored[:2] if q & set(keywords(s))]
    if not best:
        return "The professor hasn't mentioned that yet in this lecture."
    return "From the lecture: " + " ".join(best)


class Assistant:
    SYSTEM = ("You are a discreet study assistant speaking through an earpiece to a university student "
              "during a lecture. The student may have ADHD or be tired, so answer in 1-3 short, clear "
              "spoken sentences. No lists, no markdown. Use the lecture transcript when it is relevant; "
              "if you add general knowledge, keep it consistent with what the professor said.")

    def __init__(self):
        self.provider = config.ai_provider()
        self.online = bool(self.provider)
        print(f"[assistant] {self.provider + ' API' if self.online else 'offline mode (no AI key set)'}")

    def answer(self, question: str, recent_transcript: str, slide_text: str = "") -> str:
        if self.online:
            try:
                prompt = (f"Recent lecture transcript:\n{recent_transcript or '(nothing yet)'}\n\n"
                          f"Text on the current slide/board:\n{slide_text or '(none)'}\n\n"
                          f"Student's question: {question}")
                t0 = time.time()
                answer = call_ai(self.SYSTEM, prompt, max_tokens=200, fast=True)
                print(f"[assistant] answered in {time.time() - t0:.1f}s")
                return answer
            except Exception as e:
                print(f"[assistant] API error, using offline answer: {e}")
        return offline_answer(question, recent_transcript)


# ---------- Text to speech (the earpiece "voice") ----------
_speak_lock = threading.Lock()


def speak(text: str):
    """Say text out loud without freezing the app. Uses the OS voice; pyttsx3 if installed."""
    def _run():
        with _speak_lock:
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
