"""Write ID3 tags and chapter markers to MP3 files using mutagen.

Mutagen is an optional dependency. When it isn't installed, every public
function in this module raises ``MissingExtraError`` with a clear pip-install
hint, so callers can decide whether to skip or surface the error.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional


class MissingExtraError(RuntimeError):
    """Raised when mutagen isn't installed."""

    def __init__(self) -> None:
        super().__init__(
            "Writing ID3 tags requires the 'mutagen' package. "
            "Install with: pip install TTS_ka[metadata]"
        )


@dataclass(frozen=True)
class Chapter:
    title: str
    start_ms: int
    end_ms: int


@dataclass
class MetadataSpec:
    """Bundle of metadata to attach to a generated MP3."""
    title: Optional[str] = None
    author: Optional[str] = None
    album: Optional[str] = None
    cover_path: Optional[str] = None
    chapters: Optional[List[Chapter]] = None

    def is_empty(self) -> bool:
        return not (
            self.title or self.author or self.album
            or self.cover_path or self.chapters
        )


def load_chapters(path: str) -> List[Chapter]:
    """Load chapters from a JSON file with the shape:
        [{"title": "Ch1", "start_ms": 0, "end_ms": 5000}, ...]
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: chapters file must be a JSON array")
    chapters: List[Chapter] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry {i} is not an object")
        try:
            chapters.append(
                Chapter(
                    title=str(entry["title"]),
                    start_ms=int(entry["start_ms"]),
                    end_ms=int(entry["end_ms"]),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"{path}: entry {i} is malformed: {exc}") from exc
    return chapters


def _detect_cover_mime(cover_path: str) -> str:
    ext = os.path.splitext(cover_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    return "application/octet-stream"


def apply(path: str, spec: MetadataSpec) -> None:
    """Write the metadata in *spec* to the MP3 at *path*.

    A no-op when *spec* is empty so callers can pass it unconditionally.
    """
    if spec.is_empty():
        return
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, CHAP, CTOC, ID3NoHeaderError
    except ImportError:
        raise MissingExtraError()

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()

    if spec.title:
        tags.delall("TIT2")
        tags.add(TIT2(encoding=3, text=spec.title))
    if spec.author:
        tags.delall("TPE1")
        tags.add(TPE1(encoding=3, text=spec.author))
    if spec.album:
        tags.delall("TALB")
        tags.add(TALB(encoding=3, text=spec.album))

    if spec.cover_path:
        try:
            with open(spec.cover_path, "rb") as f:
                cover_bytes = f.read()
            tags.delall("APIC")
            tags.add(
                APIC(
                    encoding=3,
                    mime=_detect_cover_mime(spec.cover_path),
                    type=3,  # cover (front)
                    desc="Cover",
                    data=cover_bytes,
                )
            )
        except OSError:
            pass

    if spec.chapters:
        tags.delall("CHAP")
        tags.delall("CTOC")
        element_ids: List[str] = []
        for i, ch in enumerate(spec.chapters):
            element_id = f"ch{i}"
            element_ids.append(element_id)
            tags.add(
                CHAP(
                    element_id=element_id,
                    start_time=ch.start_ms,
                    end_time=ch.end_ms,
                    sub_frames=[TIT2(encoding=3, text=ch.title)],
                )
            )
        if element_ids:
            tags.add(
                CTOC(
                    element_id="toc",
                    flags=3,
                    child_element_ids=element_ids,
                )
            )

    tags.save(path)
