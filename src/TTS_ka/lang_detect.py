"""Pick a language for ``--lang auto`` from the script the text is written in.

Georgian, Cyrillic and Latin letters occupy disjoint Unicode ranges, so a
letter count settles ka / ru / en without a model or extra dependency. It
cannot tell two languages that share a script apart (a German text reads as
``en``); a language added to ``VOICE_MAP`` in an existing script is reachable
only through an explicit ``--lang``.

Detection runs per synthesis call (``EdgeTTSGenerator.generate``), so a long
text is decided chunk by chunk and ``--live`` / MCP streams sentence by
sentence: a Georgian paragraph followed by an English one switches voice.
"""

from __future__ import annotations

from .constants import AUTO_LANG

# Script → language whose default voice reads it. Order breaks ties.
SCRIPT_LANG = {"georgian": "ka", "cyrillic": "ru", "latin": "en"}

DEFAULT_FALLBACK = "en"


def _script(ch: str) -> str:
    cp = ord(ch)
    # Mkhedruli + Asomtavruli/Nuskhuri, Mtavruli capitals, Nuskhuri supplement.
    if 0x10A0 <= cp <= 0x10FF or 0x1C90 <= cp <= 0x1CBF or 0x2D00 <= cp <= 0x2D2F:
        return "georgian"
    if 0x0400 <= cp <= 0x052F:
        return "cyrillic"
    if ch.isalpha() and (cp < 0x80 or 0x00C0 <= cp <= 0x024F):
        return "latin"
    return ""


def detect_lang(text: str, fallback: str = DEFAULT_FALLBACK) -> str:
    """Return the language whose script has the most letters in *text*.

    Text without any Georgian, Cyrillic or Latin letter (digits, punctuation,
    emoji) returns *fallback*.
    """
    counts = dict.fromkeys(SCRIPT_LANG, 0)
    for ch in text:
        script = _script(ch)
        if script:
            counts[script] += 1
    best = max(counts, key=counts.__getitem__)
    return SCRIPT_LANG[best] if counts[best] else fallback


def resolve_lang(lang: str, text: str) -> str:
    """Return *lang*, or the language detected from *text* when it is ``auto``."""
    return detect_lang(text) if lang == AUTO_LANG else lang
