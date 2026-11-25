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
WHISPER_MODEL = os.environ.get("THIRD_EYE_WHISPER", "base.en")
SAMPLE_RATE = 16000          # Whisper expects 16 kHz mono
CHUNK_SECONDS = 8            # how much lecture audio to transcribe at a time
QUESTION_SECONDS = 6         # how long push-to-talk listens for your question
SILENCE_RMS = 0.004          # chunks quieter than this are skipped (tune for your mic)

# ---------- Camera (the Third Eye camera) ----------
CAMERA_INDEX = 0             # 0 = built-in webcam; try 1 for a USB camera
SLIDE_CHANGE_THRESHOLD = 3   # % of the picture that must change to count as a new slide
SLIDE_STABLE_FRAMES = 15     # frames the new view must stay still before we snapshot it
MIN_SECONDS_BETWEEN_SLIDES = 5

# ---------- AI assistant ----------
# Set ONE of these environment variables to turn on AI answers and AI study sheets:
#   ANTHROPIC_API_KEY  -> Claude (paid, pay-as-you-go)
#   GEMINI_API_KEY     -> Google Gemini (has a FREE tier: get a key at aistudio.google.com)
# If both are set, Claude is used. With neither, the program still works using simple offline methods.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("THIRD_EYE_MODEL", "claude-sonnet-5-5")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("THIRD_EYE_GEMINI_MODEL", "")   # optional: force a model for study sheets


def ai_provider() -> str:
    """Which AI is switched on: "Claude", "Gemini" or "" (offline)."""
    if ANTHROPIC_API_KEY:
        return "Claude"
    if GEMINI_API_KEY:
        return "Gemini"
    return ""
CONTEXT_MINUTES = 5          # how much recent lecture the assistant "remembers" for live questions

# ---------- Study sheet reminders ----------
REVIEW_DAYS = [1, 3, 7]      # spaced-repetition review reminders (days after lecture)
REMINDER_HOUR = 18           # reminders fire at 6 pm local time
