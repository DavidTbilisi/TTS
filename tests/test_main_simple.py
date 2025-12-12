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
        with patch('pyperclip.paste') as mock_paste:
            mock_paste.return_value = "clipboard text"
            result = get_input_text("clipboard")
            assert result == "clipboard text"

    def test_get_input_text_empty_clipboard(self):
        """Test processing empty clipboard."""
        with patch('pyperclip.paste') as mock_paste:
            mock_paste.return_value = ""
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

    @pytest.mark.asyncio
    async def test_main_basic_flow(self):
        """Test basic main function flow."""
        test_args = ["test_script", "Hello world"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.fast_generate_audio') as mock_generate:
                mock_generate.return_value = None
                
                with patch('TTS_ka.main.play_audio'):
                    with patch('builtins.print'):
                        try:
                            await main()
                        except SystemExit:
                            pass  # Expected for argument parsing

    @pytest.mark.asyncio
    async def test_main_chunking_flow(self):
        """Test main function with chunking."""
        test_args = ["test_script", "Long text", "--chunk-seconds", "30"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.should_chunk_text') as mock_should_chunk:
                mock_should_chunk.return_value = True
                
                with patch('TTS_ka.main.smart_generate_long_text') as mock_smart:
                    mock_smart.return_value = None
                    
                    with patch('TTS_ka.main.play_audio'):
                        with patch('builtins.print'):
                            try:
                                await main()
                            except SystemExit:
                                pass  # Expected for argument parsing

    def test_get_input_text_unicode(self):
        """Test processing Unicode text."""
        georgian_text = "გამარჯობა"
        result = get_input_text(georgian_text)
        assert result == georgian_text
        
        russian_text = "Привет"
        result = get_input_text(russian_text)
        assert result == russian_text

    def test_get_input_text_multiline(self):
        """Test processing multiline text."""
        multiline = "Line 1\nLine 2\nLine 3"
        result = get_input_text(multiline)
        assert result == multiline

    @pytest.mark.parametrize("input_text,expected", [
        ("simple", "simple"),
        ("", ""),
        ("unicode 🌍", "unicode 🌍"),
        ("multi\nline", "multi\nline")
    ])
    def test_get_input_text_various_inputs(self, input_text, expected):
        """Test get_input_text with various inputs."""
        result = get_input_text(input_text)
        assert result == expected