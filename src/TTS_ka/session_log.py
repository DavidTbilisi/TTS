"""Append-only training log for study-mode sessions.

One line per session, JSONL, stored at ``~/.tts_ka_study.jsonl`` (matching the
sibling convention in :mod:`user_config` for ``.tts_config.json``).

The log is the substrate for later analysis: WPM trajectory over weeks,
chunks-per-session, answer-correctness rate. Keeping the format flat and
append-only means a graphing script can be a one-liner over the file later;
schema changes are handled by adding new optional fields, not by migration.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class SessionRecord:
    """One study session, ready to serialize as a JSONL line."""

    date: str  # ISO-8601 UTC, e.g. "2026-06-04T11:23:00+00:00"
    text_hash: str
    voice: str
    word_count: int
    duration_ms: int
    chunks_done: int
    questions_asked: int = 0
    questions_correct: int = 0
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def wpm(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return self.word_count * 60_000.0 / self.duration_ms

    @classmethod
    def now(cls, **kwargs: object) -> "SessionRecord":
        return cls(date=datetime.now(timezone.utc).isoformat(), **kwargs)  # type: ignore[arg-type]


def default_log_path() -> Path:
    """``~/.tts_ka_study.jsonl`` — overridable via ``TTS_KA_STUDY_LOG``."""
    env = os.environ.get("TTS_KA_STUDY_LOG", "").strip()
    if env:
        return Path(os.path.expanduser(env))
    return Path.home() / ".tts_ka_study.jsonl"


def append(record: SessionRecord, path: Optional[Path] = None) -> Path:
    """Append a record as one JSON line. Returns the path written to."""
    target = path or default_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return target


def read_all(path: Optional[Path] = None) -> List[SessionRecord]:
    """Read every session record. Malformed lines are skipped, not raised."""
    target = path or default_log_path()
    if not target.exists():
        return []
    out: List[SessionRecord] = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                out.append(SessionRecord(**data))
            except (json.JSONDecodeError, TypeError):
                continue
    return out
