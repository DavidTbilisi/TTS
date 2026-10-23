"""Audio generation (edge-tts), merging, and playback helpers.

Design
------
``EdgeTTSGenerator`` synthesises one chunk with the ``edge-tts`` library,
retrying transient 403/429 responses with backoff.

``AudioMerger`` (Protocol) abstracts the merge back-ends:

* ``ConcatMp3Merger`` — byte concatenation; lossless, no deps. edge-tts emits
  headerless CBR MP3, so this is the only merger used for ``.mp3`` output.
* ``SoundFileMerger`` — soundfile + numpy (decodes and re-encodes).
* ``PydubMerger``     — PyDub (reliable pure-Python MP3 handling).
* ``FFmpegMerger``    — subprocess ffmpeg (always available when installed).

For other outputs ``fast_merge_audio_files`` tries the last three in order.
Every merger raises ``MergeFailed`` rather than dropping a part: a merged file
with a hole in it is worse than an error.

The module-level ``fast_generate_audio`` / ``fast_merge_audio_files`` /
``play_audio`` functions are the public API used by the rest of the package.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import Awaitable, Callable, Iterator, List, Optional, Protocol

try:
    import soundfile as sf
    import numpy as np
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False

from .constants import VOICE_MAP
from .not_reading import replace_not_readable
from .prosody import ProsodyOpts
from .subtitles import WordEvent


# ── Protocols ─────────────────────────────────────────────────────────────────

class AudioMerger(Protocol):
    """Interface for merging multiple audio part-files into one output file."""

    def merge(self, parts: List[str], output_path: str) -> None:
        """Concatenate *parts* and write the result to *output_path*."""
        ...


# ── Generator ─────────────────────────────────────────────────────────────────

def _edge_tts_transient(err: BaseException) -> bool:
    msg = str(err).lower()
    return "403" in msg or "invalid response status" in msg or "429" in msg


class GenerationFailed(RuntimeError):
    """Synthesis produced no audio (unsupported language, network or service error)."""


# Most recent synthesis failure. Generators report failure as ``False`` (often
# with ``quiet=True``, e.g. parallel chunks), so callers use this to tell the
# user *why* when they turn that into a ``GenerationFailed``.
_last_error: Optional[BaseException] = None


def generation_failed(summary: str, err: Optional[BaseException] = None) -> GenerationFailed:
    """Build a ``GenerationFailed`` carrying *err* (default: the latest edge-tts error) and a fix hint."""
    err = err or _last_error
    # edge-tts errors embed the full websocket URL (with tokens); keep the gist.
    reason = str(err).split(", url=")[0] if err else "edge-tts returned no audio"
    msg = f"{summary}: {reason}"
    if err is not None and _edge_tts_transient(err):
        msg += " (Microsoft rejected the request; try: pip install -U edge-tts)"
    return GenerationFailed(msg)


async def _retry_edge(attempt: Callable[[], Awaitable[None]], retries: int,
                      base_delay: float) -> None:
    """Await *attempt()* up to *retries* times, backing off on transient edge-tts errors.

    Re-raises the last error when it is not transient or retries run out.
    """
    for n in range(retries):
        try:
            await attempt()
            return
        except Exception as e:
            if n < retries - 1 and _edge_tts_transient(e):
                await asyncio.sleep(base_delay * (2**n))
                continue
            raise


def discard_empty_output(path: str) -> None:
    """Remove *path* if a failed synthesis left it behind as a 0-byte file."""
    try:
        if os.path.getsize(path) == 0:
            os.remove(path)
    except OSError:
        pass


class EdgeTTSGenerator:
    """Single-chunk generator using the ``edge-tts`` library."""

    _EDGE_RETRIES = 3
    _EDGE_RETRY_BASE_DELAY = 0.45

    async def generate(self, text: str, language: str, output_path: str,
                       quiet: bool = False, voice: Optional[str] = None,
                       prosody: Optional[ProsodyOpts] = None) -> bool:
        global _last_error
        resolved_voice = voice or VOICE_MAP.get(language)
        if not resolved_voice:
            _last_error = ValueError(
                f"language {language!r} not supported (use: {', '.join(VOICE_MAP)})"
            )
            if not quiet:
                print(f"❌ Language '{language}' not supported. Use: {', '.join(VOICE_MAP)}")
            return False
        from edge_tts import Communicate

        clean_text = replace_not_readable(text)
        edge_kwargs: dict = {}
        if prosody and not prosody.is_default():
            edge_kwargs["rate"] = prosody.rate
            edge_kwargs["pitch"] = prosody.pitch
            edge_kwargs["volume"] = prosody.volume

        async def attempt() -> None:
            communicate = Communicate(clean_text, resolved_voice, **edge_kwargs)
            await communicate.save(output_path)

        try:
            await _retry_edge(attempt, self._EDGE_RETRIES, self._EDGE_RETRY_BASE_DELAY)
        except Exception as e:
            last_err: Optional[BaseException] = e
        else:
            if not quiet:
                print(f"Generated: {os.path.abspath(output_path)}")
            return True
        _last_error = last_err
        if not quiet:
            print(f"Error generating audio: {last_err}")
            if last_err is not None and _edge_tts_transient(last_err):
                print(
                    "Hint: Microsoft often returns 403 until edge-tts tokens are updated. "
                    "Try: pip install -U edge-tts"
                )
        return False


# ── AudioMerger implementations ───────────────────────────────────────────────

class MergeFailed(RuntimeError):
    """Parts could not be merged into one output without losing audio."""


def _id3v2_size(head: bytes) -> int:
    """Byte length of the ID3v2 tag that *head* (the first 10 bytes) starts with, else 0."""
    if len(head) < 10 or head[:3] != b"ID3":
        return 0
    size = 0
    for b in head[6:10]:  # syncsafe: 7 bits per byte
        size = (size << 7) | (b & 0x7F)
    footer = 10 if head[5] & 0x10 else 0
    return 10 + size + footer


def _looks_like_mp3(path: str) -> bool:
    """True when *path* starts with an ID3 tag or an MPEG audio frame sync."""
    try:
        with open(path, "rb") as f:
            head = f.read(3)
    except OSError:
        return False
    return head == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


def _require_parts(parts: List[str], merger: str) -> None:
    """Raise ``MergeFailed`` naming the first part that is missing or empty."""
    for part in parts:
        if not os.path.isfile(part) or os.path.getsize(part) == 0:
            raise MergeFailed(f"{merger}: missing or empty part {part}")


@contextmanager
def _atomic_output(output_path: str) -> Iterator[str]:
    """Yield a temp path beside *output_path* that replaces it only if the block succeeds."""
    fd, tmp = tempfile.mkstemp(
        prefix=".tts_ka_merge_",
        suffix=os.path.splitext(output_path)[1],
        dir=os.path.dirname(os.path.abspath(output_path)),
    )
    os.close(fd)
    try:
        yield tmp
        os.replace(tmp, output_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


class ConcatMp3Merger:
    """Joins MP3 parts byte-for-byte (lossless), keeping only the first part's ID3 tag."""

    def merge(self, parts: List[str], output_path: str) -> None:
        _require_parts(parts, "ConcatMp3Merger")
        with _atomic_output(output_path) as tmp:
            with open(tmp, "wb") as out:
                for i, part in enumerate(parts):
                    with open(part, "rb") as src:
                        if i:
                            src.seek(_id3v2_size(src.read(10)))
                        shutil.copyfileobj(src, out)


class SoundFileMerger:
    """Merges MP3 parts via soundfile + numpy (decodes and re-encodes)."""

    def merge(self, parts: List[str], output_path: str) -> None:
        combined_data = []
        sample_rate: Optional[int] = None
        for part in parts:
            try:
                data, sr = sf.read(part)
            except (OSError, RuntimeError, ValueError) as exc:
                raise MergeFailed(f"SoundFileMerger: cannot read {part}: {exc}") from exc
            if sample_rate is None:
                sample_rate = sr
            combined_data.append(data)
        if not combined_data or sample_rate is None:
            raise MergeFailed("SoundFileMerger: no valid audio parts to merge")
        final_audio = np.concatenate(combined_data, axis=0)
        sf.write(output_path, final_audio, sample_rate)


class PydubMerger:
    """Merges MP3 parts using PyDub."""

    def merge(self, parts: List[str], output_path: str) -> None:
        _require_parts(parts, "PydubMerger")
        combined = AudioSegment.from_mp3(parts[0])
        for part in parts[1:]:
            combined += AudioSegment.from_mp3(part)
        combined.export(output_path, format="mp3")


class FFmpegMerger:
    """Merges audio parts via an FFmpeg concat-demuxer subprocess.

    Streams are copied when the output is MP3 and re-encoded otherwise.
    """

    def merge(self, parts: List[str], output_path: str) -> None:
        _require_parts(parts, "FFmpegMerger")
        fd, listfile = tempfile.mkstemp(prefix="tts_ka_concat_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for part in parts:
                    abs_path = os.path.abspath(part).replace("\\", "/")
                    # Per ffmpeg concat-demuxer spec, escape `'` as `'\''`.
                    escaped = abs_path.replace("'", "'\\''")
                    f.write(f"file '{escaped}'\n")
            argv = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", listfile,
            ]
            if output_path.lower().endswith(".mp3"):
                argv += ["-c", "copy"]
            argv.append(output_path)
            try:
                rc = subprocess.run(argv, shell=False, check=False).returncode
            except FileNotFoundError:
                raise MergeFailed("FFmpegMerger: ffmpeg is not installed") from None
            if rc != 0:
                raise MergeFailed(f"FFmpegMerger: ffmpeg exited with code {rc}")
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass


# ── Public API ────────────────────────────────────────────────────────────────

async def fast_generate_audio(text: str, language: str, output_path: str,
                               quiet: bool = False,
                               voice: Optional[str] = None,
                               prosody: Optional[ProsodyOpts] = None) -> bool:
    """Generate audio for one chunk of *text* via edge-tts.

    When *voice* is set, it overrides the per-language default from VOICE_MAP.
    When *prosody* is set with non-default rate/pitch/volume, the values are
    passed through to ``edge_tts.Communicate``.
    """
    return await EdgeTTSGenerator().generate(text, language, output_path,
                                              quiet, voice=voice,
                                              prosody=prosody)


async def generate_audio_with_subs(text: str, language: str, output_path: str,
                                    voice: Optional[str] = None,
                                    prosody: Optional[ProsodyOpts] = None
                                    ) -> List[WordEvent]:
    """Generate audio via edge-tts and collect WordBoundary events for subtitles.

    Returns a list of ``WordEvent`` collected during synthesis. Edge-tts uses
    100-nanosecond ticks for offsets, which are normalised to milliseconds.
    Transient errors are retried like ``fast_generate_audio``; a final failure
    removes the partial file and raises ``GenerationFailed``.
    """
    try:
        from edge_tts import Communicate
    except ImportError:
        raise RuntimeError(
            "Subtitle export requires the 'edge-tts' library (already a "
            "core dependency). Install it with: pip install edge-tts"
        )

    resolved_voice = voice or VOICE_MAP.get(language)
    if not resolved_voice:
        raise ValueError(f"Language {language!r} is not supported")

    clean_text = replace_not_readable(text)
    kwargs: dict = {}
    if prosody and not prosody.is_default():
        kwargs["rate"] = prosody.rate
        kwargs["pitch"] = prosody.pitch
        kwargs["volume"] = prosody.volume

    events: List[WordEvent] = []

    async def attempt() -> None:
        events.clear()
        # edge-tts >= 7 defaults to SentenceBoundary, which turns word events off.
        communicate = Communicate(clean_text, resolved_voice,
                                  boundary="WordBoundary", **kwargs)
        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                ctype = chunk.get("type")
                if ctype == "audio":
                    audio_file.write(chunk["data"])
                elif ctype == "WordBoundary":
                    # edge-tts uses 100-ns ticks; convert to ms.
                    offset_ms = int(chunk["offset"]) // 10_000
                    duration_ms = int(chunk["duration"]) // 10_000
                    events.append(
                        WordEvent(
                            text=chunk.get("text", ""),
                            start_ms=offset_ms,
                            duration_ms=duration_ms,
                        )
                    )

    try:
        await _retry_edge(attempt, EdgeTTSGenerator._EDGE_RETRIES,
                          EdgeTTSGenerator._EDGE_RETRY_BASE_DELAY)
    except Exception as exc:
        try:
            os.remove(output_path)
        except OSError:
            pass
        raise generation_failed("Subtitled audio generation failed", exc) from exc
    return events


def fast_merge_audio_files(parts: List[str], output_path: str) -> None:
    """Merge audio *parts* into *output_path*, raising ``MergeFailed`` rather than dropping audio.

    MP3 output from MP3 parts is joined losslessly by ``ConcatMp3Merger``;
    anything else goes through the re-encoding back-ends with fallbacks.
    """
    if not parts:
        raise ValueError("No parts to merge")
    out_abs = os.path.abspath(output_path)
    if any(os.path.abspath(p) == out_abs for p in parts):
        raise ValueError(f"Output {output_path!r} is also one of the parts to merge")
    if len(parts) == 1 or (
        output_path.lower().endswith(".mp3") and all(_looks_like_mp3(p) for p in parts)
    ):
        ConcatMp3Merger().merge(parts, output_path)
        return

    mergers: List[AudioMerger] = []
    if HAS_SOUNDFILE:
        mergers.append(SoundFileMerger())
    if HAS_PYDUB:
        mergers.append(PydubMerger())
    mergers.append(FFmpegMerger())

    last_error: Optional[Exception] = None
    for merger in mergers:
        try:
            merger.merge(parts, output_path)
            return
        except Exception as exc:
            last_error = exc

    raise MergeFailed(f"All merge strategies failed: {last_error}")


def _spawn_detached(argv: List[str]) -> bool:
    """Spawn *argv* in the background with no controlling terminal. Returns True on success."""
    try:
        kwargs = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(argv, **kwargs)
        return True
    except (OSError, ValueError):
        return False


def play_audio(file_path: str) -> bool:
    """Play an audio file using a platform-appropriate command (no shell).

    Returns ``True`` when a player was launched, ``False`` when no player
    could open the file so callers can tell the user instead of leaving them
    in silence.
    """
    try:
        abs_path = os.path.abspath(file_path)
        if sys.platform.startswith("win"):
            os.startfile(abs_path)
            return True
        if sys.platform == "darwin":
            return _spawn_detached(["open", abs_path])
        for player in ("mpv", "vlc", "xdg-open"):
            if shutil.which(player) and _spawn_detached([player, abs_path]):
                return True
    except OSError:
        pass
    return False
