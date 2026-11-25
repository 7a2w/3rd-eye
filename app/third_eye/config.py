"""
Settings for the Third Eye earpiece prototype.
Change these to fit your laptop / demo. Most can also be set from the command line.
"""
import os
from pathlib import Path

# ---------- Where notes go ("personal cloud") ----------
# Point this at a folder your phone syncs, e.g.
#   Windows: r"C:\Users\you\Google Drive\ThirdEye"
#   macOS:   "~/Library/CloudStorage/GoogleDrive-you@gmail.com/My Drive/ThirdEye"
#   or a Dropbox / OneDrive / iCloud Drive / Nextcloud folder.
SYNC_FOLDER = Path(os.environ.get("THIRD_EYE_SYNC", "./ThirdEyeNotes")).expanduser()

# ---------- Dashboard ----------
DASHBOARD_PORT = 8000        # the dashboard opens at http://localhost:8000

# ---------- Speech to text ----------
# faster-whisper model sizes: "tiny.en", "base.en", "small.en", "medium.en"
# tiny/base are fast enough for most laptops on CPU; small is more accurate.
WHISPER_MODEL = os.environ.get("THIRD_EYE_WHISPER", "small.en")
WHISPER_BEAM = 5             # wider search = fewer misheard words (1 is fastest)
SAMPLE_RATE = 16000          # Whisper expects 16 kHz mono
CHUNK_SECONDS = 8            # how much lecture audio to transcribe at a time
QUESTION_SECONDS = 6         # how long push-to-talk listens for your question
SILENCE_RMS = 0.004          # chunks quieter than this are skipped (tune for your mic)

# ---------- Camera (the Third Eye camera) ----------
CAMERA_INDEX = 0             # 0 = built-in webcam; try 1 for a USB camera
SLIDE_CHANGE_THRESHOLD = 3   # % of the picture that must change to count as a new slide
SLIDE_STABLE_FRAMES = 15     # frames the new view must stay still before we snapshot it
MIN_SECONDS_BETWEEN_SLIDES = 5
SLIDES_FROM_BUILTIN_CAMERA = False   # camera 0 usually faces you; set True if it faces the board

# ---------- AI assistant ----------
# Set ONE of these environment variables to turn on AI answers and AI study sheets:
#   ANTHROPIC_API_KEY  -> Claude (paid, pay-as-you-go)
#   GEMINI_API_KEY     -> Google Gemini (has a FREE tier: get a key at aistudio.google.com)
# If both are set, Claude is used. With neither, the program still works using simple offline methods.
def _saved_key(name):
    _load_key_file()
    """A key from this process, or on Windows one saved with setx after this terminal was opened."""
    value = os.environ.get(name, "")
    if not value and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                value = winreg.QueryValueEx(k, name)[0]
        except OSError:
            value = ""
    return value.strip()


AI_MODEL = os.environ.get("THIRD_EYE_MODEL", "claude-sonnet-5-5")
GEMINI_MODEL = os.environ.get("THIRD_EYE_GEMINI_MODEL", "")   # optional: force a model for study sheets


ENV_NAMES = {"gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def save_key(provider: str, key: str):
    """Use a key now and keep it for next time (the user's environment on Windows, ~/.third_eye_keys elsewhere)."""
    global GEMINI_API_KEY, ANTHROPIC_API_KEY
    name = ENV_NAMES[provider]
    key = key.strip()
    os.environ[name] = key
    if provider == "gemini":
        GEMINI_API_KEY = key
    else:
        ANTHROPIC_API_KEY = key
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            if key:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, key)
            else:
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass
    else:
        path = Path.home() / ".third_eye_keys"
        lines = [l for l in (path.read_text().splitlines() if path.exists() else []) if not l.startswith(name + "=")]
        if key:
            lines.append(f"{name}={key}")
        path.write_text("\n".join(lines) + "\n")
        path.chmod(0o600)


def _load_key_file():
    path = Path.home() / ".third_eye_keys"
    if os.name == "nt" or not path.exists():
        return
    for line in path.read_text().splitlines():
        name, _, value = line.partition("=")
        if name in ENV_NAMES.values() and value and not os.environ.get(name):
            os.environ[name] = value


ANTHROPIC_API_KEY = _saved_key("ANTHROPIC_API_KEY")
GEMINI_API_KEY = _saved_key("GEMINI_API_KEY") or _saved_key("GOOGLE_API_KEY")


def ai_provider() -> str:
    """Which AI is switched on: "Claude", "Gemini" or "" (offline)."""
    if ANTHROPIC_API_KEY:
        return "Claude"
    if GEMINI_API_KEY:
        return "Gemini"
    return ""


CONTEXT_MINUTES = 5          # how much recent speech the assistant "remembers" for live questions

# ---------- Always-on assistant ----------
AUTO_START = True            # start listening as soon as the speech model is ready (--manual turns this off)
THINK_SECONDS = 45           # how often it works out the situation, tasks and things to explain
THINK_MIN_WORDS = 25         # new words needed before it thinks again
AUTO_SPEAK = True            # say tasks and explanations out loud without being asked
AUTO_SPEAK_GAP = 45          # seconds between unprompted remarks
AUTO_END_MINUTES = 10        # end the session after this much quiet (0 = never)
AUTO_RESTART_SECONDS = 30    # after an automatic end, start a new session this many seconds later

# ---------- Device (earpiece buttons, clips, offline queue) ----------
CLIP_SECONDS = 30            # rolling buffer length; saving a clip copies this much audio and video
CLIP_FPS = 2                 # camera frames kept per second in the buffer
CLIP_KEY_PHRASES = [                      # moments worth keeping; a clip is saved as soon as one is heard
    "due", "exam", "midterm", "final", "assignment", "homework", "deadline", "quiz", "test", "submit",
    "important", "remember", "don't forget", "dont forget", "make sure", "pay attention", "key point", "will be on",
    "write this down", "note that", "definition", "formula", "the answer is", "we decided", "agreed",
    "action item", "next steps", "meeting at", "appointment", "phone number", "email me", "address is",
    "by tomorrow", "by friday", "next week", "tonight"]
CLIP_KEY_GAP = 20            # at most one key-phrase clip per this many seconds
OFFLINE_CHECK_SECONDS = 5    # how often the offline queue checks for internet
ASK_BEFORE_OBSIDIAN = True   # explain vault changes and wait for approval before writing them

# ---------- Voice ----------
# A calm British neural voice via edge-tts (free, needs internet). Others: en-GB-SoniaNeural,
# en-GB-MaisieNeural, en-US-AvaMultilingualNeural. Set THIRD_EYE_VOICE="" to use the built-in system voice.
VOICE = os.environ.get("THIRD_EYE_VOICE", "en-GB-LibbyNeural")
VOICE_RATE = "+20%"          # brisk, like a person talking
VOICE_PITCH = "+0Hz"

# ---------- Study sheet reminders ----------
REVIEW_DAYS = [1, 3, 7]      # spaced-repetition review reminders (days after lecture)
REMINDER_HOUR = 18           # reminders fire at 6 pm local time

try:
    import settings_store
    settings_store.load()
except Exception as e:
    print(f"[settings] not loaded: {e}")
