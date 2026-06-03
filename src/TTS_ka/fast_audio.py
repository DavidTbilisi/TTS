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
import json
import shutil
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:  # httpx is imported lazily at runtime (only for the HTTP path)
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
    SSML_LANG_MAP,
    HTTP_TIMEOUT_TOTAL,
    HTTP_TIMEOUT_CONNECT,
    HTTP_MAX_KEEPALIVE,
    HTTP_MAX_CONNECTIONS,
)
from .not_reading import replace_not_readable
from .prosody import ProsodyOpts, to_ssml_attrs
from .subtitles import WordEvent


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


async def get_http_client() -> "httpx.AsyncClient":
    """Return the shared async HTTP client, creating it on first call."""
    global _http_client
    if _http_client is None:
        import httpx
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
                       quiet: bool = False, voice: Optional[str] = None,
                       prosody: Optional[ProsodyOpts] = None) -> bool:
        resolved_voice = voice or VOICE_MAP.get(language)
        if not resolved_voice:
            if not quiet:
                print(f"❌ Language '{language}' not supported. Use: {', '.join(VOICE_MAP)}")
            return False

        safe_text = replace_not_readable(text)
        xml_lang = SSML_LANG_MAP.get(language, "en-US")
        if prosody and not prosody.is_default():
            inner = f"<prosody {to_ssml_attrs(prosody)}>{safe_text}</prosody>"
        else:
            inner = safe_text
        ssml = (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{xml_lang}'>"
            f"<voice name='{resolved_voice}'>{inner}</voice></speak>"
        )
        import httpx
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


# ── HTTP health circuit breaker ───────────────────────────────────────────────
# The unofficial Bing HTTP endpoint almost always returns 401/403 today. Probing
# it on every chunk — and on every fresh ``python -m TTS_ka`` process (each hotkey
# press is a new process) — wastes ~0.7s each time, which directly inflates
# streaming's time-to-first-audio. We remember a recent "down" verdict (in memory
# for this process, on disk for later runs) and skip the doomed request until a
# TTL elapses, re-probing afterward so a recovered endpoint is picked up again.

_HTTP_STATE_ENV = "TTS_KA_HTTP_STATE"   # override marker path (used by tests)
_HTTP_RECHECK_TTL = 6 * 3600.0          # seconds before re-probing a down endpoint
_http_down_memo: Optional[bool] = None  # process cache: None=unknown/not-probed


def _http_state_path() -> str:
    """Path to the tiny persisted HTTP-health marker."""
    override = os.environ.get(_HTTP_STATE_ENV)
    if override:
        return override
    base = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_CACHE_HOME")
        or tempfile.gettempdir()
    )
    return os.path.join(base, "tts_ka_http_health.json")


def _http_should_skip(now: Optional[float] = None) -> bool:
    """Return True if a recent probe found the HTTP endpoint down."""
    global _http_down_memo
    if _http_down_memo is not None:
        return _http_down_memo
    if now is None:
        now = time.time()
    try:
        with open(_http_state_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if bool(data.get("down")) and (now - float(data.get("ts", 0.0))) < _HTTP_RECHECK_TTL:
            _http_down_memo = True
            return True
    except (OSError, ValueError, TypeError):
        pass
    return False


def _http_record(ok: bool, now: Optional[float] = None) -> None:
    """Persist the probe result: clear the marker on success, write it on failure."""
    global _http_down_memo
    _http_down_memo = not ok
    path = _http_state_path()
    if ok:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    if now is None:
        now = time.time()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"down": True, "ts": now}, fh)
    except OSError:
        pass


def _reset_http_health() -> None:
    """Clear the in-process memo (test hook; does not touch disk)."""
    global _http_down_memo
    _http_down_memo = None


def _edge_tts_transient(err: BaseException) -> bool:
    msg = str(err).lower()
    return "403" in msg or "invalid response status" in msg or "429" in msg


class EdgeTTSGenerator:
    """Fallback generator using the ``edge-tts`` library."""

    _EDGE_RETRIES = 3
    _EDGE_RETRY_BASE_DELAY = 0.45

    async def generate(self, text: str, language: str, output_path: str,
                       quiet: bool = False, voice: Optional[str] = None,
                       prosody: Optional[ProsodyOpts] = None) -> bool:
        resolved_voice = voice or VOICE_MAP.get(language)
        if not resolved_voice:
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
                "-i", self._LISTFILE,
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
                               quiet: bool = False,
                               voice: Optional[str] = None,
                               prosody: Optional[ProsodyOpts] = None) -> bool:
    """Generate audio: try HTTP first, fall back to edge-tts on any failure.

    When *voice* is set, it overrides the per-language default from VOICE_MAP.
    When *prosody* is set with non-default rate/pitch/volume, wraps the SSML
    in a ``<prosody>`` tag (HTTP path) or passes the kwargs to ``Communicate``
    (edge-tts path).

    Environment variables:

    * ``TTS_KA_SKIP_HTTP=1`` — skip the unofficial Bing HTTP shortcut (often
      blocked with 401/403) and use edge-tts only.
    * ``TTS_KA_VERBOSE=1`` — print a notice when falling back from HTTP to
      edge-tts (off by default; HTTP failure is normal for many networks).
    """
    if HAS_UVLOOP and sys.platform != "win32":
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    # Skip the HTTP probe entirely when disabled by env or when the circuit
    # breaker recently saw it fail (saves ~0.7s of doomed request per chunk).
    if not _env_truthy(_SKIP_HTTP_ENV) and not _http_should_skip():
        http_ok = await HttpAudioGenerator().generate(
            text, language, output_path, quiet=True, voice=voice, prosody=prosody
        )
        _http_record(http_ok)
        if http_ok:
            if not quiet:
                print(f"⚡ Generated: {os.path.abspath(output_path)}")
            return True

    if _env_truthy("TTS_KA_VERBOSE") and not quiet:
        print("Notice: Bing HTTP TTS unavailable; using edge-tts.", flush=True)
    return await EdgeTTSGenerator().generate(text, language, output_path,
                                              quiet, voice=voice,
                                              prosody=prosody)


async def fallback_generate_audio(text: str, language: str, output_path: str,
                                   quiet: bool = False,
                                   voice: Optional[str] = None,
                                   prosody: Optional[ProsodyOpts] = None) -> bool:
    """Generate audio using edge-tts directly (skips the HTTP attempt)."""
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


async def cleanup_http() -> None:
    """Close and discard the shared HTTP client."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
