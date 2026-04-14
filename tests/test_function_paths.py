"""Tests for function execution paths to increase coverage."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.constants import VOICE_MAP
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestFunctionPaths:
    """Test various function execution paths for coverage."""

    # === Chunking ===
    def test_chunking_word_calculation(self):
        text = " ".join([f"word{i}" for i in range(100)])
        short_chunks = split_text_into_chunks(text, 10)
        long_chunks = split_text_into_chunks(text, 120)
        assert len(short_chunks) >= len(long_chunks)
        # Minimum word guard — very short time still produces a valid chunk
        very_short = split_text_into_chunks("a b c", 1)
        assert len(very_short) == 1

    @pytest.mark.parametrize("approx_seconds", [1, 5, 15, 30, 60, 120, 300])
    def test_chunking_time_variations(self, approx_seconds):
        words = ["word"] * 50
        text = " ".join(words)
        chunks = split_text_into_chunks(text, approx_seconds)
        assert len(chunks) >= 1
        reconstructed = []
        for chunk in chunks:
            reconstructed.extend(chunk.split())
        assert len(reconstructed) == len(words)

    # === Voice mapping (constants) ===
    def test_voice_mapping(self):
        assert 'ka' in VOICE_MAP
        assert 'en' in VOICE_MAP
        assert 'ru' in VOICE_MAP
        assert 'en-US' in VOICE_MAP
        for lang, voice in VOICE_MAP.items():
            assert isinstance(voice, str)
            assert len(voice) > 0

    # === Fallback audio generator ===
    @pytest.mark.asyncio
    async def test_fallback_generate_all_languages(self, temp_dir):
        from TTS_ka.fast_audio import fallback_generate_audio
        for lang in ['ka', 'en', 'ru']:
            output_path = os.path.join(temp_dir, f"out_{lang}.mp3")
            mock_inst = AsyncMock()
            mock_edge = MagicMock()
            mock_edge.Communicate = MagicMock(return_value=mock_inst)
            with patch.dict('sys.modules', {'edge_tts': mock_edge}):
                result = await fallback_generate_audio("test", lang, output_path, quiet=True)
            assert result is True
            used_voice = mock_edge.Communicate.call_args[0][1]
            assert used_voice == VOICE_MAP[lang]

    @pytest.mark.asyncio
    async def test_fallback_generate_unknown_language(self, temp_dir):
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        result = await fallback_generate_audio("test", "unknown", output_path, quiet=True)
        assert result is False

    @pytest.mark.asyncio
    async def test_fallback_generate_verbose_mode(self, temp_dir, capsys):
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_inst = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=mock_inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=False)
        assert result is True
        assert capsys.readouterr().out != ""

    # === Merger paths ===
    def test_merge_single_file(self, temp_dir):
        from TTS_ka.fast_audio import fast_merge_audio_files
        src = os.path.join(temp_dir, "input.mp3")
        dst = os.path.join(temp_dir, "output.mp3")
        with open(src, "wb") as f:
            f.write(b"dummy")
        fast_merge_audio_files([src], dst)
        assert os.path.exists(dst)

    def test_merge_no_pydub_uses_ffmpeg(self, temp_dir):
        from TTS_ka.fast_audio import fast_merge_audio_files
        parts = []
        for i in range(2):
            p = os.path.join(temp_dir, f"input{i}.mp3")
            with open(p, "wb") as f:
                f.write(b"dummy")
            parts.append(p)
        out = os.path.join(temp_dir, "output.mp3")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0):
            fast_merge_audio_files(parts, out)

    # === play_audio ===
    def test_play_audio_no_raise(self, temp_dir):
        from TTS_ka.fast_audio import play_audio
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"dummy")
        play_audio(f)  # best-effort, must not raise

    # === Main clipboard ===
    def test_main_input_clipboard_newlines(self):
        from TTS_ka.main import get_input_text
        with patch('TTS_ka.main._read_clipboard', return_value="line1\r\nline2\r\nline3"):
            result = get_input_text("clipboard")
        assert result == "line1\nline2\nline3"

    def test_main_input_whitespace_clipboard(self):
        from TTS_ka.main import get_input_text
        with patch('TTS_ka.main._read_clipboard', return_value="   \t  \n  "):
            result = get_input_text("clipboard")
        assert result == ""

    def test_main_file_reading(self, temp_dir):
        from TTS_ka.main import get_input_text
        unicode_file = os.path.join(temp_dir, "unicode.txt")
        with open(unicode_file, "w", encoding="utf-8") as f:
            f.write("გამარჯობა\nПривет\nHello")
        result = get_input_text(unicode_file)
        assert "გამარჯობა" in result
        assert "Привет" in result

    # === Help ===
    def test_simple_help_all_functions(self):
        with patch('builtins.print') as mock_print:
            show_simple_help()
            assert mock_print.call_count > 0
            mock_print.reset_mock()
            show_troubleshooting()
            assert mock_print.call_count > 0

    # === Module attributes ===
    def test_import_coverage(self):
        import importlib
        from TTS_ka import chunking, simple_help, fast_audio, constants
        main_mod = importlib.import_module('TTS_ka.main')
        assert hasattr(chunking, 'split_text_into_chunks')
        assert hasattr(main_mod, 'get_input_text')
        assert hasattr(simple_help, 'show_simple_help')
        assert hasattr(fast_audio, 'AudioGenerator')
        assert hasattr(fast_audio, 'MergerFactory')
        assert hasattr(constants, 'VOICE_MAP')
