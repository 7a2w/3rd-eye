"""
User settings from the dashboard, kept in ~/.third_eye_settings.json and applied onto config.
"""
import json
import os
from pathlib import Path

import config

PATH = Path.home() / ".third_eye_settings.json"

VOICES = ["en-GB-LibbyNeural", "en-GB-SoniaNeural", "en-GB-MaisieNeural", "en-GB-RyanNeural",
          "en-GB-ThomasNeural", "en-US-AvaMultilingualNeural", "en-US-EmmaMultilingualNeural",
          "en-US-AndrewMultilingualNeural", ""]

# name -> (config attribute or None, type)
FIELDS = {
    "voice": ("VOICE", str),
    "voice_rate": ("VOICE_RATE", str),
    "auto_speak": ("AUTO_SPEAK", bool),
    "auto_speak_gap": ("AUTO_SPEAK_GAP", int),
    "think_seconds": ("THINK_SECONDS", int),
    "auto_end_minutes": ("AUTO_END_MINUTES", int),
    "context_minutes": ("CONTEXT_MINUTES", int),
    "slides_from_builtin_camera": ("SLIDES_FROM_BUILTIN_CAMERA", bool),
    "review_days": ("REVIEW_DAYS", list),
    "reminder_hour": ("REMINDER_HOUR", int),
    "obsidian_vault": (None, str),
}
LIMITS = {"auto_speak_gap": (5, 600), "think_seconds": (10, 600), "auto_end_minutes": (0, 240),
          "context_minutes": (1, 60), "reminder_hour": (0, 23)}


def _rate(v):
    n = int(str(v).strip().rstrip("%") or 0)
    n = max(-30, min(40, n))
    return f"{n:+d}%"


def _clean(name, value):
    attr, kind = FIELDS[name]
    if name == "voice_rate":
        return _rate(value)
    if name == "voice":
        value = str(value or "").strip()
        if value not in VOICES:
            raise ValueError(f"unknown voice {value!r}")
        return value
    if kind is bool:
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
    if kind is int:
        lo, hi = LIMITS.get(name, (0, 10 ** 6))
        return max(lo, min(hi, int(float(value))))
    if kind is list:
        parts = value if isinstance(value, list) else str(value).replace(";", ",").split(",")
        days = sorted({int(p) for p in (str(x).strip() for x in parts) if p.isdigit() and 0 < int(p) <= 365})
        if not days:
            raise ValueError("no review days")
        return days
    value = str(value or "").strip()
    if value and not Path(value).expanduser().is_dir():
        raise ValueError(f"no folder {value!r}")
    return value


def current():
    out = {name: getattr(config, attr) for name, (attr, _) in FIELDS.items() if attr}
    out["obsidian_vault"] = os.environ.get("OBSIDIAN_VAULT", "") if _saved().get("obsidian_vault") else ""
    out["review_days"] = list(out["review_days"])
    return out


def _saved():
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def apply(values):
    good = {}
    for name, value in values.items():
        if name not in FIELDS:
            continue
        try:
            value = _clean(name, value)
        except (TypeError, ValueError):
            continue
        attr = FIELDS[name][0]
        if attr:
            setattr(config, attr, value)
        elif value:
            os.environ["OBSIDIAN_VAULT"] = value
        else:
            os.environ.pop("OBSIDIAN_VAULT", None)
        good[name] = value
    return good


def load():
    return apply({k: v for k, v in _saved().items() if k != "obsidian_vault" or v})


def save(partial):
    good = apply(partial)
    data = _saved()
    data.update(good)
    PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return current()
