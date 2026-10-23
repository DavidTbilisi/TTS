"""PDF reader — poppler's ``pdftotext`` when installed, else ``pypdf`` (optional dep)."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import List, Optional

# A whole 400-page book takes pdftotext ~3 s; this only stops a hung process.
PDFTOTEXT_TIMEOUT_S = 300


class PageRangeError(ValueError):
    """A page selection that is malformed, out of range, or not for a PDF."""


def parse_page_spec(spec: str, page_count: int) -> List[int]:
    """Turn a 1-based page selection into 0-based page indices.

    *spec* is a comma-separated list of ``N``, ``N-M``, ``N-`` (to the last
    page) and ``-M`` (from the first page), e.g. ``"20-24"`` or ``"1-3,7,10-"``.
    Pages come back in the order given, each at most once. A page past the
    end is an error rather than silently dropped, so a typo can't read the
    wrong part of a book.
    """
    indices: List[int] = []
    seen = set()
    items = [item.strip() for item in spec.split(",")]
    if not any(items):
        raise PageRangeError("empty page selection")
    for item in items:
        if not item:
            continue
        start_s, dash, end_s = item.partition("-")
        try:
            start = int(start_s) if start_s.strip() else 1
            end = (int(end_s) if end_s.strip() else page_count) if dash else start
        except ValueError:
            raise PageRangeError(
                f"invalid page range {item!r} (expected e.g. 5, 20-24, 10-)"
            ) from None
        if start < 1 or end < start:
            raise PageRangeError(f"invalid page range {item!r}")
        if end > page_count:
            raise PageRangeError(f"page {end} is past the end (the PDF has {page_count} pages)")
        for page in range(start - 1, end):
            if page not in seen:
                seen.add(page)
                indices.append(page)
    return indices


def read_pdf(path: str, pages: Optional[str] = None) -> str:
    """Extract the text of *path*; *pages* selects pages (see ``parse_page_spec``).

    Uses poppler's ``pdftotext`` when it is installed, else ``pypdf``.
    Typeset books mark hyphenation points with soft hyphens; ``pypdf`` turns
    them into spaces (``dif fer ent``), which then get spoken as fragments,
    while ``pdftotext`` keeps them as U+00AD and ``_repair_soft_hyphens``
    removes them.
    """
    exe = _pdftotext_exe()
    if exe:
        text = _read_with_pdftotext(exe, path, pages)
        if text is not None:
            return text
    return _read_with_pypdf(path, pages)


def _pdftotext_exe() -> Optional[str]:
    return shutil.which("pdftotext")


# pdftotext puts a stray space after the first glyph that follows a soft
# hyphen ("\xadr unning", "impor\xadt ant"). Rejoin it, except after a hyphen
# or dash, where the letter is usually a word of its own ("big-\xadO notation",
# "rm -\xadf out", "—\xada worklist").
_SOFT_HYPHEN_SPLIT = re.compile(r"(?<![\-‐-―])\xad([^\W\d_]) (?=[^\W\d_])")


def _repair_soft_hyphens(text: str) -> str:
    return _SOFT_HYPHEN_SPLIT.sub(r"\1", text).replace("\xad", "")


def _run_pdftotext(exe: str, path: str, first: Optional[int] = None,
                   last: Optional[int] = None) -> Optional[str]:
    """Text of pages *first*..*last* (1-based), pages separated by form feeds."""
    argv = [exe, "-enc", "UTF-8"]
    if first is not None:
        argv += ["-f", str(first), "-l", str(last)]
    try:
        proc = subprocess.run(argv + [path, "-"], capture_output=True,
                              timeout=PDFTOTEXT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def _page_count(path: str) -> Optional[int]:
    """Page count from poppler's ``pdfinfo``, or None if it isn't available."""
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, path], capture_output=True, timeout=PDFTOTEXT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(rb"^Pages:\s+(\d+)", proc.stdout, re.MULTILINE)
    return int(match.group(1)) if proc.returncode == 0 and match else None


def _read_with_pdftotext(exe: str, path: str, pages: Optional[str]) -> Optional[str]:
    """Extract with pdftotext; None when it fails (the caller falls back to pypdf)."""
    if pages is None:
        raw = _run_pdftotext(exe, path)
        if raw is None:
            return None
        texts = raw.split("\f")
    else:
        count = _page_count(path)
        if count is None:
            # No pdfinfo: extract everything once to count the pages.
            raw = _run_pdftotext(exe, path)
            if raw is None:
                return None
            all_pages = raw.split("\f")[:-1]  # pdftotext ends every page with \f
            texts = [all_pages[i] for i in parse_page_spec(pages, len(all_pages))]
        else:
            selected = parse_page_spec(pages, count)
            first = min(selected)
            raw = _run_pdftotext(exe, path, first + 1, max(selected) + 1)
            if raw is None:
                return None
            span = raw.split("\f")
            texts = [span[i - first] for i in selected if i - first < len(span)]
    cleaned = (_repair_soft_hyphens(t).strip() for t in texts)
    return "\n\n".join(t for t in cleaned if t)


def _read_with_pypdf(path: str, pages: Optional[str]) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        from ..deps import MissingExtraError
        raise MissingExtraError(
            "Reading PDF files requires the 'pypdf' package (or poppler's pdftotext)",
            "readers",
        )
    reader = PdfReader(path)
    selected = (parse_page_spec(pages, len(reader.pages)) if pages is not None
                else range(len(reader.pages)))
    texts = []
    for index in selected:
        try:
            texts.append(reader.pages[index].extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(p.strip() for p in texts if p.strip())
