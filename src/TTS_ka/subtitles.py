"""Subtitle file generation from word-boundary events.

Edge TTS emits a stream of ``WordBoundary`` events as it generates audio,
each containing a word's start time and duration. This module converts a
list of such events into SRT (SubRip) or VTT (WebVTT) text.

Multiple words are grouped into a single subtitle line until either
* the total spoken duration of the group exceeds ``MAX_LINE_MS`` (≈4s), or
* the word count reaches ``MAX_WORDS_PER_LINE`` (defaults to 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple


@dataclass(frozen=True)
class WordEvent:
    """A single word with its start time and duration in milliseconds."""
    text: str
    start_ms: int
    duration_ms: int

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms


MAX_LINE_MS = 4000
MAX_WORDS_PER_LINE = 8


def _group(events: Iterable[WordEvent]) -> List[Tuple[List[WordEvent], int, int]]:
    """Group events into subtitle lines. Returns [(words, start_ms, end_ms), ...]."""
    groups: List[Tuple[List[WordEvent], int, int]] = []
    current: List[WordEvent] = []
    for ev in events:
        if not current:
            current = [ev]
            continue
        span_ms = ev.end_ms - current[0].start_ms
        if span_ms > MAX_LINE_MS or len(current) >= MAX_WORDS_PER_LINE:
            groups.append((current, current[0].start_ms, current[-1].end_ms))
            current = [ev]
        else:
            current.append(ev)
    if current:
        groups.append((current, current[0].start_ms, current[-1].end_ms))
    return groups


def _format_ts(ms: int, sep: str = ",") -> str:
    """Format milliseconds as HH:MM:SS<sep>mmm."""
    if ms < 0:
        ms = 0
    hours, rem = divmod(ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def events_to_srt(events: Iterable[WordEvent]) -> str:
    """Render *events* as SubRip (SRT) text."""
    groups = _group(events)
    blocks: List[str] = []
    for i, (words, start, end) in enumerate(groups, start=1):
        ts = f"{_format_ts(start)} --> {_format_ts(end)}"
        text = " ".join(w.text for w in words)
        blocks.append(f"{i}\n{ts}\n{text}\n")
    return "\n".join(blocks)


def events_to_vtt(events: Iterable[WordEvent]) -> str:
    """Render *events* as WebVTT text (with the WEBVTT header)."""
    groups = _group(events)
    out = ["WEBVTT", ""]
    for words, start, end in groups:
        ts = f"{_format_ts(start, sep='.')} --> {_format_ts(end, sep='.')}"
        text = " ".join(w.text for w in words)
        out.append(ts)
        out.append(text)
        out.append("")
    return "\n".join(out)


def write_subs(events: Iterable[WordEvent], path: str, fmt: str) -> None:
    """Write *events* to *path* in either 'srt' or 'vtt' format."""
    if fmt == "srt":
        content = events_to_srt(events)
    elif fmt == "vtt":
        content = events_to_vtt(events)
    else:
        raise ValueError(f"unknown subtitle format: {fmt!r}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
