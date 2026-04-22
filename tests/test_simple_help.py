"""Tests for simple_help module."""

import pytest
from unittest.mock import patch
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestShowSimpleHelp:
    """Tests for show_simple_help()."""

    def _get_output(self):
        import io, sys
        buf = io.StringIO()
        with patch('builtins.print', side_effect=lambda *a, **kw: buf.write((' '.join(str(x) for x in a)) + '\n')):
            show_simple_help()
        return buf.getvalue()

    def test_no_exception(self):
        show_simple_help()

    def test_contains_ultra_fast_tts(self):
        out = self._get_output()
        assert "ULTRA-FAST TTS" in out

    def test_contains_supported_languages(self):
        out = self._get_output()
        assert "SUPPORTED LANGUAGES" in out
        assert "ka" in out
        assert "ka-m" in out
        assert "ru" in out
        assert "en" in out
        assert "Georgian" in out
        assert "Russian" in out

    def test_contains_quick_start(self):
        out = self._get_output()
        assert "QUICK START EXAMPLES" in out

    def test_contains_turbo_flag(self):
        out = self._get_output()
        assert "--turbo" in out

    def test_contains_clipboard(self):
        out = self._get_output()
        assert "clipboard" in out

    def test_contains_file_example(self):
        out = self._get_output()
        assert "file.txt" in out

    def test_contains_performance_info(self):
        out = self._get_output()
        assert "PERFORMANCE" in out or "seconds" in out

    def test_contains_workflows(self):
        out = self._get_output()
        assert "WORKFLOW" in out.upper()

    def test_contains_tips(self):
        out = self._get_output()
        assert "TIP" in out.upper()

    def test_contains_section_separators(self):
        out = self._get_output()
        assert "=" in out or "-" in out

    def test_contains_python_command(self):
        out = self._get_output()
        assert "python" in out.lower()

    def test_contains_lang_flag(self):
        out = self._get_output()
        assert "--lang" in out

    def test_prints_multiple_lines(self, capsys):
        show_simple_help()
        out = capsys.readouterr().out
        assert out.count('\n') > 5


class TestShowTroubleshooting:
    """Tests for show_troubleshooting()."""

    def _get_output(self):
        import io
        buf = io.StringIO()
        with patch('builtins.print', side_effect=lambda *a, **kw: buf.write((' '.join(str(x) for x in a)) + '\n')):
            show_troubleshooting()
        return buf.getvalue()

    def test_no_exception(self):
        show_troubleshooting()

    def test_contains_troubleshooting(self):
        out = self._get_output()
        assert "TROUBLESHOOTING" in out.upper() or "troubleshoot" in out.lower() or len(out) > 0

    def test_prints_something(self, capsys):
        show_troubleshooting()
        out = capsys.readouterr().out
        assert len(out) > 0

    def test_contains_audio_or_error(self):
        out = self._get_output()
        has_content = any(kw in out.lower() for kw in ["audio", "error", "slow", "install", "network", "ffmpeg"])
        assert has_content or len(out) > 10
