"""EPUB reader — uses ``ebooklib`` + ``beautifulsoup4``."""

from __future__ import annotations

import re
from typing import List, Tuple

_WS_RE = re.compile(r"\s+")


def read_epub_chapters(path: str) -> List[Tuple[str, str]]:
    """Return [(chapter_title, chapter_text), ...] in spine order.

    Title is the first heading or the document name if no heading is present.
    """
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        from ..deps import MissingExtraError
        raise MissingExtraError(
            "Reading EPUB files requires the 'ebooklib' package", "readers"
        )
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        from ..deps import MissingExtraError
        raise MissingExtraError(
            "Reading EPUB files requires the 'beautifulsoup4' package", "readers"
        )

    book = epub.read_epub(path)
    chapters: List[Tuple[str, str]] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        heading_el = soup.find(["h1", "h2", "h3"])
        title = heading_el.get_text(strip=True) if heading_el else item.get_name()
        text = _WS_RE.sub(" ", soup.get_text(separator=" ")).strip()
        if text:
            chapters.append((title, text))
    return chapters


def read_epub(path: str) -> str:
    """Concatenate all chapters into one string for plain TTS use."""
    chapters = read_epub_chapters(path)
    return "\n\n".join(text for _, text in chapters)
