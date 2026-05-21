"""Plain-text reader. Default fallback when no extension matches."""

from __future__ import annotations


def read_plain(path: str) -> str:
    """Read *path* as UTF-8 text and return its contents."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
