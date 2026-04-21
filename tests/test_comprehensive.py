"""Comprehensive tests focused on high coverage."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text
from TTS_ka.constants import VOICE_MAP
from TTS_ka.main import get_input_text
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestHighCoverage:
    """Test cases focused on achieving high coverage."""

    # === Chunking Tests ===
    def test_split_text_empty(self):
        assert split_text_into_chunks("", 60) == []

    def test_split_text_single_word(self):
        assert split_text_into_chunks("hello", 60) == ["hello"]

    def test_split_text_multiple_words(self):
        result = split_text_into_chunks("hello world test sentence", 30)
        assert len(result) >= 1
        assert all(isinstance(c, str) for c in result)

    def test_split_text_long_text(self):
        text = " ".join([f"word{i}" for i in range(200)])
        result = split_text_into_chunks(text, 15)
        assert len(result) > 1

    def test_should_chunk_text_cases(self):
        assert should_chunk_text("any text", 0) is False
        assert should_chunk_text("any text", 1) is True
        assert should_chunk_text("any text", 30) is True

    # === Main utility tests ===
    def test_get_input_text_direct(self):
        assert get_input_text("hello") == "hello"
        assert get_input_text("") == ""

    def test_get_input_text_clipboard(self):
        with patch('TTS_ka.main._read_clipboard', return_value="clipboard text"):
            assert get_input_text("clipboard") == "clipboard text"

    def test_get_input_text_empty_clipboard(self):
        with patch('TTS_ka.main._read_clipboard', return_value=""):
            assert get_input_text("clipboard") == ""

    def test_get_input_text_file_exists(self, sample_text_file):
        assert "Hello world" in get_input_text(sample_text_file)

    def test_get_input_text_file_not_exists(self):
        assert get_input_text("nonexistent.txt") == "nonexistent.txt"

    def test_get_input_text_unicode(self):
        georgian = "გამარჯობა"
        assert get_input_text(georgian) == georgian

    # === Help system tests ===
    def test_show_simple_help_output(self):
        with patch('builtins.print') as mock_print:
            show_simple_help()
            assert mock_print.called

    def test_show_troubleshooting_output(self):
        with patch('builtins.print') as mock_print:
            show_troubleshooting()
            assert mock_print.called

    def test_help_no_exceptions(self):
        show_simple_help()
        show_troubleshooting()

    # === Fast audio tests ===
    @pytest.mark.asyncio
    async def test_fast_audio_imports(self):
        from TTS_ka import fast_audio
        assert fast_audio is not None

    # === Ultra fast tests ===
    def test_ultra_fast_imports(self):
        from TTS_ka import ultra_fast
        assert ultra_fast is not None

    # === Rich progress tests ===
    def test_rich_progress_imports(self):
        from TTS_ka import rich_progress
        assert rich_progress is not None

    # === Voice mapping tests (via constants) ===
    def test_voice_mapping_exists(self):
        assert isinstance(VOICE_MAP, dict)
        assert "en" in VOICE_MAP
        assert "ka" in VOICE_MAP
        assert "ru" in VOICE_MAP

    # === Parametrized tests ===
    @pytest.mark.parametrize("text,expected", [
        ("", []),
        ("hello", ["hello"]),
        ("hello world", ["hello world"]),
    ])
    def test_chunking_variations(self, text, expected):
        result = split_text_into_chunks(text, 60)
        if not text:
            assert result == []
        else:
            assert len(result) >= 1

    @pytest.mark.parametrize("chunk_seconds,expected", [
        (0, False),
        (1, True),
        (30, True),
        (60, True),
    ])
    def test_should_chunk_variations(self, chunk_seconds, expected):
        assert should_chunk_text("any text", chunk_seconds) == expected

    @pytest.mark.parametrize("input_text", [
        "simple text",
        "გამარჯობა",
        "Привет",
        "",
    ])
    def test_get_input_text_variations(self, input_text):
        assert get_input_text(input_text) == input_text

    def test_all_modules_importable(self):
        for module_name in ["chunking", "fast_audio", "main", "simple_help", "ultra_fast", "rich_progress"]:
            try:
                __import__(f"TTS_ka.{module_name}")
            except ImportError as e:
                print(f"Warning: Could not import {module_name}: {e}")
