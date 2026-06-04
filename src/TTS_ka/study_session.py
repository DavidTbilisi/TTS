"""Study-mode session state: pure logic over a list of :class:`WordEvent`.

Holds the timing model and chunk boundaries for a single reading session.
No UI, no audio, no I/O — easy to unit test and to drive from either the
Tk player (:mod:`study_player`) or a future web/CLI front end.

The single non-obvious decision is the current-word lookup: ``current_word_at``
uses :func:`bisect.bisect_right` on the precomputed ``_starts`` array so the
sync loop (called ~50×/s in the player) stays O(log n).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .subtitles import WordEvent


DEFAULT_CHUNK_WORDS = 200


@dataclass(frozen=True)
class Peripheral:
    """Words immediately before/at/after the current playback position."""
    prev: List[WordEvent]
    current: Optional[WordEvent]
    next: List[WordEvent]


class StudySession:
    """Timing + chunk model for one reading session."""

    def __init__(
        self,
        events: List[WordEvent],
        chunk_size_words: int = DEFAULT_CHUNK_WORDS,
    ) -> None:
        if chunk_size_words <= 0:
            raise ValueError("chunk_size_words must be positive")
        self.events: List[WordEvent] = list(events)
        self.chunk_size_words = chunk_size_words
        self._starts: List[int] = [ev.start_ms for ev in self.events]

    @property
    def total_duration_ms(self) -> int:
        if not self.events:
            return 0
        return self.events[-1].end_ms

    @property
    def wpm(self) -> float:
        if not self.events or self.total_duration_ms <= 0:
            return 0.0
        return len(self.events) * 60_000.0 / self.total_duration_ms

    def current_word_index(self, pos_ms: int) -> int:
        """Index of the word that should be displayed at ``pos_ms``.

        Returns -1 if pos_ms is before the first word. After the last word,
        returns the last index (so the UI sticks on the final word at EOF).
        """
        if not self.events:
            return -1
        i = bisect.bisect_right(self._starts, pos_ms) - 1
        if i < 0:
            return -1
        if i >= len(self.events):
            return len(self.events) - 1
        return i

    def current_word_at(self, pos_ms: int) -> Optional[WordEvent]:
        i = self.current_word_index(pos_ms)
        return self.events[i] if i >= 0 else None

    def peripheral(self, pos_ms: int, span: int = 2) -> Peripheral:
        """Return up to ``span`` words on each side of the current word."""
        i = self.current_word_index(pos_ms)
        if i < 0:
            return Peripheral(prev=[], current=None, next=self.events[:span])
        start = max(0, i - span)
        end = min(len(self.events), i + span + 1)
        return Peripheral(
            prev=self.events[start:i],
            current=self.events[i],
            next=self.events[i + 1 : end],
        )

    def chunk_boundaries(self) -> List[Tuple[int, int]]:
        """List of (start_word_idx, end_word_idx_exclusive) chunk slices."""
        n = len(self.events)
        return [
            (i, min(i + self.chunk_size_words, n))
            for i in range(0, n, self.chunk_size_words)
        ]

    def chunk_index_at(self, pos_ms: int) -> int:
        """Which chunk the current playback position belongs to (0-based)."""
        i = self.current_word_index(pos_ms)
        if i < 0:
            return 0
        return i // self.chunk_size_words

    def chunk_text(self, chunk_idx: int) -> str:
        bounds = self.chunk_boundaries()
        if chunk_idx < 0 or chunk_idx >= len(bounds):
            return ""
        start, end = bounds[chunk_idx]
        return " ".join(ev.text for ev in self.events[start:end])

    def chunk_start_ms(self, chunk_idx: int) -> int:
        bounds = self.chunk_boundaries()
        if chunk_idx < 0 or chunk_idx >= len(bounds):
            return 0
        return self.events[bounds[chunk_idx][0]].start_ms

    def chunk_end_ms(self, chunk_idx: int) -> int:
        bounds = self.chunk_boundaries()
        if chunk_idx < 0 or chunk_idx >= len(bounds):
            return self.total_duration_ms
        return self.events[bounds[chunk_idx][1] - 1].end_ms
