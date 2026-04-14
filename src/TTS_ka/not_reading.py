"""Filters for non-readable substrings.

Provides helpers to replace code blocks, inline code, links, and very
large numeric sequences with short, readable placeholders so TTS engines
don't attempt to speak raw code/URLs/huge numbers.

Design
------
Each filter is a plain ``TextFilter`` callable (``str -> str``).
``TextProcessingPipeline`` composes them in order, making the set of
active filters easy to extend or override without touching call sites.
The module-level ``replace_not_readable`` convenience function runs the
default four-filter pipeline.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Pattern

__all__ = [
    "TextFilter",
    "TextProcessingPipeline",
    "replace_not_readable",
    "filter_code_blocks",
    "filter_inline_code",
    "filter_urls",
    "filter_big_numbers",
]

# A TextFilter is any callable that transforms a string
TextFilter = Callable[[str], str]

# ── Compiled regexes (module-level for reuse) ────────────────────────────────

CODE_BLOCK_RE: Pattern = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE: Pattern = re.compile(r"`([^`]+)`")
URL_RE: Pattern = re.compile(r"\b(?:https?://|http://|www\.)\S+\b", re.IGNORECASE)
BIG_NUMBER_RE: Pattern = re.compile(r"\b\d{7,}\b")  # 7+ digits => >= 1,000,000
_WHITESPACE_RE: Pattern = re.compile(r"\s{2,}")


# ── Individual filters ────────────────────────────────────────────────────────

def filter_code_blocks(text: str) -> str:
    """Replace fenced code blocks (```...```) with a placeholder."""
    return CODE_BLOCK_RE.sub(" you can see code in text ", text)


def filter_inline_code(text: str) -> str:
    """Replace inline backtick code spans with a placeholder."""
    return INLINE_CODE_RE.sub(" you can see code in text ", text)


def filter_urls(text: str) -> str:
    """Replace URLs and www links with a placeholder."""
    return URL_RE.sub(" see link in text ", text)


def filter_big_numbers(text: str) -> str:
    """Replace long digit sequences (7+ digits) with a placeholder.

    This treats any contiguous run of 7 or more digits as a "big number"
    (i.e., >= 1,000,000) which is usually not useful to speak verbatim.
    """
    return BIG_NUMBER_RE.sub(" a large number ", text)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class TextProcessingPipeline:
    """Composes a sequence of :data:`TextFilter` callables and applies them in order.

    Usage::

        pipeline = TextProcessingPipeline()          # default filters
        clean = pipeline.process(raw_text)

        custom = TextProcessingPipeline([filter_urls, filter_big_numbers])
        clean = custom.process(raw_text)
    """

    _DEFAULT_FILTERS: List[TextFilter] = [
        filter_code_blocks,
        filter_inline_code,
        filter_urls,
        filter_big_numbers,
    ]

    def __init__(self, filters: Optional[List[TextFilter]] = None) -> None:
        self._filters: List[TextFilter] = (
            filters if filters is not None else list(self._DEFAULT_FILTERS)
        )

    def process(self, text: str) -> str:
        """Apply all filters in order and return a whitespace-normalised result."""
        if not text:
            return text
        result = text
        for f in self._filters:
            result = f(result)
        return _WHITESPACE_RE.sub(" ", result).strip()


# ── Module-level convenience (default pipeline, reused across calls) ──────────

_default_pipeline = TextProcessingPipeline()


def replace_not_readable(text: str) -> str:
    """Apply all default filters and return a cleaned string suitable for TTS.

    Filters are applied in an order that avoids accidental re-matching:
    1. Code blocks
    2. Inline code
    3. URLs
    4. Big numbers

    The result is whitespace-normalized.
    """
    return _default_pipeline.process(text)


if __name__ == "__main__":
    sample = (
        "Here is code: ```def f(): pass``` and inline `x=1` and a link https://example.com "
        "and a big number 12345678."
    )
    print(replace_not_readable(sample))
