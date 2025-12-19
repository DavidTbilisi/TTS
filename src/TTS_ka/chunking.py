"""High-level chunking helpers (heuristics, decisions).

This module delegates pure text splitting to `chunker.py` which contains
low-level, deterministic splitter functions. Keep public API stable by
re-exporting names expected by callers and tests.
"""

from typing import List

from .chunker import adaptive_chunk_text as _adaptive_chunk_text
from .chunker import needs_chunking as _needs_chunking
from .chunker import smart_chunk_text as _smart_chunk_text
from .chunker import split_into_chunks as _split_into_chunks


def split_text_into_chunks(text: str, approx_seconds: int = 60) -> List[str]:
    """High-level chunking: convert approx_seconds to a word-count heuristic
    and delegate to the splitter implementation in `chunker`.
    """
    # Heuristic WPM mapping unchanged from previous implementation
    WPM = 160
    words_per_second = WPM / 60.0
    words_per_chunk = max(20, int(words_per_second * approx_seconds))
    return _split_into_chunks(text, max_words=words_per_chunk)


def should_chunk_text(text: str, chunk_seconds: int = 0) -> bool:
    """Decide whether text should be chunked.

    This delegates to `chunker.needs_chunking` while respecting explicit
    user preference via chunk_seconds.
    """
    if chunk_seconds > 0:
        return True
    return _needs_chunking(text)


# Backwards-compatible helpers expected by tests and consumers


def smart_chunk_text(text: str, max_length: int = 200) -> List[str]:
    return _smart_chunk_text(text, max_length=max_length)


def adaptive_chunk_text(text: str, target_seconds: int = 30) -> List[str]:
    return _adaptive_chunk_text(text, target_seconds=target_seconds)
