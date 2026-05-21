"""Tests for the MCP server tool surface.

We don't exercise the JSON-RPC transport — that's the mcp library's job.
Instead we call the tool callables directly via FastMCP's `call_tool`
to verify the wiring, session lifecycle, and stdout safety.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("mcp", reason="mcp extra not installed")

from TTS_ka.mcp_server import _LiveSession, build_server  # noqa: E402


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

    FastMCP wraps scalar returns in ``{"result": value}``; we peel that off.
    Dict / list returns from tools with explicit shapes pass through as-is
    (FastMCP keeps the top-level field name).
    """
    _, structured = await server.call_tool(name, kwargs)
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

            r = await _call(server, "stream_append",
                            session_id=sid, text="One. Two! ")
            assert "queued 2" in r

            r = await _call(server, "stream_close", session_id=sid)
            assert "closed" in r
            assert sid not in sessions

    @pytest.mark.asyncio
    async def test_append_unknown_session(self):
        sessions = {}
        server = build_server(sessions=sessions)
        r = await _call(server, "stream_append",
                        session_id="bogus", text="hi")
        assert "unknown session_id" in r

    @pytest.mark.asyncio
    async def test_close_unknown_session(self):
        sessions = {}
        server = build_server(sessions=sessions)
        r = await _call(server, "stream_close", session_id="bogus")
        assert "unknown session_id" in r

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
                c = await _call(server, "stream_open")
                assert "error" in c
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
            r = await _call(server, "speak", text="hi", lang="en")
        assert "error" in r
        assert "network down" in r

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
            sid1 = await _call(server, "stream_open")
            sid2 = await _call(server, "stream_open")
            assert len(sessions) == 2
            r = await _call(server, "stop")
        assert "stopped 2" in r
        assert sessions == {}

    @pytest.mark.asyncio
    async def test_stop_when_empty_returns_zero(self):
        server = build_server(sessions={})
        with patch("TTS_ka.mcp_server.stop_active_streaming_player"):
            r = await _call(server, "stop")
        assert "stopped 0" in r


class TestSessionStatus:
    @pytest.mark.asyncio
    async def test_status_unknown_session(self):
        server = build_server(sessions={})
        r = await _call(server, "session_status", session_id="bogus")
        assert "error" in r
        assert "unknown session_id" in r["error"]

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
        # FastMCP wraps list returns in a {"result": [...]} structured payload.
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
