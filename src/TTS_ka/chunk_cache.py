"""Content-addressed cache of synthesized chunks.

Every successful edge-tts synthesis is stored under a key derived from the
exact request (sanitized text, voice, rate / pitch / volume, output format),
so the same chunk is never synthesized twice. That also makes long runs
resumable: when one chunk fails the run fails (see the failure contract in
``fast_audio``), but the chunks that did finish are cached, and re-running
the same command only synthesizes what is missing.

Layout: ``<root>/v1/<key[:2]>/<key>.mp3`` plus an optional
``<key>.words.json`` with the word timings used by subtitles and study mode.
Writes are atomic (temp file + ``os.replace``) so concurrent runs never see a
partial entry. The cache is capped (``TTS_KA_CACHE_MAX_MB``, default 500 MB,
roughly 23 hours of speech) and pruned least-recently-used first.

Every operation is best-effort: an unwritable or corrupt cache only costs a
re-synthesis, never a failed run.

Environment:

* ``TTS_KA_CACHE=0`` disables the cache (also ``--no-cache``, config ``"cache": false``).
* ``TTS_KA_CACHE_DIR`` overrides the location.
* ``TTS_KA_CACHE_MAX_MB`` sets the size cap.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .prosody import ProsodyOpts
from .subtitles import WordEvent

# Bump to invalidate every entry (e.g. if the service changes what a voice sounds like).
CACHE_VERSION = "v1"
# What edge-tts returns; part of the key so a format change can't serve stale bytes.
AUDIO_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
DEFAULT_MAX_MB = 500
# Pruning stops once the cache is back under this fraction of the cap.
PRUNE_TARGET_RATIO = 0.9


def _env_disabled() -> bool:
    return os.environ.get("TTS_KA_CACHE", "1").strip().lower() in ("0", "false", "no", "off")


def default_dir() -> Path:
    """Cache location: ``TTS_KA_CACHE_DIR``, else the platform's user cache dir."""
    override = os.environ.get("TTS_KA_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / "tts-ka" / "Cache"
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "tts-ka"
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    return (Path(xdg) if xdg else home / ".cache") / "tts-ka"


def _max_bytes_from_env() -> int:
    try:
        mb = int(os.environ.get("TTS_KA_CACHE_MAX_MB", DEFAULT_MAX_MB))
    except ValueError:
        mb = DEFAULT_MAX_MB
    return max(0, mb) * 1024 * 1024


def cache_key(clean_text: str, voice: str, prosody: Optional[ProsodyOpts]) -> str:
    """Key for one synthesis request; *clean_text* is the already-sanitized text."""
    p = prosody or ProsodyOpts()
    fields = (CACHE_VERSION, AUDIO_FORMAT, clean_text, voice, p.rate, p.pitch, p.volume)
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


class ChunkCache:
    """A directory of cached chunk MP3s (and word-timing sidecars)."""

    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes
        self._pruned = False

    def path_for(self, key: str, suffix: str = ".mp3") -> Path:
        return self.root / CACHE_VERSION / key[:2] / f"{key}{suffix}"

    # ── Audio ────────────────────────────────────────────────────────────────

    def fetch(self, key: str, dest: str) -> bool:
        """Copy the cached chunk for *key* to *dest*; False on a miss.

        A copy, not a link: callers modify their output in place (ID3 tags).
        """
        src = self.path_for(key)
        try:
            if src.stat().st_size == 0:
                return False
            shutil.copyfile(src, dest)
            os.utime(src)  # mark as recently used for LRU pruning
            return True
        except OSError:
            return False

    def store(self, key: str, src: str) -> None:
        """Save *src* (a finished, non-empty chunk) under *key*."""
        try:
            if os.path.getsize(src) == 0:
                return
        except OSError:
            return
        self._write(self.path_for(key), lambda tmp: shutil.copyfile(src, tmp))

    # ── Word timings (subtitles / study mode) ────────────────────────────────

    def fetch_words(self, key: str) -> Optional[List[WordEvent]]:
        try:
            raw = json.loads(self.path_for(key, ".words.json").read_text(encoding="utf-8"))
            return [WordEvent(**e) for e in raw]
        except (OSError, ValueError, TypeError):
            return None

    def store_words(self, key: str, events: List[WordEvent]) -> None:
        payload = json.dumps([asdict(e) for e in events], ensure_ascii=False)
        self._write(self.path_for(key, ".words.json"),
                    lambda tmp: Path(tmp).write_text(payload, encoding="utf-8"))

    # ── Maintenance ──────────────────────────────────────────────────────────

    def _entries(self) -> Iterator[os.DirEntry]:
        top = self.root / CACHE_VERSION
        try:
            shards = list(os.scandir(top))
        except OSError:
            return
        for shard in shards:
            if not shard.is_dir():
                continue
            try:
                yield from (e for e in os.scandir(shard.path) if e.is_file())
            except OSError:
                continue

    def usage(self) -> Tuple[int, int]:
        """``(files, bytes)`` currently in the cache."""
        files = size = 0
        for entry in self._entries():
            try:
                size += entry.stat().st_size
                files += 1
            except OSError:
                pass
        return files, size

    def prune(self, target_ratio: float = PRUNE_TARGET_RATIO) -> int:
        """Delete least-recently-used files until under the cap; return how many."""
        stats = []
        total = 0
        for entry in self._entries():
            try:
                st = entry.stat()
            except OSError:
                continue
            stats.append((st.st_mtime, st.st_size, entry.path))
            total += st.st_size
        if total <= self.max_bytes:
            return 0
        target = self.max_bytes * target_ratio
        removed = 0
        for _mtime, size, path in sorted(stats):
            if total <= target:
                break
            try:
                os.remove(path)
                total -= size
                removed += 1
            except OSError:
                pass
        return removed

    def clear(self) -> Tuple[int, int]:
        """Delete every entry; return ``(files, bytes)`` removed."""
        files, size = self.usage()
        shutil.rmtree(self.root / CACHE_VERSION, ignore_errors=True)
        return files, size

    def _write(self, target: Path, fill) -> None:
        """Atomically create *target* by calling ``fill(tmp_path)``; swallow I/O errors."""
        tmp = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
            os.close(fd)
            fill(tmp)
            os.replace(tmp, target)
            tmp = None
        except OSError:
            pass
        finally:
            if tmp is not None:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        if not self._pruned:
            self._pruned = True  # at most one directory walk per process
            self.prune()


# ── Process-wide instance ─────────────────────────────────────────────────────

_cache: Optional[ChunkCache] = None
_enabled_override: Optional[bool] = None


def configure(*, enabled: Optional[bool] = None) -> None:
    """Override whether the cache is used (``--no-cache``); resets the instance."""
    global _cache, _enabled_override
    _enabled_override = enabled
    _cache = None


def get_cache() -> Optional[ChunkCache]:
    """The process-wide cache, or None when caching is disabled."""
    global _cache
    enabled = _enabled_override if _enabled_override is not None else not _env_disabled()
    if not enabled:
        return None
    if _cache is None:
        _cache = ChunkCache(default_dir(), _max_bytes_from_env())
    return _cache
