"""FEAT-4: stdin auto-detect + --json structured output."""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_main(argv, stdin_text=None, isatty=True):
    """Run main() with mocked generation and a controlled stdin."""
    stdin_obj = io.StringIO(stdin_text) if stdin_text is not None else io.StringIO("")
    stdin_obj.isatty = lambda: isatty
    with patch("sys.argv", argv), \
         patch("sys.stdin", stdin_obj), \
         patch("TTS_ka.main.fast_generate_audio",
               new=AsyncMock(return_value=True)) as mfa, \
         patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
         patch("TTS_ka.main.get_optimal_settings",
               return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
        from TTS_ka.main import main
        main()
    return mfa


class TestStdinInput:
    def test_explicit_dash_reads_stdin(self):
        mfa = _stub_main(
            ["TTS_ka", "-", "--lang", "en", "--no-play"],
            stdin_text="piped hello",
            isatty=False,
        )
        assert "piped hello" in mfa.call_args.args[0]

    def test_piped_stdin_no_text_arg(self):
        """No text arg + stdin not a TTY -> read stdin."""
        mfa = _stub_main(
            ["TTS_ka", "--lang", "en", "--no-play"],
            stdin_text="auto-detected",
            isatty=False,
        )
        assert "auto-detected" in mfa.call_args.args[0]

    def test_tty_stdin_no_text_arg_shows_help(self, capsys):
        """No text arg + stdin is a TTY -> show help, do not block."""
        from unittest.mock import AsyncMock
        with patch("sys.argv", ["TTS_ka"]), \
             patch("sys.stdin", new=MagicMock(isatty=lambda: True)), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)) as mfa, \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()):
            from TTS_ka.main import main
            main()
        mfa.assert_not_called()
        assert "--doctor" in capsys.readouterr().out


class TestJSONMode:
    def _capture_main_stdout(self, argv, stdin_text=""):
        """Invoke main and capture the *real* stdout (where JSON events go)."""
        buf = io.StringIO()
        stdin_obj = io.StringIO(stdin_text)
        stdin_obj.isatty = lambda: stdin_text == ""
        with patch("sys.argv", argv), \
             patch("sys.stdout", buf), \
             patch("sys.stdin", stdin_obj), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
            from TTS_ka.main import main
            main()
        return buf.getvalue()

    def _parse_lines(self, text):
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
        return events

    def test_every_line_is_valid_json(self):
        out = self._capture_main_stdout(
            ["TTS_ka", "hello world", "--lang", "en", "--no-play", "--json"]
        )
        events = self._parse_lines(out)
        assert len(events) >= 2

    def test_emits_start_and_done_events(self):
        out = self._capture_main_stdout(
            ["TTS_ka", "hello world", "--lang", "en", "--no-play", "--json"]
        )
        events = self._parse_lines(out)
        event_types = [e.get("event") for e in events]
        assert "start" in event_types
        assert "done" in event_types

    def test_done_event_includes_output_and_duration(self):
        out = self._capture_main_stdout(
            ["TTS_ka", "hello world", "--lang", "en", "--no-play", "--json"]
        )
        events = self._parse_lines(out)
        done = next(e for e in events if e["event"] == "done")
        assert "output" in done
        assert "seconds" in done
        assert isinstance(done["seconds"], (int, float))

    def test_json_mode_suppresses_emoji_lines_on_real_stdout(self):
        """In --json mode, no '⚡' or 'OPTIMIZED MODE' should appear on stdout."""
        out = self._capture_main_stdout(
            ["TTS_ka", "hello world", "--lang", "en", "--no-play", "--json"]
        )
        assert "⚡" not in out
        assert "OPTIMIZED MODE" not in out

    def test_no_text_in_json_mode_emits_error_event(self):
        from unittest.mock import AsyncMock
        buf = io.StringIO()
        with patch("sys.argv", ["TTS_ka", "--json"]), \
             patch("sys.stdout", buf), \
             patch("sys.stdin", new=MagicMock(isatty=lambda: True)), \
             patch("TTS_ka.main.fast_generate_audio",
                   new=AsyncMock(return_value=True)), \
             patch("TTS_ka.main.cleanup_http", new=AsyncMock()):
            from TTS_ka.main import main
            main()
        events = [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
        assert any(e.get("event") == "error" for e in events)
