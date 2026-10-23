"""MCP server exposing TTS_ka to AI clients (Claude Code, Claude Desktop, etc).

Tools:

- ``speak(text, lang?, voice?, blocking?)`` — synthesize and play immediately.
- ``stream_open(lang?, voice?)`` → session_id — start an incremental session.
- ``stream_append(session_id, text)`` — push text; speaks complete sentences.
- ``stream_close(session_id)`` — drain remaining buffer and stop accepting input.
- ``session_status(session_id)`` — progress, pending/failed synths, buffer preview.
- ``list_sessions()`` — IDs of all active streaming sessions.
- ``stop()`` — terminate all active playback and sessions.
- ``list_voices(lang?)`` — return the voice catalog.

Transport: stdio (JSON-RPC). Because stdout is reserved for the protocol,
mcp's ``stdio_server`` points fd 1 at stderr while serving, so decorative
``print()`` from underlying modules (and subprocesses) never reaches the wire.

Run via ``TTS_ka-mcp`` (installed entry point) or ``python -m TTS_ka.mcp_server``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Coroutine, Dict, List, Optional, Set

from .fast_audio import fast_generate_audio, generation_failed, play_audio
from .live_stream import DEFAULT_IDLE_FLUSH_MS, SentenceBuffer
from .not_reading import replace_not_readable
from .prosody import ProsodyOpts, parse_pitch, parse_rate, parse_volume
from .streaming_player import StreamingAudioPlayer, stop_active_streaming_player
from .user_config import argparse_defaults_from_config, load_user_config
from . import voices as _voices
from .constants import PLAYBACK_JOIN_TIMEOUT


MAX_SESSIONS = 8
MAX_CONCURRENT_PER_SESSION = 4
# Extra seconds a one-shot clip's files are kept past its measured duration
# (covers player start-up), and how long to keep them when ffprobe can't
# measure the duration at all.
PLAYBACK_GRACE_SECONDS = 5.0
UNKNOWN_DURATION_KEEP_SECONDS = float(PLAYBACK_JOIN_TIMEOUT)


# ── Temp-dir lifecycle ────────────────────────────────────────────────────────
#
# Synthesized MP3s live in per-call / per-session temp dirs. They can't be
# removed when a tool returns, because the player may still be reading them,
# so each dir is removed once its playback is over. Every dir is also recorded
# here so main() can sweep whatever is left (unclosed sessions, the no-player
# path, cleanup tasks cancelled at shutdown) when the server exits.

_tmp_dirs: Set[str] = set()
_cleanup_tasks: Set["asyncio.Task[None]"] = set()  # strong refs for create_task


def _make_tmp_dir(prefix: str) -> str:
    path = tempfile.mkdtemp(prefix=prefix)
    _tmp_dirs.add(path)
    return path


def _remove_tmp_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
    _tmp_dirs.discard(path)


def _remove_all_tmp_dirs() -> None:
    """Remove every temp dir this process created that is still on disk."""
    for path in list(_tmp_dirs):
        _remove_tmp_dir(path)


def _spawn_cleanup(coro: Coroutine[None, None, None]) -> None:
    task = asyncio.create_task(coro)
    _cleanup_tasks.add(task)
    task.add_done_callback(_cleanup_tasks.discard)


async def _remove_after_clip(tmp_dir: str, path: str) -> None:
    """Remove a one-shot clip's dir once it has had time to finish playing.

    ``play_audio`` launches a detached player and keeps no handle to it, so
    the clip's measured duration is the only end-of-playback signal.
    """
    dur = await asyncio.to_thread(_audio_duration_seconds, path)
    keep = dur + PLAYBACK_GRACE_SECONDS if dur else UNKNOWN_DURATION_KEEP_SECONDS
    await asyncio.sleep(keep)
    _remove_tmp_dir(tmp_dir)


def _audio_duration_seconds(path: str) -> Optional[float]:
    """Best-effort audio duration in seconds (via ffprobe through pydub).

    Used to make ``speak(blocking=True)`` wait for playback to finish.
    Returns ``None`` when the duration can't be determined.
    """
    try:
        from pydub.utils import mediainfo
        info = mediainfo(path)
        raw = info.get("duration")
        return float(raw) if raw else None
    except Exception:  # noqa: BLE001 - any failure → unknown duration
        return None


def _describe_settings(lang: str, voice: Optional[str],
                       prosody: Optional[ProsodyOpts]) -> str:
    """Short human-readable echo of the resolved synthesis settings."""
    parts = [f"lang={lang}", f"voice={voice or 'default'}"]
    if prosody is not None:
        parts.append(f"rate={prosody.rate}")
        parts.append(f"pitch={prosody.pitch}")
        parts.append(f"volume={prosody.volume}")
    return ", ".join(parts)


class _LiveSession:
    """Long-lived sentence buffer + streaming player for one MCP stream."""

    def __init__(self, lang: str, voice: Optional[str],
                 prosody: Optional[ProsodyOpts] = None) -> None:
        self.lang = lang
        self.voice = voice
        self.prosody = prosody
        self.buf = SentenceBuffer(idle_flush_ms=DEFAULT_IDLE_FLUSH_MS)
        self.player = StreamingAudioPlayer(show_gui=False)
        self.player.start()
        self.tmp_dir = _make_tmp_dir("ttska-mcp-")
        self._idx = 0      # output-file counter (incremented inside _speak)
        self._queued = 0   # sentences ever scheduled — visible in status
        self._failed = 0   # synth tasks that raised — visible in status
        self._last_error: Optional[str] = None
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_PER_SESSION)
        self._tasks: List[asyncio.Task] = []
        self._closed = False

    async def feed(self, text: str) -> int:
        """Append text; spawn synth tasks for any complete sentences. Return count."""
        if self._closed:
            raise RuntimeError("session already closed")
        sentences = self.buf.feed(text)
        for s in sentences:
            self._queued += 1
            self._tasks.append(asyncio.create_task(self._speak(s)))
        return len(sentences)

    def synths_pending(self) -> int:
        """Count of synthesis tasks not yet finished."""
        return sum(1 for t in self._tasks if not t.done())

    def status(self) -> Dict[str, object]:
        """Snapshot of session state for the ``session_status`` tool."""
        preview = self.buf.buffer
        return {
            "lang": self.lang,
            "voice": self.voice,
            "rate": self.prosody.rate if self.prosody else None,
            "pitch": self.prosody.pitch if self.prosody else None,
            "volume": self.prosody.volume if self.prosody else None,
            "closed": self._closed,
            "total_sentences": self._queued,
            "synths_pending": self.synths_pending(),
            "synths_failed": self._failed,
            "last_error": self._last_error,
            "buffer_chars": len(preview),
            "buffer_preview": preview[:400],
        }

    async def _speak(self, sentence: str) -> None:
        async with self._sem:
            cleaned = replace_not_readable(sentence)
            if not cleaned.strip():
                return
            idx = self._idx
            self._idx += 1
            path = os.path.join(self.tmp_dir, f".part_{idx:04d}.mp3")
            try:
                ok = await fast_generate_audio(cleaned, self.lang, path,
                                               voice=self.voice, prosody=self.prosody)
                if ok is False:
                    raise generation_failed("synthesis failed")
                self.player.add_chunk(path, chunk_index=idx)
            except Exception as exc:  # noqa: BLE001
                self._failed += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                print(f"⚠️  synth failed (idx={idx}): {exc}", file=sys.stderr)

    async def close(self) -> int:
        """Drain partial buffer, await pending synths, signal player end of input.

        Does not block on actual playback — the player thread keeps running
        until the queue drains in the background.

        Returns the total number of sentences spoken.
        """
        if self._closed:
            return self._idx
        self._closed = True
        tail = self.buf.drain(force=True)
        if tail:
            self._queued += 1
            self._tasks.append(asyncio.create_task(self._speak(tail)))
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        try:
            self.player.finish_generation()
        except Exception:
            pass
        _spawn_cleanup(self._remove_tmp_after_playback())
        return self._queued

    async def _remove_tmp_after_playback(self) -> None:
        """Remove the session's MP3s once the player is done with them.

        The playback thread exits when the queue drains, but VLC / mplayer
        (and the Unix fallback) only *launch* a process and return, so also
        wait for ``player.process`` before deleting.
        """
        await asyncio.to_thread(self.player.wait_for_completion)
        proc = self.player.process
        if proc is not None and proc.poll() is None:
            try:
                await asyncio.to_thread(proc.wait, PLAYBACK_JOIN_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
        _remove_tmp_dir(self.tmp_dir)

    def hard_stop(self) -> None:
        """Synchronous teardown — kills the player and removes the tmp dir."""
        self._closed = True
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.player.finish_generation()
        except Exception:
            pass
        _remove_tmp_dir(self.tmp_dir)


# ── Server factory ────────────────────────────────────────────────────────────


def _resolve_prosody(rate: Optional[str], pitch: Optional[str], volume: Optional[str],
                     default: ProsodyOpts) -> Optional[ProsodyOpts]:
    """Merge per-call rate/pitch/volume on top of the config-driven *default*.

    Returns ``None`` if both per-call and default are all-zero (no SSML wrap).
    Bad per-call values raise SystemExit inside parse_*; we map those to
    silently falling back to the default so a typo from the agent doesn't
    crash the MCP session.
    """
    try:
        merged = ProsodyOpts(
            rate=parse_rate(rate) if rate is not None else default.rate,
            pitch=parse_pitch(pitch) if pitch is not None else default.pitch,
            volume=parse_volume(volume) if volume is not None else default.volume,
        )
    except SystemExit:
        merged = default
    return None if merged.is_default() else merged


def _load_default_prosody() -> ProsodyOpts:
    """Read rate/pitch/volume from the user config; tolerate any bad input."""
    try:
        cfg = load_user_config()
        defs = argparse_defaults_from_config(cfg)
        rate, pitch, volume = defs.get("rate"), defs.get("pitch"), defs.get("volume")
        if rate is None and pitch is None and volume is None:
            return ProsodyOpts()
        return ProsodyOpts(
            rate=parse_rate(rate) if rate is not None else "+0%",
            pitch=parse_pitch(pitch) if pitch is not None else "+0Hz",
            volume=parse_volume(volume) if volume is not None else "+0%",
        )
    except (SystemExit, Exception):
        return ProsodyOpts()


def build_server(sessions: Optional[Dict[str, _LiveSession]] = None,
                 default_prosody: Optional[ProsodyOpts] = None):
    """Construct an MCPServer with the TTS_ka tools registered.

    *sessions* is the session dict — exposed so tests can inspect state.
    *default_prosody* overrides the config-derived default (useful for tests).
    """
    from mcp.server.mcpserver import MCPServer  # local import: optional extra

    server = MCPServer(
        "tts-ka",
        instructions=(
            "Text-to-speech for AI agents. Use `speak` for one-shot lines, "
            "or `stream_open` + `stream_append` to read text as you generate it. "
            "Call `stream_close` when done, or `stop` to abort all audio."
        ),
    )
    sessions = sessions if sessions is not None else {}
    default_prosody = default_prosody if default_prosody is not None else _load_default_prosody()

    @server.tool()
    async def speak(text: str, lang: str = "en",
                    voice: Optional[str] = None,
                    rate: Optional[str] = None,
                    pitch: Optional[str] = None,
                    volume: Optional[str] = None,
                    blocking: bool = False) -> str:
        """Speak *text* immediately.

        With ``blocking=False`` (default) the call returns as soon as
        playback is launched. With ``blocking=True`` it waits for the audio's
        full duration before returning, so an agent can sequence speech
        without overlapping. The return string echoes the resolved settings.

        rate / pitch / volume are signed percentages or Hz (rate '+30%',
        pitch '+5Hz' or '-10%', volume '-25%'). Unspecified values fall
        back to the server-wide defaults from ``~/.tts_config.json``.
        """
        cleaned = replace_not_readable(text)
        if not cleaned.strip():
            return "skipped: empty"
        prosody = _resolve_prosody(rate, pitch, volume, default_prosody)
        echo = _describe_settings(lang, voice, prosody)
        tmp_dir = _make_tmp_dir("ttska-mcp-one-")
        path = os.path.join(tmp_dir, "out.mp3")
        try:
            ok = await fast_generate_audio(cleaned, lang, path,
                                           voice=voice, prosody=prosody)
            if ok is False:
                raise generation_failed("synthesis failed")
        except Exception as exc:  # noqa: BLE001
            _remove_tmp_dir(tmp_dir)
            return f"error: {exc}"
        played = play_audio(path)
        if not played:
            # Kept so the agent/user can open it; swept when the server exits.
            return f"error: no audio player available; saved {path} [{echo}]"
        if blocking:
            # Truly wait for playback: sleep for the audio's measured duration
            # so the agent can sequence speech instead of racing ahead.
            dur = await asyncio.to_thread(_audio_duration_seconds, path)
            if dur:
                await asyncio.sleep(dur + 0.3)
                _remove_tmp_dir(tmp_dir)
                return f"played in {dur:.1f}s [{echo}]"
            # Unknown length: the player may still be reading the file.
            _spawn_cleanup(_remove_after_clip(tmp_dir, path))
            return f"played [{echo}]"
        _spawn_cleanup(_remove_after_clip(tmp_dir, path))
        return f"queued {path} [{echo}]"

    @server.tool()
    async def stream_open(lang: str = "en",
                          voice: Optional[str] = None,
                          rate: Optional[str] = None,
                          pitch: Optional[str] = None,
                          volume: Optional[str] = None) -> str:
        """Open a streaming session. Returns the session_id to use with stream_append/close.

        Prosody (rate / pitch / volume) is locked in at open time and applies
        to every sentence in the session. Unspecified values fall back to
        the server-wide defaults from ``~/.tts_config.json``.
        """
        if len(sessions) >= MAX_SESSIONS:
            return f"error: max {MAX_SESSIONS} concurrent sessions"
        prosody = _resolve_prosody(rate, pitch, volume, default_prosody)
        sid = uuid.uuid4().hex[:12]
        sessions[sid] = _LiveSession(lang=lang, voice=voice, prosody=prosody)
        return sid

    @server.tool()
    async def stream_append(session_id: str, text: str) -> str:
        """Push *text* to a streaming session. Speaks each complete sentence."""
        sess = sessions.get(session_id)
        if sess is None:
            return f"error: unknown session_id {session_id!r}"
        try:
            n = await sess.feed(text)
        except RuntimeError as exc:
            return f"error: {exc}"
        return f"queued {n} sentence(s)"

    @server.tool()
    async def stream_close(session_id: str) -> str:
        """Drain the remaining buffer, await pending synths, end the session."""
        sess = sessions.pop(session_id, None)
        if sess is None:
            return f"error: unknown session_id {session_id!r}"
        total = await sess.close()
        return f"closed: spoke {total} chunk(s)"

    @server.tool()
    async def session_status(session_id: str) -> Dict[str, object]:
        """Return progress info for a streaming session.

        Fields: lang, voice, rate, pitch, volume, closed, total_sentences,
        synths_pending, synths_failed, last_error, buffer_chars,
        buffer_preview. Useful for an agent to decide whether to keep
        streaming or wait for synths to drain, and to detect failed synths
        (synths_failed > 0 with the most recent message in last_error).
        """
        sess = sessions.get(session_id)
        if sess is None:
            return {"error": f"unknown session_id {session_id!r}"}
        snap = sess.status()
        snap["session_id"] = session_id
        return snap

    @server.tool()
    async def list_sessions() -> List[Dict[str, object]]:
        """Return a brief snapshot of every active session."""
        out: List[Dict[str, object]] = []
        for sid, sess in sessions.items():
            out.append({
                "session_id": sid,
                "lang": sess.lang,
                "voice": sess.voice,
                "closed": sess._closed,
                "total_sentences": sess._queued,
                "synths_pending": sess.synths_pending(),
                "synths_failed": sess._failed,
            })
        return out

    @server.tool()
    async def stop() -> str:
        """Abort all playback and tear down every session."""
        try:
            stop_active_streaming_player()
        except Exception:
            pass
        n = len(sessions)
        for sess in list(sessions.values()):
            sess.hard_stop()
        sessions.clear()
        return f"stopped {n} session(s)"

    @server.tool()
    def list_voices(lang: Optional[str] = None) -> List[Dict[str, str]]:
        """Return available voices. Optionally filter by catalog lang (ka, ru, en)."""
        catalog = (lang and _voices.voices_for_lang(lang)) or _voices.all_voices()
        return [
            {
                "id": v.id,
                "lang": v.lang,
                "locale": v.locale,
                "gender": v.gender,
                "display_name": v.display_name,
            }
            for v in catalog
        ]

    return server


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio.

    mcp >= 2 diverts fd 1 to stderr for the life of the transport and frames
    JSON-RPC on a private duplicate of the real stdout, so stray ``print()``
    from edge-tts, players, etc. cannot corrupt the protocol stream.

    stdout is a pipe here, so it is block-buffered: a print still sitting in
    the buffer at shutdown would flush *after* fd 1 is restored and land on
    the wire. Line buffering flushes each print while fd 1 is still diverted.
    """
    sys.stdout.reconfigure(line_buffering=True)
    try:
        build_server().run("stdio")
    finally:
        _remove_all_tmp_dirs()


if __name__ == "__main__":
    main()
