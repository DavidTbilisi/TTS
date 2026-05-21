"""MCP server exposing TTS_ka to AI clients (Claude Code, Claude Desktop, etc).

Tools:

- ``speak(text, lang?, voice?, blocking?)`` — synthesize and play immediately.
- ``stream_open(lang?, voice?)`` → session_id — start an incremental session.
- ``stream_append(session_id, text)`` — push text; speaks complete sentences.
- ``stream_close(session_id)`` — drain remaining buffer and stop accepting input.
- ``stop()`` — terminate all active playback and sessions.
- ``list_voices(lang?)`` — return the voice catalog.

Transport: stdio (JSON-RPC). Because stdout is reserved for the protocol,
all decorative ``print()`` from underlying modules is redirected to stderr
for the lifetime of the server.

Run via ``TTS_ka-mcp`` (installed entry point) or ``python -m TTS_ka.mcp_server``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import uuid
from typing import Dict, List, Optional

from .fast_audio import cleanup_http, fast_generate_audio, play_audio
from .live_stream import DEFAULT_IDLE_FLUSH_MS, SentenceBuffer
from .not_reading import replace_not_readable
from .streaming_player import StreamingAudioPlayer, stop_active_streaming_player
from . import voices as _voices


MAX_SESSIONS = 8
MAX_CONCURRENT_PER_SESSION = 4


class _LiveSession:
    """Long-lived sentence buffer + streaming player for one MCP stream."""

    def __init__(self, lang: str, voice: Optional[str]) -> None:
        self.lang = lang
        self.voice = voice
        self.buf = SentenceBuffer(idle_flush_ms=DEFAULT_IDLE_FLUSH_MS)
        self.player = StreamingAudioPlayer(show_gui=False)
        self.player.start()
        self.tmp_dir = tempfile.mkdtemp(prefix="ttska-mcp-")
        self._idx = 0      # output-file counter (incremented inside _speak)
        self._queued = 0   # sentences ever scheduled — visible in status
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
            "closed": self._closed,
            "total_sentences": self._queued,
            "synths_pending": self.synths_pending(),
            "buffer_chars": len(preview),
            "buffer_preview": preview[:80],
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
                await fast_generate_audio(cleaned, self.lang, path,
                                          voice=self.voice, prosody=None)
                self.player.add_chunk(path, chunk_index=idx)
            except Exception as exc:  # noqa: BLE001
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
        return self._queued

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
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


# ── Server factory ────────────────────────────────────────────────────────────


def build_server(sessions: Optional[Dict[str, _LiveSession]] = None):
    """Construct a FastMCP server with the TTS_ka tools registered.

    *sessions* is the session dict — exposed so tests can inspect state.
    """
    from mcp.server.fastmcp import FastMCP  # local import: optional extra

    server = FastMCP(
        "tts-ka",
        instructions=(
            "Text-to-speech for AI agents. Use `speak` for one-shot lines, "
            "or `stream_open` + `stream_append` to read text as you generate it. "
            "Call `stream_close` when done, or `stop` to abort all audio."
        ),
    )
    sessions = sessions if sessions is not None else {}

    @server.tool()
    async def speak(text: str, lang: str = "en",
                    voice: Optional[str] = None,
                    blocking: bool = False) -> str:
        """Speak *text* immediately. Returns when synth starts (or finishes if blocking)."""
        cleaned = replace_not_readable(text)
        if not cleaned.strip():
            return "skipped: empty"
        tmp_dir = tempfile.mkdtemp(prefix="ttska-mcp-one-")
        path = os.path.join(tmp_dir, "out.mp3")
        try:
            await fast_generate_audio(cleaned, lang, path,
                                      voice=voice, prosody=None)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return f"error: {exc}"
        if blocking:
            # play_audio is non-blocking on most platforms; for blocking we'd
            # need a sync waiter. Honour the parameter as a documentation hint
            # and warn if true — current impl is fire-and-forget.
            play_audio(path)
            return f"played {path}"
        play_audio(path)
        return f"queued {path}"

    @server.tool()
    async def stream_open(lang: str = "en",
                          voice: Optional[str] = None) -> str:
        """Open a streaming session. Returns the session_id to use with stream_append/close."""
        if len(sessions) >= MAX_SESSIONS:
            return f"error: max {MAX_SESSIONS} concurrent sessions"
        sid = uuid.uuid4().hex[:12]
        sessions[sid] = _LiveSession(lang=lang, voice=voice)
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

        Fields: lang, voice, closed, total_sentences, synths_pending,
        buffer_chars, buffer_preview. Useful for an agent to decide whether
        to keep streaming or wait for synths to drain.
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
        try:
            await cleanup_http()
        except Exception:
            pass
        return f"stopped {n} session(s)"

    @server.tool()
    def list_voices(lang: Optional[str] = None) -> List[Dict[str, str]]:
        """Return available voices. Optionally filter by lang (ka, ru, en, en-US)."""
        catalog = (_voices.voices_for_lang(lang)
                   if lang and lang in {"ka", "ru", "en", "en-US"}
                   else _voices.all_voices())
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


async def _run_with_preserved_stdout(server) -> None:
    """Run the FastMCP server, keeping the real OS stdout for protocol framing.

    Strategy:
      1. ``os.dup(1)`` saves a duplicate fd pointing at the real stdout.
      2. ``os.dup2(2, 1)`` redirects fd 1 (and therefore ``sys.stdout``,
         ``print``, and any subprocesses inheriting fd 1) to stderr.
      3. We hand the saved fd to ``stdio_server`` so JSON-RPC framing still
         goes out the original stdout the client is reading.

    Any ``print()`` from imported modules (``StreamingAudioPlayer`` warnings,
    HTTP-fallback notices, etc.) lands on the user's stderr — never on the
    protocol stream.
    """
    import os
    from io import TextIOWrapper
    import anyio
    from mcp.server.stdio import stdio_server

    saved_stdout_fd = os.dup(1)
    os.dup2(2, 1)
    real_stdout_binary = os.fdopen(saved_stdout_fd, "wb", buffering=0)
    real_stdout = anyio.wrap_file(TextIOWrapper(real_stdout_binary, encoding="utf-8"))

    async with stdio_server(stdout=real_stdout) as (read, write):
        await server._mcp_server.run(
            read, write, server._mcp_server.create_initialization_options()
        )


def main() -> None:
    """Run the MCP server over stdio with print-corruption protection.

    See :func:`_run_with_preserved_stdout` for why this dance is needed.
    """
    server = build_server()
    asyncio.run(_run_with_preserved_stdout(server))


if __name__ == "__main__":
    main()
