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
from typing import Callable, Dict

from .plain import read_plain
from .markdown import read_markdown
from .html import read_html
from .pdf import read_pdf
from .epub import read_epub
from .docx import read_docx


class MissingExtraError(RuntimeError):
    """Raised when a reader's optional dependency is not installed."""

    def __init__(self, extra: str, package: str) -> None:
        super().__init__(
            f"Reading {extra} files requires the {package!r} package. "
            f"Install with: pip install TTS_ka[readers]"
        )
        self.extra = extra
        self.package = package


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


def read_file(path: str) -> str:
    """Read text from *path*, dispatching by extension. Unknown extensions
    fall back to plain-text reading.
    """
    ext = os.path.splitext(path)[1].lower()
    reader = READERS.get(ext, read_plain)
    return reader(path)


__all__ = ["read_file", "READERS", "MissingExtraError"]
