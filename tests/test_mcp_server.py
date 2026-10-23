"""Tests for the MCP server tool surface.

We don't exercise the JSON-RPC transport — that's the mcp library's job.
Instead we call the tool callables directly via MCPServer's `call_tool`
to verify the wiring, session lifecycle, and stdout safety.

Sessions get a ``_StubPlayer`` instead of ``StreamingAudioPlayer`` (autouse
fixture below), so no test launches a real mpv/VLC on the 1-byte placeholder
MP3s; the player itself is covered by ``test_streaming.py``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
import sys
from unittest.mock import AsyncMock, patch

import pytest


pytest.importorskip("mcp", reason="mcp extra not installed")

from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from TTS_ka import mcp_server as _mcp  # noqa: E402
from TTS_ka.mcp_server import _LiveSession, build_server  # noqa: E402


class _StubPlayer:
    """StreamingAudioPlayer stand-in: records calls, no thread, no subprocess.

    ``process`` can be set to a real Popen to model VLC / mplayer, which
    launch a player and return while it is still playing.
    """

    instances: list = []
    controllable = True

    def __init__(self, show_gui=False):
        self.chunks = []           # (chunk_index, path) in add_chunk order
        self.skipped = []          # chunk indices reported as never coming
        self.controls = []         # pause / resume / skip_current calls
        self.process = None
        self.started = False
        self.finished = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def add_chunk(self, path, chunk_index=None):
        self.chunks.append((chunk_index, path))

    def skip_index(self, chunk_index):
        self.skipped.append(chunk_index)

    def finish_generation(self):
        self.finished = True

    def wait_for_completion(self):
        pass

    def wait_until_released(self, timeout=None):
        if self.process is not None:
            self.process.wait(timeout)
        return True

    def stop(self):
        self.stopped = True

    def _control(self, name):
        self.controls.append(name)
        return self.controllable

    def pause(self):
        return self._control("pause")

    def resume(self):
        return self._control("resume")

    def skip_current(self):
        return self._control("skip_current")


@pytest.fixture(autouse=True)
def _stub_player():
    """Stub the player, and report no streaming player so ``speak`` uses ``play_audio``.

    Tests of the streaming-player ``speak`` path patch ``PlayerDetector.find`` back on.
    """
    _StubPlayer.instances = []
    _StubPlayer.controllable = True
    with patch("TTS_ka.mcp_server.StreamingAudioPlayer", _StubPlayer), \
         patch("TTS_ka.mcp_server.PlayerDetector.find", return_value=None), \
         patch("TTS_ka.mcp_server.stop_all_streaming_players"):
        yield


@pytest.fixture(autouse=True)
def _sweep_tmp_dirs():
    """Remove temp dirs left behind when a test's loop cancels cleanup tasks."""
    yield
    _mcp._remove_all_tmp_dirs()


# ── _LiveSession ──────────────────────────────────────────────────────────────


class TestLiveSession:
    @pytest.mark.asyncio
    async def test_feed_returns_sentence_count(self):
        sess = _LiveSession(lang="en", voice=None)
        with patch("TTS_ka.mcp_server.fast_generate_audio",
                   new=AsyncMock()) as gen:
            # Touch the file so the player won't reject it
            async def fake(text, lang, output, *, voice=None, prosody=None):
                with open(output, "wb") as f:
                    f.write(b"x")
            gen.side_effect = fake
            n = await sess.feed("First. Second! ")
            await sess.close()
        assert n == 2

    @pytest.mark.asyncio
    async def test_close_drains_partial(self):
        sess = _LiveSession(lang="en", voice=None)
        calls = []
        async def fake(text, lang, output, *, voice=None, prosody=None):
            calls.append(text)
            with open(output, "wb") as f:
                f.write(b"x")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            await sess.feed("partial")
            await sess.close()
        # The partial was drained on close.
        assert any("partial" in c for c in calls)

    @pytest.mark.asyncio
    async def test_double_close_idempotent(self):
        sess = _LiveSession(lang="en", voice=None)
        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            await sess.close()
            await sess.close()  # must not raise

    @pytest.mark.asyncio
    async def test_feed_after_close_raises(self):
        sess = _LiveSession(lang="en", voice=None)
        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            await sess.close()
        with pytest.raises(RuntimeError, match="closed"):
            await sess.feed("late text")


# ── Tools via build_server() ──────────────────────────────────────────────────


async def _call(server, name, **kwargs):
    """Invoke a registered MCP tool and return the unwrapped Python value.

    MCPServer wraps scalar and list returns in ``{"result": value}``; we peel
    that off. Dict returns pass through as-is.
    """
    structured = (await server.call_tool(name, kwargs)).structured_content
    if isinstance(structured, dict) and list(structured.keys()) == ["result"]:
        return structured["result"]
    return structured


class TestStreamFlow:
    @pytest.mark.asyncio
    async def test_open_append_close_lifecycle(self):
        sessions = {}
        server = build_server(sessions=sessions)

        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            sid = await _call(server, "stream_open", lang="en")
            assert isinstance(sid, str)
            assert sid in sessions
            player = sessions[sid].player
            assert player.started

            r = await _call(server, "stream_append",
                            session_id=sid, text="One. Two! ")
            assert "queued 2" in r

            r = await _call(server, "stream_close", session_id=sid)
            assert "closed" in r
            assert sid not in sessions
        # Both sentences reached the player, indexed in document order,
        # and close() told it no more input is coming.
        assert sorted(i for i, _ in player.chunks) == [0, 1]
        assert all(p.endswith(f".part_{i:04d}.mp3") for i, p in player.chunks)
        assert player.finished

    @pytest.mark.asyncio
    async def test_append_unknown_session(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with pytest.raises(ToolError, match="unknown session_id"):
            await _call(server, "stream_append", session_id="bogus", text="hi")

    @pytest.mark.asyncio
    async def test_close_unknown_session(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with pytest.raises(ToolError, match="unknown session_id"):
            await _call(server, "stream_close", session_id="bogus")

    @pytest.mark.asyncio
    async def test_max_concurrent_sessions(self):
        from TTS_ka import mcp_server
        sessions = {}
        # Pre-fill to the cap with dummy entries.
        with patch.object(mcp_server, "MAX_SESSIONS", 2):
            server = build_server(sessions=sessions)
            async def fake(text, lang, output, *, voice=None, prosody=None):
                with open(output, "wb") as f:
                    f.write(b"x")
            with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
                a = await _call(server, "stream_open")
                b = await _call(server, "stream_open")
                with pytest.raises(ToolError, match="max 2 concurrent sessions"):
                    await _call(server, "stream_open")
                # Cleanup
                await _call(server, "stream_close", session_id=a)
                await _call(server, "stream_close", session_id=b)


class TestSpeakTool:
    @pytest.mark.asyncio
    async def test_speak_calls_generator_and_player(self, tmp_path):
        server = build_server()
        synth_calls = []

        async def fake(text, lang, output, *, voice=None, prosody=None):
            synth_calls.append((text, lang, voice))
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio") as mplay:
            r = await _call(server, "speak", text="Hello world", lang="en")
        assert "queued" in r or "played" in r
        assert synth_calls
        assert mplay.called

    @pytest.mark.asyncio
    async def test_speak_empty_text_skipped(self):
        server = build_server()
        with patch("TTS_ka.mcp_server.fast_generate_audio",
                   new=AsyncMock()) as gen, \
             patch("TTS_ka.mcp_server.play_audio") as mplay:
            r = await _call(server, "speak", text="   ", lang="en")
        assert "skipped" in r
        assert not gen.called
        assert not mplay.called

    @pytest.mark.asyncio
    async def test_speak_generator_error_returns_message(self):
        server = build_server()
        async def boom(*a, **kw):
            raise RuntimeError("network down")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=boom), \
             patch("TTS_ka.mcp_server.play_audio"):
            with pytest.raises(ToolError, match="network down"):
                await _call(server, "speak", text="hi", lang="en")

    @pytest.mark.asyncio
    async def test_speak_false_return_is_an_error_not_played(self):
        """fast_generate_audio returning False (e.g. HTTP 403) must not report success."""
        server = build_server()
        with patch("TTS_ka.mcp_server.fast_generate_audio", new=AsyncMock(return_value=False)), \
             patch("TTS_ka.mcp_server.play_audio") as mplay:
            with pytest.raises(ToolError, match="synthesis failed"):
                await _call(server, "speak", text="hi", lang="en")
        mplay.assert_not_called()

    @pytest.mark.asyncio
    async def test_speak_blocking_waits_for_duration(self):
        """blocking=True sleeps for the measured duration and echoes settings."""
        import asyncio as _asyncio
        server = build_server()
        slept = {}

        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")

        async def fake_sleep(secs):
            slept["secs"] = secs

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio", return_value=True), \
             patch("TTS_ka.mcp_server._audio_duration_seconds", return_value=2.0), \
             patch.object(_asyncio, "sleep", side_effect=fake_sleep):
            r = await _call(server, "speak", text="Hello", lang="en", blocking=True)
        assert "played" in r
        assert "lang=en" in r
        assert slept["secs"] >= 2.0

    @pytest.mark.asyncio
    async def test_speak_no_player_reports_error(self):
        """When no player launches, speak says so instead of pretending success."""
        server = build_server()

        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio", return_value=False):
            with pytest.raises(ToolError, match="no audio player"):
                await _call(server, "speak", text="Hi", lang="en")

    @pytest.mark.asyncio
    async def test_speak_echoes_settings_when_queued(self):
        server = build_server()

        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio", return_value=True):
            r = await _call(server, "speak", text="Hi", lang="en",
                            voice="en-US-JennyNeural")
        assert "queued" in r
        assert "voice=en-US-JennyNeural" in r

    @pytest.mark.asyncio
    async def test_speak_propagates_voice(self):
        server = build_server()
        seen = {}

        async def fake(text, lang, output, *, voice=None, prosody=None):
            seen["voice"] = voice
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio"):
            await _call(server, "speak", text="Hi",
                        lang="en", voice="en-US-JennyNeural")
        assert seen["voice"] == "en-US-JennyNeural"


class TestStopTool:
    @pytest.mark.asyncio
    async def test_stop_clears_sessions(self):
        sessions = {}
        server = build_server(sessions=sessions)

        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            await _call(server, "stream_open")
            await _call(server, "stream_open")
            assert len(sessions) == 2
            players = [sess.player for sess in sessions.values()]
            r = await _call(server, "stop")
        assert "stopped 2" in r
        assert sessions == {}
        assert all(p.stopped for p in players)

    @pytest.mark.asyncio
    async def test_stop_when_empty_returns_zero(self):
        server = build_server(sessions={})
        r = await _call(server, "stop")
        assert "stopped 0" in r


class TestSessionStatus:
    @pytest.mark.asyncio
    async def test_status_unknown_session(self):
        server = build_server(sessions={})
        with pytest.raises(ToolError, match="unknown session_id"):
            await _call(server, "session_status", session_id="bogus")

    @pytest.mark.asyncio
    async def test_status_reports_progress(self):
        sessions = {}
        server = build_server(sessions=sessions)
        # Block synthesis so we can observe synths_pending.
        gate = __import__("asyncio").Event()

        async def slow(text, lang, output, *, voice=None, prosody=None):
            await gate.wait()
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=slow):
            sid = await _call(server, "stream_open", lang="en")
            await _call(server, "stream_append",
                        session_id=sid, text="One. Two. ")
            snap = await _call(server, "session_status", session_id=sid)
            assert snap["session_id"] == sid
            assert snap["lang"] == "en"
            assert snap["closed"] is False
            assert snap["total_sentences"] == 2
            assert snap["synths_pending"] == 2
            # Release the gate and wait for close to drain.
            gate.set()
            await _call(server, "stream_close", session_id=sid)

    @pytest.mark.asyncio
    async def test_status_failure_fields_present(self):
        """synths_failed / last_error appear in the status snapshot."""
        sessions = {}
        server = build_server(sessions=sessions)

        async def boom(text, lang, output, *, voice=None, prosody=None):
            raise RuntimeError("network down")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=boom):
            sid = await _call(server, "stream_open", lang="en")
            await _call(server, "stream_append", session_id=sid, text="One. ")
            # Let the synth task run and fail.
            import asyncio as _a
            await _a.sleep(0)
            await _a.gather(*sessions[sid]._tasks, return_exceptions=True)
            snap = await _call(server, "session_status", session_id=sid)
            assert snap["synths_failed"] == 1
            assert "network down" in (snap["last_error"] or "")
            await _call(server, "stream_close", session_id=sid)

    @pytest.mark.asyncio
    async def test_status_counts_false_return_as_failure(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", new=AsyncMock(return_value=False)):
            sid = await _call(server, "stream_open", lang="en")
            await _call(server, "stream_append", session_id=sid, text="One. ")
            import asyncio as _a
            await _a.sleep(0)
            await _a.gather(*sessions[sid]._tasks, return_exceptions=True)
            snap = await _call(server, "session_status", session_id=sid)
            assert snap["synths_failed"] == 1
            assert "GenerationFailed" in (snap["last_error"] or "")
            await _call(server, "stream_close", session_id=sid)

    @pytest.mark.asyncio
    async def test_status_shows_buffer_preview(self):
        sessions = {}
        server = build_server(sessions=sessions)
        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            sid = await _call(server, "stream_open", lang="en")
            # No sentence terminator → stays in the buffer.
            await _call(server, "stream_append",
                        session_id=sid, text="A partial sentence in progress")
            snap = await _call(server, "session_status", session_id=sid)
            assert snap["total_sentences"] == 0
            assert "partial" in snap["buffer_preview"]
            assert snap["buffer_chars"] > 0
            await _call(server, "stream_close", session_id=sid)


class TestListSessions:
    @pytest.mark.asyncio
    async def test_empty(self):
        server = build_server(sessions={})
        r = await _call(server, "list_sessions")
        assert r == []

    @pytest.mark.asyncio
    async def test_two_sessions(self):
        sessions = {}
        server = build_server(sessions=sessions)
        async def fake(text, lang, output, *, voice=None, prosody=None):
            with open(output, "wb") as f:
                f.write(b"x")
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake):
            a = await _call(server, "stream_open", lang="en")
            b = await _call(server, "stream_open", lang="ka",
                            voice="ka-GE-EkaNeural")
            listing = await _call(server, "list_sessions")
            assert len(listing) == 2
            by_id = {x["session_id"]: x for x in listing}
            assert by_id[a]["lang"] == "en"
            assert by_id[b]["lang"] == "ka"
            assert by_id[b]["voice"] == "ka-GE-EkaNeural"
            await _call(server, "stream_close", session_id=a)
            await _call(server, "stream_close", session_id=b)


class TestProsody:
    """Config-driven prosody defaults + per-call overrides."""

    @pytest.mark.asyncio
    async def test_default_prosody_applied_to_session(self):
        """stream_open with no rate uses the server's default_prosody."""
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        default = ProsodyOpts(rate="+30%", pitch="+0Hz", volume="+0%")
        server = build_server(sessions=sessions, default_prosody=default)
        sid = await _call(server, "stream_open", lang="en")
        sess = sessions[sid]
        assert sess.prosody is not None
        assert sess.prosody.rate == "+30%"

    @pytest.mark.asyncio
    async def test_per_call_rate_overrides_default(self):
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        default = ProsodyOpts(rate="+30%")
        server = build_server(sessions=sessions, default_prosody=default)
        sid = await _call(server, "stream_open", lang="en", rate="-20%")
        assert sessions[sid].prosody.rate == "-20%"

    @pytest.mark.asyncio
    async def test_per_call_pitch_keeps_default_rate(self):
        """Partial override: pitch from agent, rate from config."""
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        default = ProsodyOpts(rate="+30%")
        server = build_server(sessions=sessions, default_prosody=default)
        sid = await _call(server, "stream_open", lang="en", pitch="+5Hz")
        sess = sessions[sid]
        assert sess.prosody.rate == "+30%"
        assert sess.prosody.pitch == "+5Hz"

    @pytest.mark.asyncio
    async def test_all_defaults_zero_means_no_prosody(self):
        """ProsodyOpts() with all zeros → session.prosody is None (no SSML wrap)."""
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        server = build_server(sessions=sessions, default_prosody=ProsodyOpts())
        sid = await _call(server, "stream_open", lang="en")
        assert sessions[sid].prosody is None

    @pytest.mark.asyncio
    async def test_speak_passes_prosody_to_generator(self):
        """The speak tool merges default+override and forwards to fast_generate_audio."""
        from TTS_ka.prosody import ProsodyOpts
        captured = {}

        async def fake(text, lang, output, *, voice=None, prosody=None):
            captured["prosody"] = prosody
            with open(output, "wb") as f:
                f.write(b"x")

        default = ProsodyOpts(rate="+30%")
        server = build_server(default_prosody=default)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=fake), \
             patch("TTS_ka.mcp_server.play_audio"):
            await _call(server, "speak", text="hi", lang="en")
        assert captured["prosody"] is not None
        assert captured["prosody"].rate == "+30%"

    @pytest.mark.asyncio
    async def test_session_status_includes_prosody(self):
        """session_status surfaces rate/pitch/volume so the agent can confirm."""
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        default = ProsodyOpts(rate="+30%", pitch="+5Hz")
        server = build_server(sessions=sessions, default_prosody=default)
        sid = await _call(server, "stream_open", lang="en")
        snap = await _call(server, "session_status", session_id=sid)
        assert snap["rate"] == "+30%"
        assert snap["pitch"] == "+5Hz"
        assert snap["volume"] == "+0%"

    @pytest.mark.asyncio
    async def test_bad_per_call_rate_falls_back_to_default(self):
        """A bogus rate from the agent doesn't crash the server."""
        from TTS_ka.prosody import ProsodyOpts
        sessions = {}
        default = ProsodyOpts(rate="+30%")
        server = build_server(sessions=sessions, default_prosody=default)
        sid = await _call(server, "stream_open", lang="en", rate="garbage")
        # Bad input → fall back to the full default ProsodyOpts.
        assert sessions[sid].prosody.rate == "+30%"


class TestLoadDefaultProsody:
    """`_load_default_prosody` is what production calls when build_server doesn't override."""

    def test_no_config_returns_default(self, monkeypatch, tmp_path):
        from TTS_ka import mcp_server
        from TTS_ka.prosody import ProsodyOpts
        monkeypatch.setenv("TTS_KA_CONFIG", str(tmp_path / "missing.json"))
        # Also point HOME so the fallback default_config_path() also misses.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        assert mcp_server._load_default_prosody() == ProsodyOpts()

    def test_config_rate_applied(self, monkeypatch, tmp_path):
        from TTS_ka import mcp_server
        import json
        cfg = tmp_path / "tts.json"
        cfg.write_text(json.dumps({"rate": "+30%"}), encoding="utf-8")
        monkeypatch.setenv("TTS_KA_CONFIG", str(cfg))
        defaults = mcp_server._load_default_prosody()
        assert defaults.rate == "+30%"
        assert defaults.pitch == "+0Hz"
        assert defaults.volume == "+0%"

    def test_invalid_config_rate_swallowed(self, monkeypatch, tmp_path):
        """Typo in the config doesn't kill the MCP server — falls back to defaults."""
        from TTS_ka import mcp_server
        from TTS_ka.prosody import ProsodyOpts
        import json
        cfg = tmp_path / "tts.json"
        cfg.write_text(json.dumps({"rate": "not a percentage"}), encoding="utf-8")
        monkeypatch.setenv("TTS_KA_CONFIG", str(cfg))
        assert mcp_server._load_default_prosody() == ProsodyOpts()


class TestListVoices:
    @pytest.mark.asyncio
    async def test_list_all(self):
        server = build_server()
        result = await _call(server, "list_voices")
        # MCPServer wraps list returns in a {"result": [...]} structured payload.
        items = result["result"] if isinstance(result, dict) and "result" in result else result
        assert isinstance(items, list)
        assert all("id" in v and "lang" in v for v in items)

    @pytest.mark.asyncio
    async def test_list_filtered_by_lang(self):
        server = build_server()
        result = await _call(server, "list_voices", lang="ka")
        items = result["result"] if isinstance(result, dict) and "result" in result else result
        assert items
        assert all(v["lang"] == "ka" for v in items)

    @pytest.mark.asyncio
    async def test_list_unknown_lang_returns_all(self):
        server = build_server()
        result = await _call(server, "list_voices", lang="zz")
        items = result["result"] if isinstance(result, dict) and "result" in result else result
        # Unknown lang falls through to all_voices, not an empty list.
        assert items


# ── Temp-dir cleanup ──────────────────────────────────────────────────────────


async def _write_one_byte(text, lang, output, *, voice=None, prosody=None):
    with open(output, "wb") as f:
        f.write(b"x")


async def _drain_cleanup_tasks():
    await asyncio.gather(*list(_mcp._cleanup_tasks))


class TestTmpDirCleanup:
    @pytest.mark.asyncio
    async def test_stream_close_removes_dir_after_playback(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
            sid = await _call(server, "stream_open", lang="en")
            tmp_dir = sessions[sid].tmp_dir
            await _call(server, "stream_append", session_id=sid, text="One. Two. ")
            await _call(server, "stream_close", session_id=sid)
            await _drain_cleanup_tasks()
        assert not os.path.exists(tmp_dir)
        assert tmp_dir not in _mcp._tmp_dirs

    @pytest.mark.asyncio
    async def test_stream_close_waits_for_launched_player_process(self):
        """VLC / mplayer return right after launch: wait for the process too."""
        sessions = {}
        server = build_server(sessions=sessions)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
        try:
            with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
                sid = await _call(server, "stream_open", lang="en")
                sess = sessions[sid]
                sess.player.process = proc
                await _call(server, "stream_append", session_id=sid, text="One. ")
                await _call(server, "stream_close", session_id=sid)
                assert os.path.isdir(sess.tmp_dir)  # player still running
                await _drain_cleanup_tasks()
            assert proc.returncode is not None
            assert not os.path.exists(sess.tmp_dir)
        finally:
            proc.kill()
            proc.wait()

    @pytest.mark.asyncio
    async def test_queued_speak_removed_after_clip_duration(self):
        server = build_server()
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch("TTS_ka.mcp_server.play_audio", return_value=True), \
             patch("TTS_ka.mcp_server._audio_duration_seconds", return_value=0.05), \
             patch.object(_mcp, "PLAYBACK_GRACE_SECONDS", 0.0):
            r = await _call(server, "speak", text="Hello there", lang="en")
            path = r.split()[1]
            assert r.startswith("queued") and os.path.exists(path)
            await _drain_cleanup_tasks()
        assert not os.path.exists(os.path.dirname(path))

    @pytest.mark.asyncio
    async def test_blocking_speak_unknown_duration_defers_removal(self):
        """No duration → don't delete under a player that may still be reading."""
        server = build_server()
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch("TTS_ka.mcp_server.play_audio", return_value=True), \
             patch("TTS_ka.mcp_server._audio_duration_seconds", return_value=None), \
             patch.object(_mcp, "UNKNOWN_DURATION_KEEP_SECONDS", 0.01):
            r = await _call(server, "speak", text="Hello there", lang="en", blocking=True)
            assert r.startswith("played [")
            (tmp_dir,) = [d for d in _mcp._tmp_dirs if "ttska-mcp-one-" in d]
            assert os.path.isdir(tmp_dir)
            await _drain_cleanup_tasks()
        assert not os.path.exists(tmp_dir)

    @pytest.mark.asyncio
    async def test_sweep_removes_unclosed_session_and_no_player_clip(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch("TTS_ka.mcp_server.play_audio", return_value=False):
            sid = await _call(server, "stream_open", lang="en")
            with pytest.raises(ToolError, match="no audio player") as exc:
                await _call(server, "speak", text="Hello there", lang="en")
        r = str(exc.value)
        dirs = [sessions[sid].tmp_dir, os.path.dirname(r.split("saved ")[1].split()[0])]
        assert all(os.path.isdir(d) for d in dirs)
        _mcp._remove_all_tmp_dirs()
        assert not any(os.path.exists(d) for d in dirs)
        assert not _mcp._tmp_dirs

    def test_main_sweeps_tmp_dirs_on_exit(self):
        made = []

        class _Server:
            def run(self, transport):
                made.append(_mcp._make_tmp_dir("ttska-mcp-"))
                raise KeyboardInterrupt

        with patch("TTS_ka.mcp_server.build_server", return_value=_Server()), \
             patch.object(sys.stdout, "reconfigure", create=True):
            with pytest.raises(KeyboardInterrupt):
                _mcp.main()
        assert made and not os.path.exists(made[0])


# ── Streaming robustness, controls, validation ───────────────────────────────


async def _open(server, sessions, **kwargs):
    sid = await _call(server, "stream_open", **kwargs)
    return sid, sessions[sid]


class TestStreamRobustness:
    async def test_failed_sentence_is_skipped_so_later_ones_play(self):
        sessions = {}
        server = build_server(sessions=sessions)

        async def gen(text, lang, output, *, voice=None, prosody=None):
            if "broken" in text:
                return False
            with open(output, "wb") as f:
                f.write(b"x")

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=gen):
            sid, sess = await _open(server, sessions)
            await _call(server, "stream_append", session_id=sid,
                        text="First fine. This is broken. Third fine. ")
            r = await _call(server, "stream_close", session_id=sid)
        assert sess.player.skipped == [1]
        assert sorted(i for i, _ in sess.player.chunks) == [0, 2]
        assert r == "closed: spoke 2 chunk(s)"

    async def test_task_cancelled_before_it_starts_still_skips_its_index(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
            sid, sess = await _open(server, sessions)
            # feed() never yields, so neither task has taken a step yet.
            await sess.feed("First fine. Second fine. ")
            sess._tasks[0].cancel()
            await asyncio.gather(*sess._tasks, return_exceptions=True)
            await _call(server, "stream_close", session_id=sid)
        assert sess.player.skipped == [0]
        assert [i for i, _ in sess.player.chunks] == [1]

    async def test_sentence_ending_an_append_is_spoken_without_close(self):
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
            sid, sess = await _open(server, sessions)
            r = await _call(server, "stream_append", session_id=sid, text="Hello there.")
            assert r == "queued 1 sentence(s)"
            await asyncio.gather(*sess._tasks)
            assert len(sess.player.chunks) == 1
            await _call(server, "stream_close", session_id=sid)

    async def test_trailing_fragment_flushes_after_idle(self, monkeypatch):
        monkeypatch.setattr(_mcp, "MCP_IDLE_FLUSH_MS", 20)
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
            sid, sess = await _open(server, sessions)
            r = await _call(server, "stream_append", session_id=sid, text="and then we")
            assert r == "queued 0 sentence(s)"
            await asyncio.sleep(0.1)
            await asyncio.gather(*sess._tasks)
            assert len(sess.player.chunks) == 1     # spoken with no further append
            assert sess.buf.buffer == ""
            await _call(server, "stream_close", session_id=sid)

    async def test_new_append_postpones_idle_flush(self, monkeypatch):
        monkeypatch.setattr(_mcp, "MCP_IDLE_FLUSH_MS", 60)
        sessions = {}
        server = build_server(sessions=sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte):
            sid, sess = await _open(server, sessions)
            await _call(server, "stream_append", session_id=sid, text="and then")
            await asyncio.sleep(0.03)
            await _call(server, "stream_append", session_id=sid, text=" we left.")
            await asyncio.sleep(0.1)
            await asyncio.gather(*sess._tasks)
            assert sess._queued == 1                # one sentence, not a fragment + rest
            await _call(server, "stream_close", session_id=sid)


class TestValidation:
    @pytest.mark.parametrize("tool", ["stream_open", "speak"])
    async def test_bad_lang_rejected_up_front(self, tool):
        server = build_server(sessions={})
        kwargs = {"text": "hi"} if tool == "speak" else {}
        with patch("TTS_ka.mcp_server.fast_generate_audio", new=AsyncMock()) as gen:
            with pytest.raises(ToolError, match="invalid lang 'xx'"):
                await _call(server, tool, lang="xx", **kwargs)
        gen.assert_not_called()

    @pytest.mark.parametrize("tool", ["stream_open", "speak"])
    async def test_unknown_voice_rejected_up_front(self, tool):
        server = build_server(sessions={})
        kwargs = {"text": "hi"} if tool == "speak" else {}
        with pytest.raises(ToolError, match="unknown voice"):
            await _call(server, tool, voice="xx-XX-NobodyNeural", **kwargs)


class TestReaping:
    def test_reap_idle_sessions_is_pure_bookkeeping(self):
        fresh_s = type("S", (), {"last_activity": 1000.0})()
        stale_s = type("S", (), {"last_activity": 1000.0 - _mcp.SESSION_IDLE_TIMEOUT_S - 1})()
        sessions = {"a": fresh_s, "b": stale_s}
        assert _mcp._reap_idle_sessions(sessions, now=1000.0) == [stale_s]
        assert list(sessions) == ["a"]

    async def test_stream_open_reaps_forgotten_sessions(self, monkeypatch):
        sessions = {}
        server = build_server(sessions=sessions)
        monkeypatch.setattr(_mcp, "MAX_SESSIONS", 1)
        _, old_sess = await _open(server, sessions)
        old_sess.last_activity -= _mcp.SESSION_IDLE_TIMEOUT_S + 1
        new = await _call(server, "stream_open")
        assert list(sessions) == [new]
        assert old_sess._closed and old_sess.player.finished
        await _call(server, "stream_close", session_id=new)


class TestStopAndControls:
    async def test_stop_one_session_leaves_others(self):
        sessions = {}
        server = build_server(sessions=sessions)
        a, sa = await _open(server, sessions)
        b, sb = await _open(server, sessions)
        r = await _call(server, "stop", session_id=a)
        assert r == f"stopped session {a}"
        assert list(sessions) == [b]
        assert sa.player.stopped and not sb.player.stopped
        assert not os.path.exists(sa.tmp_dir)
        with pytest.raises(ToolError, match="unknown session_id"):
            await _call(server, "stop", session_id=a)

    async def test_stop_cancels_pending_synths(self):
        sessions = {}
        server = build_server(sessions=sessions)
        started = asyncio.Event()

        async def slow(text, lang, output, *, voice=None, prosody=None):
            started.set()
            await asyncio.sleep(3600)

        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=slow):
            sid, sess = await _open(server, sessions)
            await _call(server, "stream_append", session_id=sid, text="Never finishes. ")
            await started.wait()
            await asyncio.wait_for(_call(server, "stop"), timeout=2)
        assert all(t.done() for t in sess._tasks)

    @pytest.mark.parametrize("tool,method,word", [
        ("pause", "pause", "paused"),
        ("resume", "resume", "resumed"),
        ("skip", "skip_current", "skipped"),
    ])
    async def test_controls_route_to_one_or_all_players(self, tool, method, word):
        sessions = {}
        server = build_server(sessions=sessions)
        a, sa = await _open(server, sessions)
        b, sb = await _open(server, sessions)
        assert await _call(server, tool, session_id=a) == f"{word} 1 stream(s)"
        assert sa.player.controls == [method] and sb.player.controls == []
        assert await _call(server, tool) == f"{word} 2 stream(s)"
        assert sb.player.controls == [method]
        await _call(server, "stop")

    async def test_controls_unsupported_player_is_an_error(self):
        sessions = {}
        server = build_server(sessions=sessions)
        await _open(server, sessions)
        _StubPlayer.controllable = False
        with pytest.raises(ToolError, match="needs mpv"):
            await _call(server, "pause")
        await _call(server, "stop")

    async def test_controls_with_nothing_playing(self):
        server = build_server(sessions={})
        assert await _call(server, "pause") == "nothing is playing"


class TestSpeakThroughStreamingPlayer:
    """With mpv/VLC/ffplay installed, speak plays through a controllable player."""

    @pytest.fixture(autouse=True)
    def _player_found(self):
        with patch("TTS_ka.mcp_server.PlayerDetector.find", return_value="mpv"):
            yield

    async def test_queued_clip_plays_and_dir_is_removed_when_released(self):
        server = build_server(sessions={})
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch("TTS_ka.mcp_server.play_audio") as mplay:
            r = await _call(server, "speak", text="Hello there", lang="en")
            player = _StubPlayer.instances[-1]
            path = r.split()[1]
            assert r.startswith("queued")
            assert player.started and player.finished
            assert player.chunks == [(0, path)]
            await _drain_cleanup_tasks()
        mplay.assert_not_called()
        assert not os.path.exists(os.path.dirname(path))

    async def test_blocking_waits_for_release(self):
        server = build_server(sessions={})
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch.object(_StubPlayer, "wait_until_released", return_value=True) as mwait:
            r = await _call(server, "speak", text="Hello there", lang="en", blocking=True)
        assert r.startswith("played in")
        mwait.assert_called_once()
        assert not [d for d in _mcp._tmp_dirs if "ttska-mcp-one-" in d]

    async def test_clip_can_be_paused_while_playing(self):
        server = build_server(sessions={})
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch.object(_StubPlayer, "wait_until_released",
                          side_effect=lambda timeout=None: time.sleep(0.2) or True):
            await _call(server, "speak", text="Hello there", lang="en")
            assert await _call(server, "pause") == "paused 1 stream(s)"
            await _drain_cleanup_tasks()

    async def test_interrupt_stops_current_audio_first(self):
        sessions = {}
        server = build_server(sessions=sessions)
        sid, sess = await _open(server, sessions)
        with patch("TTS_ka.mcp_server.fast_generate_audio", side_effect=_write_one_byte), \
             patch("TTS_ka.mcp_server.stop_all_streaming_players") as mstop_all:
            await _call(server, "speak", text="Urgent", lang="en", interrupt=True)
            await _drain_cleanup_tasks()
        mstop_all.assert_called_once()
        assert sess.player.stopped and sessions == {}
