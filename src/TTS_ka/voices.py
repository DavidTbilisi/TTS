"""Voice catalog for TTS_ka.

A curated subset of Microsoft Edge neural voices, indexed by id. The catalog
backs ``--list-voices`` and ``--voice ID``; the existing
``constants.VOICE_MAP`` continues to map a language code to that language's
default voice for callers that don't care about specific voice selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Voice:
    id: str
    lang: str          # short code (ka, ru, en) used by --lang
    locale: str        # full locale (en-GB, ka-GE, ...)
    gender: str        # "Female" | "Male"
    display_name: str  # human-friendly, e.g. "Sonia"


_VOICES: Tuple[Voice, ...] = (
    # Georgian
    Voice("ka-GE-EkaNeural",       "ka", "ka-GE", "Female", "Eka"),
    Voice("ka-GE-GiorgiNeural",    "ka", "ka-GE", "Male",   "Giorgi"),

    # Russian
    Voice("ru-RU-SvetlanaNeural",  "ru", "ru-RU", "Female", "Svetlana"),
    Voice("ru-RU-DmitryNeural",    "ru", "ru-RU", "Male",   "Dmitry"),

    # English — UK
    Voice("en-GB-SoniaNeural",     "en", "en-GB", "Female", "Sonia"),
    Voice("en-GB-RyanNeural",      "en", "en-GB", "Male",   "Ryan"),

    # English — US
    Voice("en-US-JennyNeural",     "en", "en-US", "Female", "Jenny"),
    Voice("en-US-AriaNeural",      "en", "en-US", "Female", "Aria"),
    Voice("en-US-GuyNeural",       "en", "en-US", "Male",   "Guy"),
    Voice("en-US-SteffanNeural",   "en", "en-US", "Male",   "Steffan"),

    # English — AU
    Voice("en-AU-NatashaNeural",   "en", "en-AU", "Female", "Natasha"),
    Voice("en-AU-WilliamNeural",   "en", "en-AU", "Male",   "William"),
)

# Lookup tables built once at import time.
VOICES_BY_ID: Dict[str, Voice] = {v.id: v for v in _VOICES}


def all_voices() -> List[Voice]:
    """Return every voice in the catalog (stable order)."""
    return list(_VOICES)


def voices_for_lang(lang: str) -> List[Voice]:
    """Return all voices whose short language code matches *lang*."""
    return [v for v in _VOICES if v.lang == lang]


def get_voice(voice_id: str) -> Optional[Voice]:
    """Return the catalog entry for *voice_id*, or None if unknown."""
    return VOICES_BY_ID.get(voice_id)


def lang_for_voice(voice_id: str) -> Optional[str]:
    """Return the short language code (ka/ru/en) for *voice_id*, or None."""
    v = VOICES_BY_ID.get(voice_id)
    return v.lang if v else None


def validate_lang_voice(lang: str, voice: Optional[str]) -> Optional[str]:
    """Return an error message when *lang* or *voice* is unsupported, else None.

    Shared by the REST and MCP servers so bad input fails up front instead of
    in every later synthesis call.
    """
    from .constants import VOICE_MAP

    if lang not in VOICE_MAP:
        return f"invalid lang {lang!r} (use one of: {', '.join(VOICE_MAP)})"
    if voice and get_voice(voice) is None:
        return f"unknown voice {voice!r} (see list_voices)"
    return None


def format_table(voices: List[Voice]) -> str:
    """Render *voices* as a fixed-width table suitable for terminal output."""
    if not voices:
        return "(no voices match)"
    headers = ("ID", "Lang", "Locale", "Gender", "Name")
    rows = [
        (v.id, v.lang, v.locale, v.gender, v.display_name) for v in voices
    ]
    widths = [
        max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)
    ]
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines.extend(fmt.format(*r) for r in rows)
    return "\n".join(lines)


# Short preview phrase per language used by --preview-voice.
PREVIEW_PHRASE: Dict[str, str] = {
    "ka": "გამარჯობა, ეს არის ხმის ნიმუში.",
    "ru": "Здравствуйте, это образец голоса.",
    "en": "Hello, this is a voice sample.",
}
