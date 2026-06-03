"""Text chunking utilities for long text processing."""

from typing import List
from .constants import WPM


def split_text_into_chunks(text: str, approx_seconds: int = 60,
                           first_chunk_seconds: int = 0) -> List[str]:
    """Split text into chunks of approximately the specified duration.

    Uses words-per-minute heuristics (WPM constant -> ~2.66 wps at 160 wpm).

    When *first_chunk_seconds* > 0, the **first** chunk is sized to roughly that
    (shorter) duration while the rest use *approx_seconds*. A small first chunk
    generates faster, so streaming playback starts sooner (lower
    time-to-first-audio). Has no effect unless it actually makes the first chunk
    smaller and there is more text after it.
    """
    words_per_second = WPM / 60.0
    words_per_chunk = max(20, int(words_per_second * approx_seconds))

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0

    if first_chunk_seconds and first_chunk_seconds > 0:
        first_words = max(8, int(words_per_second * first_chunk_seconds))
        if first_words < len(words) and first_words < words_per_chunk:
            chunks.append(' '.join(words[:first_words]))
            start = first_words

    for i in range(start, len(words), words_per_chunk):
        chunks.append(' '.join(words[i:i + words_per_chunk]))

    return chunks


def should_chunk_text(text: str, chunk_seconds: int = 0) -> bool:
    """Determine if text should be chunked based on explicit user request only."""
    return chunk_seconds > 0