"""Tests for main module CLI functionality."""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.main import get_input_text


class TestGetInputText:
    """Tests for get_input_text() helper."""

    def test_direct_text(self):
        assert get_input_text("Hello world") == "Hello world"

    def test_clipboard(self):
        with patch('pyperclip.paste', return_value="clipboard text"):
            assert get_input_text("clipboard") == "clipboard text"

    def test_clipboard_empty(self, capsys):
        with patch('pyperclip.paste', return_value="   "):
            result = get_input_text("clipboard")
        assert result == ""
        assert "No text" in capsys.readouterr().out

    def test_clipboard_strips_crlf(self):
        with patch('pyperclip.paste', return_value="line1\r\nline2"):
            result = get_input_text("clipboard")
        assert result == "line1\nline2"

    def test_file_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("file content", encoding="utf-8")
        assert get_input_text(str(f)) == "file content"

    def test_nonexistent_file_treated_as_text(self):
        result = get_input_text("nonexistent_xyz.txt")
        assert result == "nonexistent_xyz.txt"


class TestMain:
    """Tests for main() entry point."""

    def test_no_text_shows_help(self, capsys):
        """main() with no text argument prints help and returns."""
        with patch('sys.argv', ['TTS_ka']):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert "Error: No text provided" in out

    def test_help_full_calls_show_simple_help(self, capsys):
        """--help-full calls show_simple_help and show_troubleshooting."""
        with patch('sys.argv', ['TTS_ka', 'hello', '--help-full']):
            with patch('TTS_ka.main.show_simple_help') as msh, \
                 patch('TTS_ka.main.show_troubleshooting') as mst:
                from TTS_ka.main import main
                main()
        msh.assert_called_once()
        mst.assert_called_once()

    def test_direct_generation_no_play(self):
        """Short text goes through fast_generate_audio; --no-play skips playback."""
        with patch('sys.argv', ['TTS_ka', 'Hello', '--lang', 'en', '--no-play']):
            with patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)) as mfa, \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()
        mfa.assert_called_once()

    def test_stream_flag_passes_enable_streaming(self):
        """--stream routes through smart_generate_long_text with enable_streaming=True."""
        with patch('sys.argv', ['TTS_ka', 'Hello world', '--lang', 'en', '--stream', '--no-play']):
            with patch('TTS_ka.main.smart_generate_long_text', new=AsyncMock()) as msl, \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()
        msl.assert_called_once()
        _, kwargs = msl.call_args
        assert kwargs.get('enable_streaming') is True

    def test_no_play_skips_play_audio(self):
        """play_audio is NOT called when --no-play is used."""
        with patch('sys.argv', ['TTS_ka', 'hi', '--lang', 'en', '--no-play']):
            with patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.main.play_audio') as mpa, \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()
        mpa.assert_not_called()

    def test_keyboard_interrupt_handled(self, capsys):
        """KeyboardInterrupt during asyncio.run is caught gracefully."""
        with patch('sys.argv', ['TTS_ka', 'hi', '--lang', 'en', '--no-play']):
            with patch('asyncio.run', side_effect=KeyboardInterrupt):
                from TTS_ka.main import main
                main()
        assert "cancelled" in capsys.readouterr().out.lower()

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
    def test_valid_languages_accepted(self, lang):
        """Parser accepts ka, ru, en."""
        with patch('sys.argv', ['TTS_ka', 'test', '--lang', lang, '--no-play']):
            with patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()  # must not raise SystemExit

    def test_invalid_language_exits(self):
        """Parser rejects unknown language codes."""
        with patch('sys.argv', ['TTS_ka', 'test', '--lang', 'xx']):
            import argparse
            with pytest.raises(SystemExit):
                from TTS_ka.main import main
                main()

    def test_clipboard_input_via_main(self):
        """'clipboard' text arg reads from pyperclip."""
        with patch('sys.argv', ['TTS_ka', 'clipboard', '--lang', 'en', '--no-play']):
            with patch('pyperclip.paste', return_value='pasted text'), \
                 patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()

    def test_file_input_via_main(self, tmp_path):
        """File path text arg reads the file content."""
        f = tmp_path / "input.txt"
        f.write_text("file text", encoding="utf-8")
        with patch('sys.argv', ['TTS_ka', str(f), '--lang', 'en', '--no-play']):
            with patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()), \
                 patch('TTS_ka.main.get_optimal_settings', return_value={'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}):
                from TTS_ka.main import main
                main()

    def test_no_turbo_skips_optimization(self, capsys):
        """--no-turbo skips the optimization block."""
        with patch('sys.argv', ['TTS_ka', 'hello', '--lang', 'en', '--no-play', '--no-turbo']):
            with patch('TTS_ka.main.fast_generate_audio', new=AsyncMock(return_value=True)), \
                 patch('TTS_ka.main.cleanup_http', new=AsyncMock()):
                from TTS_ka.main import main
                main()
        assert "OPTIMIZED MODE" not in capsys.readouterr().out
