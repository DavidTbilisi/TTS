"""Text chunking utilities for long text processing."""

from typing import List


def split_text_into_chunks(text: str, approx_seconds: int = 60) -> List[str]:
    """Split text into chunks of approximately the specified duration.
    
    Uses words-per-minute heuristics (avg 160 wpm -> ~2.66 wps).
    """
    WPM = 160
    words_per_second = WPM / 60.0
    words_per_chunk = max(20, int(words_per_second * approx_seconds))
    
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), words_per_chunk):
        chunk = ' '.join(words[i:i + words_per_chunk])
        chunks.append(chunk)
    
    return chunks


def should_chunk_text(text: str, chunk_seconds: int = 0) -> bool:
    """Determine if text should be chunked based on explicit user request only."""
    return chunk_seconds > 0