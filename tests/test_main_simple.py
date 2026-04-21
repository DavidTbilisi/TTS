"""Tests for main module CLI functionality."""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from TTS_ka.main import get_input_text, main


class TestMain:
    """Test cases for main CLI functionality."""

    def test_get_input_text_direct_text(self):
        """Test processing direct text input."""
        result = get_input_text("Hello world")
        assert result == "Hello world"

    def test_get_input_text_clipboard(self):
        """Test processing clipboard input."""
        with patch('TTS_ka.main._read_clipboard', return_value="clipboard text"):
            result = get_input_text("clipboard")
            assert result == "clipboard text"

    def test_get_input_text_empty_clipboard(self):
        """Test processing empty clipboard."""
        with patch('TTS_ka.main._read_clipboard', return_value=""):
            result = get_input_text("clipboard")
            assert result == ""

    def test_get_input_text_file(self, sample_text_file):
        """Test processing file input."""
        result = get_input_text(sample_text_file)
        assert result == "Hello world, this is a test."

    def test_get_input_text_nonexistent_file(self):
        """Test processing non-existent file."""
        result = get_input_text("nonexistent.txt")
        assert result == "nonexistent.txt"

    def test_main_basic_flow(self):
        """Test basic main function flow (main() is sync; it calls asyncio.run internally)."""
        test_args = ["test_script", "Hello world"]

        with patch('sys.argv', test_args), \
             patch('TTS_ka.main.asyncio') as mock_asyncio, \
             patch('builtins.print'):
            mock_asyncio.run = MagicMock()
            try:
                main()
            except SystemExit:
                pass

    def test_get_input_text_unicode(self):
        """Test processing Unicode text."""
        assert get_input_text("გამარჯობა") == "გამარჯობა"
        assert get_input_text("Привет") == "Привет"

    def test_get_input_text_multiline(self):
        """Test processing multiline text."""
        multiline = "Line 1\nLine 2\nLine 3"
        assert get_input_text(multiline) == multiline

    @pytest.mark.parametrize("input_text,expected", [
        ("simple", "simple"),
        ("", ""),
        ("unicode 🌍", "unicode 🌍"),
        ("multi\nline", "multi\nline"),
    ])
    def test_get_input_text_various_inputs(self, input_text, expected):
        """Test get_input_text with various inputs."""
        assert get_input_text(input_text) == expected
