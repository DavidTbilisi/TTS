"""DOCX reader — uses ``python-docx``."""

from __future__ import annotations


def read_docx(path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        from ..deps import MissingExtraError
        raise MissingExtraError(
            "Reading DOCX files requires the 'python-docx' package", "readers"
        )
    doc = Document(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
