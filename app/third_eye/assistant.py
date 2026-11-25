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


def _gemini_request(model, system, user, max_tokens, timeout, extra_parts=None, search=False, key=None):
    key = key or config.GEMINI_API_KEY
    gen = {"maxOutputTokens": max_tokens * 4 + 1024, "temperature": 0.4}
    # Thinking makes answers slower; switch it off where the model allows.
    if model.startswith("gemini-2.5-flash") and model not in _no_thinking_cfg:
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": (extra_parts or []) + [{"text": user}]}],
            "generationConfig": gen}
    if search:
        body["tools"] = [{"google_search": {}}]
    req = urllib.request.Request(
        gemini_url(model, key),
        data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": key, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


_no_search = set()          # models that refused the Google Search tool


_key_rest = {}              # key -> time it can be tried again after hitting its limit
RECENT = re.compile(r"\b(today|tonight|now|right now|currently|current|latest|recent|news|this (week|month|year)|"
                    r"weather|forecast|score|scores|won|winning|game|stock|price|cost|release|released|election|"
                    r"who is the|president|prime minister|ceo|20\d\d)\b", re.I)


def needs_search(question: str) -> bool:
    return bool(RECENT.search(question))


def _keys_to_try():
    keys = config.GEMINI_API_KEYS or ([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])
    now = time.time()
    fresh = [k for k in keys if _key_rest.get(k, 0) <= now]
    return fresh or sorted(keys, key=lambda k: _key_rest.get(k, 0))[:1]


def call_gemini(system: str, user: str, max_tokens: int = 600, fast: bool = False,
                search: bool = False, extra_parts=None) -> str:
    """Google Gemini API (free tier available), standard library only. Moves to the next key in the
    queue when one hits its limit. search=True lets it look things up."""
    last_error = None
    for key in _keys_to_try():
        try:
            text = _call_gemini_key(key, system, user, max_tokens, fast, search, extra_parts)
            if key != config.GEMINI_API_KEY:
                config.GEMINI_API_KEY = key
                print(f"[assistant] switched to the next Gemini key in the queue")
            return text
        except RuntimeError as e:
            last_error = e
            if "limit" in str(e).lower():
                _key_rest[key] = time.time() + 60
                continue
            raise
    raise last_error or RuntimeError("no Gemini key set")


def _call_gemini_key(key, system, user, max_tokens, fast, search, extra_parts):
    if key not in _endpoint:
        check_gemini_key(key)
    mode = "fast" if fast else "smart"
    models = [config.GEMINI_MODEL] if config.GEMINI_MODEL and not fast else []
    models = list(dict.fromkeys(([_last_good[mode]] if mode in _last_good else []) + models
                                + (GEMINI_FAST if fast else GEMINI_SMART)))
    timeout = 8 if fast else 60
    last_error = None
    for attempt in range(2 if not fast else 1):
        for model in models:
            use_search = search and model not in _no_search
            try:
                try:
                    data = _gemini_request(model, system, user, max_tokens, timeout, extra_parts, use_search, key)
                except urllib.error.HTTPError as e:
                    if e.code == 400 and use_search:
                        _no_search.add(model)
                        data = _gemini_request(model, system, user, max_tokens, timeout, extra_parts, key=key)
                    elif e.code == 400 and model not in _no_thinking_cfg:
                        _no_thinking_cfg.add(model)
                        data = _gemini_request(model, system, user, max_tokens, timeout, extra_parts, key=key)
                    else:
                        raise
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="ignore")[:300]
                if e.code in (404, 500, 503, 504):
                    last_error = f"{model}: {'not available' if e.code == 404 else 'busy right now'}"
                    continue
                if e.code == 429:
                    if use_search:
                        try:
                            data = _gemini_request(model, system, user, max_tokens, timeout, extra_parts, key=key)
                        except Exception:
                            last_error = "Gemini free-tier limit reached; wait a minute and try again"
                            continue
                    else:
                        last_error = "Gemini free-tier limit reached; wait a minute and try again"
                        continue
                else:
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
        if not fast:
            time.sleep(1)
    raise RuntimeError(last_error or "Gemini didn't answer")


def call_ai(system: str, user: str, max_tokens: int = 600, fast: bool = False, search: bool = False) -> str:
    """Use whichever AI has a key: Claude first, then Gemini. fast=True for live questions."""
    if config.ANTHROPIC_API_KEY:
        return call_claude(system, user, max_tokens)
    if config.GEMINI_API_KEY:
        return call_gemini(system, user, max_tokens, fast=fast, search=search)
    raise RuntimeError("no AI key set")


def gemini_transcribe(wav_bytes: bytes, context: str = "") -> str:
    """Speech to text with Gemini. Raises on any failure so the caller can fall back to Whisper."""
    import base64
    prompt = ("Transcribe the speech in this audio exactly as spoken, in English. Output only the words. "
              "If there is no clear speech, output nothing.")
    if context:
        prompt += f" The speech continues from: \"{context[-200:]}\""
    part = {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav_bytes).decode()}}
    text = call_gemini("You are an accurate speech-to-text engine.", prompt, max_tokens=300, fast=True,
                       extra_parts=[part])
    text = text.strip().strip('"')
    return "" if text.lower() in ("", "nothing", "(no speech)", "[no speech]", "no speech") else text


def keywords(text: str):
    return [w for w in re.findall(r"[a-z][a-z'-]+", text.lower()) if w not in STOPWORDS and len(w) > 2]


def offline_answer(question: str, transcript: str) -> str:
    q = set(keywords(question))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript)
                 if len(s.split()) > 3 and not re.search(r"\b(third|3rd)[\s-]?(eye|i)\b", s, re.I)]
    about_talk = re.search(r"\b(said|say|says|saying|mention|mentioned|talk|talking|told|lecture|meeting|class|professor|they|he|she)\b",
                           question, re.I)
    scored = sorted(sentences, key=lambda s: len(q & set(keywords(s))), reverse=True)
    best = [s for s in scored[:2] if len(q & set(keywords(s))) >= 2]
    if about_talk and best:
        return "From what I heard: " + " ".join(best)
    return "I need an AI key for that. Click AI key and paste one."


class Assistant:
    SYSTEM = ("You are Third Eye, an assistant speaking in the user's earpiece. Answer exactly what they asked, "
              "directly, in one or two short sentences. Lead with the answer itself. Use general knowledge for "
              "general questions, and search the web for anything recent (news, scores, weather, prices, dates). Never describe the situation, summarize what you heard, or mention the "
              "background unless the question is about it. If the question is garbled, answer the most likely "
              "meaning. No lists, no markdown, no filler.")

    def __init__(self):
        self.provider = config.ai_provider()
        self.online = bool(self.provider)
        self.session_folder = None
        print(f"[assistant] {self.provider + ' API' if self.online else 'offline mode (no AI key set)'}")

    def answer(self, question: str, recent_transcript: str, slide_text: str = "", situation: str = "",
               tasks=None, fallback: bool = True) -> str:
        """fallback=False raises when the AI call fails instead of answering from the transcript."""
        quick = quick_answer(question, recent_transcript, tasks)
        if quick:
            return quick
        past, asks_past = "", False
        try:
            import memory
            asks_past = memory.about_the_past(question)
            if asks_past:
                past = memory.search(question, skip_folder=self.session_folder)
        except Exception as e:
            print(f"[memory] {e}")
        if not self.online and past:
            return "Earlier: " + past.splitlines()[0].split("] ", 1)[-1]
        if self.online:
            try:
                task_lines = "\n".join(f"- {t['task']}" + (f" (due {t['due']})" if t.get("due") else "")
                                        for t in (tasks or []) if not t.get("done")) or "(none)"
                prompt = (f"QUESTION: {question}\n\n"
                          "Background, only for questions about what was said, the room, or their tasks:\n"
                          f"- Now: {time.strftime('%A %Y-%m-%d %H:%M')}\n"
                          f"- Situation: {situation or 'unknown'}\n"
                          f"- Recently heard (speech-to-text, may be wrong): {recent_transcript[-1500:] or '(nothing)'}\n"
                          f"- On screen: {slide_text[-500:] or '(nothing)'}\n"
                          f"- Open tasks: {task_lines}\n"
                          + (f"- Earlier sessions (matching lines):\n{past}\n" if past else
                             "- Earlier sessions: nothing matching was found. If the QUESTION is about an "
                             "earlier session, say you don't have that.\n" if asks_past else "")
                          + "\nAnswer the QUESTION.")
                t0 = time.time()
                answer = call_ai(self.SYSTEM, prompt, max_tokens=150, fast=True,
                                 search=config.WEB_SEARCH and needs_search(question))
                print(f"[assistant] answered in {time.time() - t0:.1f}s")
                return answer
            except Exception as e:
                if not fallback:
                    raise
                print(f"[assistant] API error, using offline answer: {e}")
                if "limit" in str(e).lower():
                    return "Gemini's free limit is used up for the moment. Ask again in a minute."
                if "reach" in str(e).lower():
                    return "I can't reach Gemini right now. Check the internet and ask again."
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
