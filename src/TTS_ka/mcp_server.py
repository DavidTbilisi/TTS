"""MCP server exposing TTS_ka to AI clients (Claude Code, Claude Desktop, etc).

Tools:

- ``speak(text, lang?, voice?, blocking?, interrupt?)`` — synthesize and play immediately.
- ``stream_open(lang?, voice?)`` → session_id — start an incremental session.
- ``stream_append(session_id, text)`` — push text; speaks complete sentences.
- ``stream_close(session_id)`` — drain remaining buffer and stop accepting input.
- ``session_status(session_id)`` — progress, pending/failed synths, buffer preview.
- ``list_sessions()`` — IDs of all active streaming sessions.
- ``pause`` / ``resume`` / ``skip(session_id?)`` — control playback (mpv over IPC).
- ``stop(session_id?)`` — terminate one session, or all playback and sessions.
- ``list_voices(lang?)`` — return the voice catalog.

Failures (unknown session, bad lang/voice, synthesis error, no player) are
raised as ``ToolError``, so clients see an ``isError`` result rather than a
string to parse.

Transport: stdio (JSON-RPC). Because stdout is reserved for the protocol,
mcp's ``stdio_server`` points fd 1 at stderr while serving, so decorative
``print()`` from underlying modules (and subprocesses) never reaches the wire.

Run via ``TTS_ka-mcp`` (installed entry point) or ``python -m TTS_ka.mcp_server``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import time
import uuid
from typing import Callable, Coroutine, Dict, List, Optional, Set

from .fast_audio import fast_generate_audio, generation_failed, play_audio
from .live_stream import SentenceBuffer
from .not_reading import replace_not_readable
from .prosody import ProsodyOpts, parse_pitch, parse_rate, parse_volume
from .streaming_player import PlayerDetector, StreamingAudioPlayer, stop_all_streaming_players
from .user_config import argparse_defaults_from_config, load_user_config
from . import voices as _voices
from .constants import PLAYBACK_JOIN_TIMEOUT


MAX_SESSIONS = 8
MAX_CONCURRENT_PER_SESSION = 4
# A partial sentence is spoken after this much silence from the agent, so the
# last words of an append don't wait for the next append or stream_close.
MCP_IDLE_FLUSH_MS = 500
# Sessions with no append for this long are closed and torn down (an agent
# that forgot stream_close must not hold a player and a session slot forever).
SESSION_IDLE_TIMEOUT_S = 900.0
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
        self.buf = SentenceBuffer(idle_flush_ms=MCP_IDLE_FLUSH_MS)
        self.player = StreamingAudioPlayer(show_gui=False)
        self.player.start()
        self.tmp_dir = _make_tmp_dir("ttska-mcp-")
        # Sentences ever scheduled. Also each sentence's playback index, so
        # the player knows which index an empty or failed sentence leaves out.
        self._queued = 0
        self._spoken = 0   # sentences handed to the player
        self._failed = 0   # synth tasks that raised — visible in status
        self._last_error: Optional[str] = None
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_PER_SESSION)
        self._tasks: List[asyncio.Task] = []
        self._closed = False
        self._idle_timer: Optional[asyncio.TimerHandle] = None
        self.last_activity = time.monotonic()

    async def feed(self, text: str) -> int:
        """Append text; spawn synth tasks for any complete sentences. Return count.

        Each append is treated as a complete message, so a sentence ending
        right at its end is spoken now; a trailing fragment is spoken after
        ``MCP_IDLE_FLUSH_MS`` unless more text arrives first.
        """
        if self._closed:
            raise RuntimeError("session already closed")
        self.last_activity = time.monotonic()
        sentences = self.buf.feed(text, eager_end=True)
        for s in sentences:
            self._schedule(s)
        self._arm_idle_flush()
        return len(sentences)

    def _schedule(self, sentence: str) -> None:
        idx = self._queued
        self._queued += 1
        self._tasks.append(asyncio.create_task(self._speak(sentence, idx)))

    def _arm_idle_flush(self) -> None:
        self._cancel_idle_flush()
        if self.buf.buffer.strip():
            loop = asyncio.get_running_loop()
            self._idle_timer = loop.call_later(MCP_IDLE_FLUSH_MS / 1000.0, self._idle_flush)

    def _cancel_idle_flush(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_flush(self) -> None:
        self._idle_timer = None
        if self._closed:
            return
        tail = self.buf.drain()  # held back while a code fence is open
        if tail:
            self._schedule(tail)

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
            "controllable": bool(getattr(self.player, "controllable", False)),
        }

    async def _speak(self, sentence: str, idx: int) -> None:
        added = False
        try:
            async with self._sem:
                cleaned = replace_not_readable(sentence)
                if not cleaned.strip():
                    return
                path = os.path.join(self.tmp_dir, f".part_{idx:04d}.mp3")
                try:
                    ok = await fast_generate_audio(cleaned, self.lang, path,
                                                   voice=self.voice, prosody=self.prosody)
                    if ok is False:
                        raise generation_failed("synthesis failed")
                    self.player.add_chunk(path, chunk_index=idx)
                    added = True
                    self._spoken += 1
                except Exception as exc:  # noqa: BLE001
                    self._failed += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    print(f"⚠️  synth failed (idx={idx}): {exc}", file=sys.stderr)
        finally:
            if not added:
                # Later sentences must not wait for one that will never play.
                self.player.skip_index(idx)

    async def close(self) -> int:
        """Drain partial buffer, await pending synths, signal player end of input.

        Does not block on actual playback — the player thread keeps running
        until the queue drains in the background.

        Returns the number of sentences handed to the player.
        """
        if self._closed:
            return self._spoken
        self._closed = True
        self._cancel_idle_flush()
        tail = self.buf.drain(force=True)
        if tail:
            self._schedule(tail)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        try:
            self.player.finish_generation()
        except Exception:
            pass
        _spawn_cleanup(self._remove_tmp_after_playback())
        return self._spoken

    async def _remove_tmp_after_playback(self) -> None:
        """Remove the session's MP3s once the player is done with them."""
        await asyncio.to_thread(self.player.wait_until_released, PLAYBACK_JOIN_TIMEOUT)
        _remove_tmp_dir(self.tmp_dir)

    async def stop(self) -> None:
        """Tear down now: cancel pending synths, kill the player, remove the tmp dir.

        The player is stopped in a worker thread so a slow-to-die process
        never blocks the event loop (and every other session with it).
        """
        self._closed = True
        self._cancel_idle_flush()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        try:
            await asyncio.to_thread(self.player.stop)
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


def _reap_idle_sessions(sessions: Dict[str, _LiveSession],
                        now: Optional[float] = None) -> List[_LiveSession]:
    """Remove and return sessions idle longer than ``SESSION_IDLE_TIMEOUT_S``.

    Pure bookkeeping: the caller closes the returned sessions.
    """
    now = time.monotonic() if now is None else now
    stale = [sid for sid, sess in sessions.items()
             if now - sess.last_activity > SESSION_IDLE_TIMEOUT_S]
    return [sessions.pop(sid) for sid in stale]


def build_server(sessions: Optional[Dict[str, _LiveSession]] = None,
                 default_prosody: Optional[ProsodyOpts] = None):
    """Construct an MCPServer with the TTS_ka tools registered.

    *sessions* is the session dict — exposed so tests can inspect state.
    *default_prosody* overrides the config-derived default (useful for tests).
    """
    from mcp.server.mcpserver import MCPServer  # local import: optional extra
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer(
        "tts-ka",
        instructions=(
            "Text-to-speech for AI agents. Use `speak` for one-shot lines, "
            "or `stream_open` + `stream_append` to read text as you generate it. "
            "Call `stream_close` when done, or `stop` to abort all audio."
        ),
    )
    sessions = sessions if sessions is not None else {}
    # One-shot ``speak`` clips still playing through a StreamingAudioPlayer.
    clips: Dict[str, StreamingAudioPlayer] = {}
    default_prosody = default_prosody if default_prosody is not None else _load_default_prosody()

    def _session(session_id: str) -> _LiveSession:
        sess = sessions.get(session_id)
        if sess is None:
            raise ToolError(f"unknown session_id {session_id!r}")
        return sess

    def _check_lang_voice(lang: str, voice: Optional[str]) -> None:
        invalid = _voices.validate_lang_voice(lang, voice)
        if invalid:
            raise ToolError(invalid)

    async def _close_reaped() -> None:
        # Lazy: runs whenever a tool touches the session table, so a forgotten
        # session frees its slot without a background task.
        for sess in _reap_idle_sessions(sessions):
            await sess.close()

    async def _stop_all() -> int:
        await asyncio.to_thread(stop_all_streaming_players)
        n = len(sessions)
        for sess in list(sessions.values()):
            await sess.stop()
        sessions.clear()
        return n

    def _players(session_id: Optional[str]) -> List[StreamingAudioPlayer]:
        if session_id is not None:
            return [_session(session_id).player]
        return [sess.player for sess in sessions.values()] + list(clips.values())

    def _control(session_id: Optional[str], action: Callable[[StreamingAudioPlayer], bool],
                 verb: str) -> str:
        players = _players(session_id)
        if not players:
            return "nothing is playing"
        done = sum(1 for p in players if action(p))
        if not done:
            raise ToolError(f"cannot {verb}: playback control needs mpv driven over IPC "
                            "(Linux/macOS); this player only supports stop")
        return f"{verb}d {done} stream(s)" if verb.endswith("e") else f"{verb}ped {done} stream(s)"

    async def _play_clip(path: str, tmp_dir: str, blocking: bool) -> Optional[float]:
        """Play *path* through a StreamingAudioPlayer; return seconds waited when *blocking*.

        Returns None (without playing) when no streaming-capable player is
        installed, so the caller can fall back to ``play_audio``. A blocking
        call raises ``ToolError`` when the player reported that it could not
        play the clip, rather than claiming it was played.
        """
        if PlayerDetector.find() is None:
            return None
        player = StreamingAudioPlayer(show_gui=False)
        clip_id = uuid.uuid4().hex[:12]
        clips[clip_id] = player
        player.start()
        player.add_chunk(path, chunk_index=0)
        player.finish_generation()

        async def release() -> None:
            await asyncio.to_thread(player.wait_until_released, PLAYBACK_JOIN_TIMEOUT)
            clips.pop(clip_id, None)
            _remove_tmp_dir(tmp_dir)

        if not blocking:
            _spawn_cleanup(release())
            return 0.0
        started = time.monotonic()
        await release()
        if player.playback_error:
            raise ToolError(f"playback failed: {player.playback_error}")
        return time.monotonic() - started

    @server.tool()
    async def speak(text: str, lang: str = "en",
                    voice: Optional[str] = None,
                    rate: Optional[str] = None,
                    pitch: Optional[str] = None,
                    volume: Optional[str] = None,
                    blocking: bool = False,
                    interrupt: bool = False) -> str:
        """Speak *text* immediately.

        With ``blocking=False`` (default) the call returns as soon as
        playback is launched. With ``blocking=True`` it returns when playback
        has finished, so an agent can sequence speech without overlapping.
        With ``interrupt=True`` everything currently playing (other clips and
        streaming sessions) is stopped first. The return string echoes the
        resolved settings.

        rate / pitch / volume are signed percentages or Hz (rate '+30%',
        pitch '+5Hz' or '-10%', volume '-25%'). Unspecified values fall
        back to the server-wide defaults from ``~/.tts_config.json``.
        """
        _check_lang_voice(lang, voice)
        cleaned = replace_not_readable(text)
        if not cleaned.strip():
            return "skipped: empty"
        if interrupt:
            await _stop_all()
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
            raise ToolError(str(exc)) from exc

        waited = await _play_clip(path, tmp_dir, blocking)
        if waited is not None:
            if blocking:
                return f"played in {waited:.1f}s [{echo}]"
            return f"queued {path} [{echo}]"

        # No streaming player: hand the file to the desktop's default opener.
        if not play_audio(path):
            # Kept so the agent/user can open it; swept when the server exits.
            raise ToolError(f"no audio player available; saved {path} [{echo}]")
        if blocking:
            # play_audio keeps no handle, so the measured duration is the only
            # end-of-playback signal.
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
        the server-wide defaults from ``~/.tts_config.json``. Sessions idle
        for 15 minutes are closed the next time a session is opened or listed.
        """
        _check_lang_voice(lang, voice)
        await _close_reaped()
        if len(sessions) >= MAX_SESSIONS:
            raise ToolError(f"max {MAX_SESSIONS} concurrent sessions; "
                            "stream_close or stop one first")
        prosody = _resolve_prosody(rate, pitch, volume, default_prosody)
        sid = uuid.uuid4().hex[:12]
        sessions[sid] = _LiveSession(lang=lang, voice=voice, prosody=prosody)
        return sid

    @server.tool()
    async def stream_append(session_id: str, text: str) -> str:
        """Push *text* to a streaming session. Speaks each complete sentence.

        A sentence that ends the appended text is spoken right away; an
        unfinished tail is spoken after a short pause if nothing follows.
        """
        sess = _session(session_id)
        try:
            n = await sess.feed(text)
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc
        return f"queued {n} sentence(s)"

    @server.tool()
    async def stream_close(session_id: str) -> str:
        """Drain the remaining buffer, await pending synths, end the session."""
        sess = sessions.pop(session_id, None)
        if sess is None:
            raise ToolError(f"unknown session_id {session_id!r}")
        total = await sess.close()
        return f"closed: spoke {total} chunk(s)"

    @server.tool()
    async def session_status(session_id: str) -> Dict[str, object]:
        """Return progress info for a streaming session.

        Fields: lang, voice, rate, pitch, volume, closed, total_sentences,
        synths_pending, synths_failed, last_error, buffer_chars,
        buffer_preview, controllable. Useful for an agent to decide whether
        to keep streaming or wait for synths to drain, and to detect failed
        synths (synths_failed > 0 with the most recent message in last_error).
        """
        snap = _session(session_id).status()
        snap["session_id"] = session_id
        return snap

    @server.tool()
    async def list_sessions() -> List[Dict[str, object]]:
        """Return a brief snapshot of every active session."""
        await _close_reaped()
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
    async def pause(session_id: Optional[str] = None) -> str:
        """Pause one session's playback, or everything playing when no id is given."""
        return _control(session_id, lambda p: p.pause(), "pause")

    @server.tool()
    async def resume(session_id: Optional[str] = None) -> str:
        """Resume paused playback for one session, or everything when no id is given."""
        return _control(session_id, lambda p: p.resume(), "resume")

    @server.tool()
    async def skip(session_id: Optional[str] = None) -> str:
        """Skip the sentence currently playing (one session, or every stream)."""
        return _control(session_id, lambda p: p.skip_current(), "skip")

    @server.tool()
    async def stop(session_id: Optional[str] = None) -> str:
        """Abort playback. With *session_id*, tear down just that session;
        otherwise stop every clip and session."""
        if session_id is not None:
            sess = sessions.pop(session_id, None)
            if sess is None:
                raise ToolError(f"unknown session_id {session_id!r}")
            await sess.stop()
            return f"stopped session {session_id}"
        n = await _stop_all()
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
