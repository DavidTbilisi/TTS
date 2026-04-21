"""Fast audio generation using optimized HTTP client and streaming.

Design
------
``AudioGenerator`` (Protocol) decouples callers from the concrete TTS
back-end.  Two implementations are provided:

* ``HttpAudioGenerator``  — direct Azure Cognitive Services call (fastest).
* ``EdgeTTSGenerator``    — edge-tts library fallback.

``AudioMerger`` (Protocol) abstracts the three merge back-ends:

* ``SoundFileMerger`` — soundfile + numpy (lowest latency).
* ``PydubMerger``     — PyDub (reliable pure-Python MP3 handling).
* ``FFmpegMerger``    — subprocess ffmpeg (always available when installed).

``MergerFactory.create()`` picks the best available merger at runtime.

The module-level ``fast_generate_audio`` / ``fast_merge_audio_files`` /
``play_audio`` functions are the public API used by the rest of the package.
"""

from __future__ import annotations

import os
import sys

# If set, skip unofficial Bing HTTP TTS (often 401/403) and use edge-tts only.
_SKIP_HTTP_ENV = "TTS_KA_SKIP_HTTP"
import asyncio
import shutil
from typing import List, Optional, Protocol, runtime_checkable

import httpx

try:
    import uvloop
    HAS_UVLOOP = True
except ImportError:
    HAS_UVLOOP = False

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

from .constants import (
    VOICE_MAP,
    HTTP_TIMEOUT_TOTAL,
    HTTP_TIMEOUT_CONNECT,
    HTTP_MAX_KEEPALIVE,
    HTTP_MAX_CONNECTIONS,
)
from .not_reading import replace_not_readable


# ── Protocols ─────────────────────────────────────────────────────────────────

@runtime_checkable
class AudioGenerator(Protocol):
    """Interface for a single-chunk TTS generator."""

    async def generate(self, text: str, language: str, output_path: str,
                       quiet: bool = False) -> bool:
        """Generate audio from *text* and write it to *output_path*.

        Returns ``True`` on success, ``False`` on failure.
        """
        ...


class AudioMerger(Protocol):
    """Interface for merging multiple audio part-files into one output file."""

    def merge(self, parts: List[str], output_path: str) -> None:
        """Concatenate *parts* and write the result to *output_path*."""
        ...


# ── Shared HTTP client (module-level singleton) ───────────────────────────────

_http_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client, creating it on first call."""
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(
            max_keepalive_connections=HTTP_MAX_KEEPALIVE,
            max_connections=HTTP_MAX_CONNECTIONS,
        )
        timeout = httpx.Timeout(HTTP_TIMEOUT_TOTAL, connect=HTTP_TIMEOUT_CONNECT)
        _http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _http_client


# ── AudioGenerator implementations ───────────────────────────────────────────

class HttpAudioGenerator:
    """Primary generator: direct Azure Cognitive Services TTS endpoint.

    Uses the shared ``httpx.AsyncClient`` for connection reuse and streams
    the response directly to disk in 8 KB chunks.
    """

    _TTS_URL = "https://speech.platform.bing.com/synthesize"
    _HEADERS = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "Mozilla/5.0",
    }

    async def generate(self, text: str, language: str, output_path: str,
                       quiet: bool = False) -> bool:
        voice = VOICE_MAP.get(language)
        if not voice:
            if not quiet:
                print(f"❌ Language '{language}' not supported. Use: {', '.join(VOICE_MAP)}")
            return False

        safe_text = replace_not_readable(text)
        ssml = (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{voice}'>{safe_text}</voice></speak>"
        )
        try:
            client = await get_http_client()
            async with client.stream(
                "POST", self._TTS_URL, headers=self._HEADERS, content=ssml.encode()
            ) as response:
                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                    if not quiet:
                        print(f"⚡ Generated: {os.path.abspath(output_path)}")
                    return True
                return False
        except (httpx.HTTPError, httpx.TimeoutException, OSError):
            return False


def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _edge_tts_transient(err: BaseException) -> bool:
    msg = str(err).lower()
    return "403" in msg or "invalid response status" in msg or "429" in msg


class EdgeTTSGenerator:
    """Fallback generator using the ``edge-tts`` library."""

    _EDGE_RETRIES = 3
    _EDGE_RETRY_BASE_DELAY = 0.45

    async def generate(self, text: str, language: str, output_path: str,
                       quiet: bool = False) -> bool:
        voice = VOICE_MAP.get(language)
        if not voice:
            if not quiet:
                print(f"❌ Language '{language}' not supported. Use: {', '.join(VOICE_MAP)}")
            return False
        from edge_tts import Communicate

        clean_text = replace_not_readable(text)
        last_err: Optional[BaseException] = None
        for attempt in range(self._EDGE_RETRIES):
            try:
                communicate = Communicate(clean_text, voice)
                await communicate.save(output_path)
                if not quiet:
                    print(f"Generated (fallback): {os.path.abspath(output_path)}")
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
        if not quiet:
            print(f"Error generating audio: {last_err}")
            if last_err is not None and _edge_tts_transient(last_err):
                print(
                    "Hint: Microsoft often returns 403 until edge-tts tokens are updated. "
                    "Try: pip install -U 'edge-tts>=7.2.7' "
                    f"or set {_SKIP_HTTP_ENV}=1 to skip the fast HTTP path."
                )
        return False


# ── AudioMerger implementations ───────────────────────────────────────────────

class SoundFileMerger:
    """Merges MP3 parts via soundfile + numpy (fastest; lossless concat)."""

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
    """Merges MP3 parts via an FFmpeg concat-demuxer subprocess."""

    _LISTFILE = ".ff_concat.txt"

    def merge(self, parts: List[str], output_path: str) -> None:
        try:
            with open(self._LISTFILE, "w", encoding="utf-8") as f:
                for part in parts:
                    if os.path.exists(part):
                        abs_path = os.path.abspath(part).replace("\\", "/")
                        f.write(f"file '{abs_path}'\n")
            cmd = (
                f'ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 '
                f'-i "{self._LISTFILE}" -c copy "{output_path}"'
            )
            rc = os.system(cmd)
            if rc != 0:
                # Last resort: copy first part so caller always has *something*
                if os.path.exists(parts[0]):
                    shutil.copy2(parts[0], output_path)
                else:
                    raise RuntimeError("FFmpegMerger: no valid parts found")
        finally:
            try:
                os.remove(self._LISTFILE)
            except OSError:
                pass


class MergerFactory:
    """Returns the fastest ``AudioMerger`` supported by the current environment."""

    @staticmethod
    def create() -> AudioMerger:
        if HAS_SOUNDFILE:
            return SoundFileMerger()
        if HAS_PYDUB:
            return PydubMerger()
        return FFmpegMerger()


# ── Public API ────────────────────────────────────────────────────────────────

async def fast_generate_audio(text: str, language: str, output_path: str,
                               quiet: bool = False) -> bool:
    """Generate audio: try HTTP first, fall back to edge-tts on any failure.

    Environment variables:

    * ``TTS_KA_SKIP_HTTP=1`` — skip the unofficial Bing HTTP shortcut (often
      blocked with 401/403) and use edge-tts only.
    * ``TTS_KA_VERBOSE=1`` — print a notice when falling back from HTTP to
      edge-tts (off by default; HTTP failure is normal for many networks).
    """
    if HAS_UVLOOP and sys.platform != "win32":
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    if not _env_truthy(_SKIP_HTTP_ENV) and await HttpAudioGenerator().generate(
        text, language, output_path, quiet=True
    ):
        if not quiet:
            print(f"⚡ Generated: {os.path.abspath(output_path)}")
        return True

    if _env_truthy("TTS_KA_VERBOSE") and not quiet:
        print("Notice: Bing HTTP TTS unavailable; using edge-tts.", flush=True)
    return await EdgeTTSGenerator().generate(text, language, output_path, quiet)


async def fallback_generate_audio(text: str, language: str, output_path: str,
                                   quiet: bool = False) -> bool:
    """Generate audio using edge-tts directly (skips the HTTP attempt)."""
    return await EdgeTTSGenerator().generate(text, language, output_path, quiet)


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


def play_audio(file_path: str) -> None:
    """Play an audio file using a platform-appropriate command."""
    try:
        abs_path = os.path.abspath(file_path)
        if sys.platform.startswith("win"):
            os.startfile(abs_path)
        elif sys.platform == "darwin":
            os.system(f"open '{abs_path}' &")
        else:
            for cmd in [f"mpv '{abs_path}' &", f"vlc '{abs_path}' &", f"xdg-open '{abs_path}' &"]:
                if os.system(cmd) == 0:
                    break
    except OSError:
        pass


async def cleanup_http() -> None:
    """Close and discard the shared HTTP client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
