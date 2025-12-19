"""Text chunking for long documents and pure splitting helpers."""

import re
from typing import List


def split_into_chunks(text: str, max_words: int = 150) -> List[str]:
    """Split text into manageable chunks for TTS generation.

    Args:
        text: Text to split
        max_words: Maximum words per chunk (default 150 ~30 seconds)

    Returns:
        List of text chunks
    """
    if text is None:
        return []

    # Preserve whitespace-only input exactly
    if text.strip() == "" and text != "":
        return [text]

    # Normalize text boundaries but keep content otherwise
    stripped = text.strip()
    if not stripped:
        return [text]

    # Split into sentences (basic sentence boundary detection)
    sentences = re.split(r"(?<=[.!?])\s+", stripped)

    chunks = []
    current_chunk: List[str] = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        # If single sentence exceeds max, add it as its own chunk
        if sentence_words > max_words:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_words = 0
            chunks.append(sentence)
            continue

        # If adding this sentence would exceed max, start new chunk
        if current_words + sentence_words > max_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_words = 0

        current_chunk.append(sentence)
        current_words += sentence_words

    # Add remaining chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # If no chunks were produced, return the original text (including whitespace)
    if chunks:
        return chunks
    # Preserve original text (including whitespace) when nothing split
    return [text]


def needs_chunking(text: str, threshold_words: int = 200) -> bool:
    """Check if text needs to be chunked.

    Args:
        text: Text to check
        threshold_words: Word count threshold for chunking

    Returns:
        True if text should be chunked
    """
    return len(text.split()) > threshold_words


# --- Pure splitting helpers used by higher-level chunking logic/tests ---


def smart_chunk_text(text: str, max_length: int = 200) -> List[str]:
    """Create chunks that attempt to stay under a character `max_length`.

    This implementation preserves the original spacing by tokenizing into
    segments that keep trailing whitespace so that joining the resulting
    chunks with "" reconstructs the original string.
    """
    if text is None:
        return [""]

    # Preserve whitespace-only input exactly
    if text.strip() == "" and text != "":
        return [text]

    # Tokenize into non-space sequences with following whitespace (if any)
    tokens = re.findall(r"\S+\s*", text)
    if not tokens:
        return [text]

    chunks: List[str] = []
    cur = []
    cur_len = 0

    for tok in tokens:
        tlen = len(tok)
        if cur and (cur_len + tlen) > max_length:
            chunks.append("".join(cur))
            cur = [tok]
            cur_len = tlen
        else:
            cur.append(tok)
            cur_len += tlen

    if cur:
        chunks.append("".join(cur))

    return chunks


def adaptive_chunk_text(text: str, target_seconds: int = 30) -> List[str]:
    """Adaptive chunking that maps a target duration (seconds) to chunk sizes.

    Uses a words-per-minute heuristic to compute chunk sizes and preserves
    original spacing similar to `smart_chunk_text`.
    """
    if text is None:
        return [""]

    if text.strip() == "" and text != "":
        return [text]

    WPM = 160
    words_per_second = WPM / 60.0
    words_per_chunk = max(20, int(words_per_second * max(1, target_seconds)))

    # Tokenize by words preserving following whitespace
    tokens = re.findall(r"\S+\s*", text)
    if not tokens:
        return [text]

    # Convert tokens to words-only for counting but keep tokens for output
    words = [re.match(r"(\S+)", t).group(1) for t in tokens]

    chunks = []
    i = 0
    while i < len(words):
        end = i + words_per_chunk
        # Build chunk from corresponding tokens
        chunk = "".join(tokens[i:end])
        chunks.append(chunk)
        i = end

    return chunks
