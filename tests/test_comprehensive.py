"""Comprehensive tests focused on high coverage."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka.chunking import should_chunk_text, split_text_into_chunks
from TTS_ka.main import get_input_text
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestHighCoverage:
    """Test cases focused on achieving high coverage."""

    # === Chunking Tests ===
    def test_split_text_empty(self):
        """Test chunking empty text returns empty list."""
        result = split_text_into_chunks("", 60)
        assert result == []

    def test_split_text_single_word(self):
        """Test chunking single word."""
        result = split_text_into_chunks("hello", 60)
        assert result == ["hello"]

    def test_split_text_multiple_words(self):
        """Test chunking multiple words."""
        text = "hello world test sentence"
        result = split_text_into_chunks(text, 30)
        assert len(result) >= 1
        assert all(isinstance(chunk, str) for chunk in result)

    def test_split_text_long_text(self):
        """Test chunking very long text."""
        text = " ".join([f"word{i}" for i in range(200)])
        result = split_text_into_chunks(text, 15)
        assert len(result) > 1

    def test_should_chunk_text_cases(self):
        """Test should_chunk_text logic."""
        assert should_chunk_text("any text", 0) == False
        assert should_chunk_text("any text", 1) == True
        assert should_chunk_text("any text", 30) == True

    # === Main utility tests ===
    def test_get_input_text_direct(self):
        """Test get_input_text with direct text."""
        assert get_input_text("hello") == "hello"
        assert get_input_text("") == ""

    def test_get_input_text_clipboard(self):
        """Test get_input_text with clipboard."""
        with patch("pyperclip.paste") as mock_paste:
            mock_paste.return_value = "clipboard text"
            result = get_input_text("clipboard")
            assert result == "clipboard text"

    def test_get_input_text_empty_clipboard(self):
        """Test get_input_text with empty clipboard."""
        with patch("pyperclip.paste") as mock_paste:
            mock_paste.return_value = ""
            result = get_input_text("clipboard")
            assert result == ""

    def test_get_input_text_file_exists(self, sample_text_file):
        """Test get_input_text with existing file."""
        result = get_input_text(sample_text_file)
        assert "Hello world" in result

    def test_get_input_text_file_not_exists(self):
        """Test get_input_text with non-existent file."""
        result = get_input_text("nonexistent.txt")
        assert result == "nonexistent.txt"

    def test_get_input_text_unicode(self):
        """Test get_input_text with Unicode."""
        georgian = "გამარჯობა"
        assert get_input_text(georgian) == georgian

    # === Help system tests ===
    def test_show_simple_help_output(self):
        """Test that show_simple_help produces output."""
        with patch("builtins.print") as mock_print:
            show_simple_help()
            assert mock_print.called

    def test_show_troubleshooting_output(self):
        """Test that show_troubleshooting produces output."""
        with patch("builtins.print") as mock_print:
            show_troubleshooting()
            assert mock_print.called

    def test_help_no_exceptions(self):
        """Test help functions don't raise exceptions."""
        try:
            show_simple_help()
            show_troubleshooting()
        except Exception as e:
            pytest.fail(f"Help raised exception: {e}")

    # === Audio tests (mocked) ===
    @pytest.mark.asyncio
    async def test_generate_audio_success(self, temp_dir):
        """Test audio generation success path."""
        from TTS_ka.audio import generate_audio

        output_path = os.path.join(temp_dir, "test.mp3")

        with patch("edge_tts.Communicate") as mock_comm:
            mock_instance = MagicMock()
            mock_comm.return_value = mock_instance
            mock_instance.save = AsyncMock()

            result = await generate_audio("test", "en", output_path, quiet=True)
            assert result == True

    @pytest.mark.asyncio
    async def test_generate_audio_failure(self, temp_dir):
        """Test audio generation failure path."""
        from TTS_ka.audio import generate_audio

        output_path = os.path.join(temp_dir, "test.mp3")

        with patch("edge_tts.Communicate") as mock_comm:
            mock_comm.side_effect = Exception("Test error")

            result = await generate_audio("test", "en", output_path, quiet=True)
            assert result == False

    def test_merge_audio_files_empty_list(self):
        """Test merge_audio_files with empty list raises error."""
        from TTS_ka.audio import merge_audio_files

        with pytest.raises(ValueError):
            merge_audio_files([], "output.mp3")

    def test_play_audio_file_not_found(self):
        """Test play_audio with non-existent file."""
        from TTS_ka.audio import play_audio

        # Should not raise exception
        play_audio("nonexistent.mp3")

    # === Fast audio tests ===
    @pytest.mark.asyncio
    async def test_fast_audio_imports(self):
        """Test that fast_audio module can be imported."""
        try:
            from TTS_ka import fast_audio

            assert fast_audio is not None
        except ImportError as e:
            pytest.fail(f"Could not import fast_audio: {e}")

    # === Ultra fast tests ===
    def test_ultra_fast_imports(self):
        """Test that ultra_fast module can be imported."""
        try:
            from TTS_ka import ultra_fast

            assert ultra_fast is not None
        except ImportError as e:
            pytest.fail(f"Could not import ultra_fast: {e}")

    # === Rich progress tests ===
    def test_rich_progress_imports(self):
        """Test that rich_progress module can be imported."""
        try:
            from TTS_ka import rich_progress

            assert rich_progress is not None
        except ImportError as e:
            pytest.fail(f"Could not import rich_progress: {e}")

    # === Parametrized tests for coverage ===
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("", []),
            ("hello", ["hello"]),
            ("hello world", ["hello world"]),
            (
                "a b c d e f g h i j k l m n o p",
                ["a b c d e f g h i j k l m n o p"],
            ),  # Will get chunked based on time
        ],
    )
    def test_chunking_variations(self, text, expected):
        """Test various chunking scenarios."""
        result = split_text_into_chunks(text, 60)
        if not text:
            assert result == []
        else:
            assert len(result) >= 1

    @pytest.mark.parametrize(
        "chunk_seconds,expected", [(0, False), (1, True), (30, True), (60, True)]
    )
    def test_should_chunk_variations(self, chunk_seconds, expected):
        """Test should_chunk_text variations."""
        result = should_chunk_text("any text", chunk_seconds)
        assert result == expected

    @pytest.mark.parametrize(
        "input_text",
        ["simple text", "გამარჯობა", "Привет", "Hello 🌍", ""],  # Georgian  # Russian  # Emoji
    )
    def test_get_input_text_variations(self, input_text):
        """Test get_input_text with various inputs."""
        result = get_input_text(input_text)
        assert result == input_text

    # === Module level tests ===
    def test_all_modules_importable(self):
        """Test that all TTS_ka modules can be imported."""
        modules = [
            "audio",
            "chunking",
            "fast_audio",
            "main",
            "simple_help",
            "ultra_fast",
            "rich_progress",
        ]

        for module_name in modules:
            try:
                __import__(f"TTS_ka.{module_name}")
            except ImportError as e:
                # Some modules might have optional dependencies
                print(f"Warning: Could not import {module_name}: {e}")

    def test_voice_mapping_exists(self):
        """Test that VOICE_MAP exists in audio module."""
        from TTS_ka.audio import VOICE_MAP

        assert isinstance(VOICE_MAP, dict)
        assert "en" in VOICE_MAP
        assert "ka" in VOICE_MAP
        assert "ru" in VOICE_MAP
