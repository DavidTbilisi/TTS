"""Dispatch text extraction by file extension.

Each reader lives in its own module and depends on at most one optional
third-party library. Heavy deps (``pypdf``, ``ebooklib``, ``python-docx``,
``beautifulsoup4``) are installed via the ``[readers]`` extra:

    pip install TTS_ka[readers]

When a reader's dependency is missing, ``read_file`` raises
``MissingExtraError`` with a clear ``pip install`` hint instead of an opaque
ImportError.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from ..deps import MissingExtraError

from .plain import read_plain
from .markdown import read_markdown
from .html import read_html
from .pdf import PageRangeError, read_pdf
from .epub import read_epub
from .docx import read_docx


# Extension → reader. Lowercase, leading dot.
READERS: Dict[str, Callable[[str], str]] = {
    ".txt":  read_plain,
    ".rst":  read_plain,
    ".md":   read_markdown,
    ".markdown": read_markdown,
    ".html": read_html,
    ".htm":  read_html,
    ".pdf":  read_pdf,
    ".epub": read_epub,
    ".docx": read_docx,
}


def read_file(path: str, pages: Optional[str] = None) -> str:
    """Read text from *path*, dispatching by extension. Unknown extensions
    fall back to plain-text reading.

    *pages* (e.g. ``"20-24"``) selects PDF pages; for any other file type it
    raises ``PageRangeError``.
    """
    ext = os.path.splitext(path)[1].lower()
    if pages is not None:
        if ext != ".pdf":
            raise PageRangeError("a page selection only works with PDF files")
        return read_pdf(path, pages=pages)
    reader = READERS.get(ext, read_plain)
    return reader(path)


__all__ = ["read_file", "READERS", "MissingExtraError", "PageRangeError"]
