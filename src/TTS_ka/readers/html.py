"""HTML reader — extracts text and drops script/style tags.

Uses ``beautifulsoup4`` when available; falls back to a regex stripper for
basic HTML when the dependency is missing (so TXT-like .htm files still work
without ``[readers]`` installed).
"""

from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _fallback_strip(html: str) -> str:
    html = _SCRIPT_RE.sub(" ", html)
    html = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", html).strip()


def read_html(path: str) -> str:
    """Extract readable text from an HTML file."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _fallback_strip(raw)
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return _WS_RE.sub(" ", soup.get_text(separator=" ")).strip()
