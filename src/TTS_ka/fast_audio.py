"""Audio generation (edge-tts), merging, and playback helpers.

Design
------
``EdgeTTSGenerator`` synthesises one chunk with the ``edge-tts`` library,
retrying transient 403/429 responses with backoff.

``AudioMerger`` (Protocol) abstracts the three merge back-ends:

* ``SoundFileMerger`` — soundfile + numpy (lowest latency).
* ``PydubMerger``     — PyDub (reliable pure-Python MP3 handling).
* ``FFmpegMerger``    — subprocess ffmpeg (always available when installed).

``fast_merge_audio_files`` tries them in that order until one succeeds.

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
from typing import List, Optional, Protocol

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

        last_err: Optional[BaseException] = None
        for attempt in range(self._EDGE_RETRIES):
            try:
                communicate = Communicate(clean_text, resolved_voice, **edge_kwargs)
                await communicate.save(output_path)
                if not quiet:
                    print(f"Generated: {os.path.abspath(output_path)}")
                return True
            except Exception as e:
                last_err = e
                if (
                    attempt < self._EDGE_RETRIES - 1
                    and _edge_tts_transient(e)
                ):
                    await asyncio.sleep(
                        self._EDGE_RETRY_BASE_DELAY * (2**attempt)
                    )
                    continue
                break
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

class SoundFileMerger:
    """Merges MP3 parts via soundfile + numpy (decodes and re-encodes)."""

    def merge(self, parts: List[str], output_path: str) -> None:
        combined_data = []
        sample_rate: Optional[int] = None
        for part in parts:
            try:
                data, sr = sf.read(part)
                if sample_rate is None:
                    sample_rate = sr
                combined_data.append(data)
            except (OSError, RuntimeError, ValueError):
                continue
        if not combined_data or sample_rate is None:
            raise RuntimeError("SoundFileMerger: no valid audio parts to merge")
        final_audio = np.concatenate(combined_data, axis=0)
        sf.write(output_path, final_audio, sample_rate)


class PydubMerger:
    """Merges MP3 parts using PyDub."""

    def merge(self, parts: List[str], output_path: str) -> None:
        combined = AudioSegment.from_mp3(parts[0])
        for part in parts[1:]:
            if os.path.exists(part):
                combined += AudioSegment.from_mp3(part)
        combined.export(output_path, format="mp3")


class FFmpegMerger:
    """Merges MP3 parts via an FFmpeg concat-demuxer subprocess (stream copy)."""

    def merge(self, parts: List[str], output_path: str) -> None:
        fd, listfile = tempfile.mkstemp(prefix="tts_ka_concat_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for part in parts:
                    if os.path.exists(part):
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
                "-c", "copy",
                output_path,
            ]
            try:
                result = subprocess.run(argv, shell=False, check=False)
                rc = result.returncode
            except FileNotFoundError:
                rc = 127
            if rc != 0:
                # Last resort: copy first part so caller always has *something*
                if os.path.exists(parts[0]):
                    shutil.copy2(parts[0], output_path)
                else:
                    raise RuntimeError("FFmpegMerger: no valid parts found")
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

    communicate = Communicate(clean_text, resolved_voice, **kwargs)
    events: List[WordEvent] = []
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
    return events


def fast_merge_audio_files(parts: List[str], output_path: str) -> None:
    """Merge audio parts using the best available strategy, with fallbacks."""
    if not parts:
        raise ValueError("No parts to merge")
    if os.path.exists(output_path):
        os.remove(output_path)
    if len(parts) == 1:
        if os.path.abspath(parts[0]) != os.path.abspath(output_path):
            shutil.copy2(parts[0], output_path)
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

    raise RuntimeError(f"All merge strategies failed: {last_error}")


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
