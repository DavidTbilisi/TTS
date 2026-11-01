"""Desktop notification when a read starts, saying how long the audio will last.

Linux only (``notify-send`` from libnotify). Hotkey / ``tts-ka cb`` runs have no
visible terminal, so this is the only place the user learns how long to wait.

Disable with ``--no-notify``, ``TTS_KA_NOTIFY=0`` or ``"notify": false`` in the
config file.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from typing import Optional

# Measured edge-tts speaking speed at +0% rate, pauses included (words/minute).
# Georgian and Russian words are long, so a single WPM would be ~40% off.
SPEECH_WPM = {"en": 180, "en-US": 180, "ru": 130, "ka": 115, "ka-m": 115}
DEFAULT_SPEECH_WPM = 150

_RATE_RE = re.compile(r"^([+-]\d+)%$")
_NOTIFY_TIMEOUT_MS = 10000
# Same tag on every notification → a new read replaces the previous bubble.
_SYNC_HINT = "string:x-canonical-private-synchronous:tts-ka"


def rate_factor(rate: Optional[str]) -> float:
    """``"+30%"`` → 1.3, ``"-50%"`` → 0.5; anything unparsable → 1.0."""
    m = _RATE_RE.match((rate or "").strip())
    if not m:
        return 1.0
    return max(0.1, 1.0 + int(m.group(1)) / 100.0)


def estimate_speech_seconds(text: str, lang: str, rate: Optional[str] = None) -> float:
    """Roughly how long *text* takes to speak in *lang* at *rate*."""
    words = len(text.split())
    wpm = SPEECH_WPM.get(lang, DEFAULT_SPEECH_WPM) * rate_factor(rate)
    return words / wpm * 60.0


def format_duration(seconds: float) -> str:
    """``42`` → ``"42 s"``, ``430`` → ``"7 min"``, ``4500`` → ``"1 h 15 min"``."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{max(1, seconds)} s"
    minutes = int(round(seconds / 60.0))
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if minutes else f"{hours} h"


def notifications_enabled() -> bool:
    """Linux, not switched off by ``TTS_KA_NOTIFY=0``, and ``notify-send`` exists."""
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("TTS_KA_NOTIFY", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return shutil.which("notify-send") is not None


def send_notification(summary: str, body: str = "") -> bool:
    """Show a desktop notification. Never raises; returns whether it was sent."""
    exe = shutil.which("notify-send")
    if not exe:
        return False
    argv = [exe, "-a", "TTS_ka", "-i", "audio-speakers",
            "-t", str(_NOTIFY_TIMEOUT_MS), "-h", _SYNC_HINT, summary]
    if body:
        argv.append(body)
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def reading_started_message(text: str, lang: str, rate: Optional[str] = None,
                            now: Optional[float] = None) -> tuple:
    """(summary, body) for the start notification."""
    seconds = estimate_speech_seconds(text, lang, rate)
    words = len(text.split())
    summary = f"🔊 Reading ~{format_duration(seconds)}"
    body = f"{words:,} words · {lang}"
    if seconds >= 60:
        end = time.localtime((time.time() if now is None else now) + seconds)
        body += f" · done ≈ {time.strftime('%H:%M', end)}"
    return summary, body


def notify_reading_started(text: str, lang: str, rate: Optional[str] = None) -> bool:
    """Tell the desktop how long this read will take (no-op when disabled)."""
    if not notifications_enabled():
        return False
    return send_notification(*reading_started_message(text, lang, rate))
