"""Markdown reader — strips formatting syntax via lightweight regex.

This is deliberately not a full markdown parser; it produces *spoken-friendly*
text by removing structural marks that would otherwise be read aloud.
"""

from __future__ import annotations

import re

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HR = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_ITAL = re.compile(r"\*([^*]+)\*|_([^_]+)_")


def _strip(md: str) -> str:
    md = _FENCED_CODE.sub(" ", md)
    md = _IMAGE.sub("", md)
    md = _LINK.sub(r"\1", md)        # keep link text
    md = _INLINE_CODE.sub(r"\1", md)
    md = _HEADING.sub("", md)
    md = _BLOCKQUOTE.sub("", md)
    md = _HR.sub("", md)
    md = _BULLET.sub("", md)
    md = _NUMBERED.sub("", md)
    md = _BOLD.sub(lambda m: m.group(1) or m.group(2), md)
    md = _ITAL.sub(lambda m: m.group(1) or m.group(2), md)
    return md


def read_markdown(path: str) -> str:
    """Read a Markdown file and return spoken-friendly text."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return _strip(f.read())
