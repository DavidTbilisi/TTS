"""PDF reader — uses ``pypdf``. Optional dep."""

from __future__ import annotations


def read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        from . import MissingExtraError
        raise MissingExtraError("PDF", "pypdf")
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p.strip() for p in pages if p.strip())
