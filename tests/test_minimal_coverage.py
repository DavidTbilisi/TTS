"""Minimal focused test suite for achievable coverage."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text
from TTS_ka.constants import VOICE_MAP
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestMinimalCoverage:
    """Test suite focusing on modules without complex dependencies."""

    # === Chunking (100% coverage target) ===
    def test_chunking_all_paths(self):
        assert split_text_into_chunks("", 60) == []
        assert split_text_into_chunks("word", 60) == ["word"]

        long_text = " ".join([f"word{i}" for i in range(200)])
        assert len(split_text_into_chunks(long_text, 5)) > 1
        assert len(split_text_into_chunks(long_text, 60)) >= 1
        assert len(split_text_into_chunks(long_text, 300)) >= 1

        assert should_chunk_text("any text", 0) is False
        assert should_chunk_text("any text", 1) is True
        assert should_chunk_text("", 60) is True

    # === Simple help (100% coverage target) ===
    def test_simple_help_all_functions(self):
        calls: list = []
        with patch('builtins.print', side_effect=lambda *a, **k: calls.append(a)):
            show_simple_help()
            help_n = len(calls)
            calls.clear()
            show_troubleshooting()
            trouble_n = len(calls)
        assert help_n > 0
        assert trouble_n > 0

    # === Voice mapping (constants) ===
    def test_voice_map_complete(self):
        expected = {
            "ka": "ka-GE-EkaNeural",
            "en": "en-GB-SoniaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "en-US": "en-US-SteffanNeural",
        }
        for lang, voice in expected.items():
            assert VOICE_MAP[lang] == voice
        assert VOICE_MAP.get("unknown_lang", "default") == "default"

    @pytest.mark.parametrize("lang", ["ka", "en", "ru", "en-US"])
    def test_voice_mapping_parametrized(self, lang):
        voice = VOICE_MAP.get(lang)
        assert voice is not None
        assert voice.endswith("Neural")

    # === Fast audio merger tests ===
    def test_merge_empty_raises(self):
        from TTS_ka.fast_audio import fast_merge_audio_files
        with pytest.raises(ValueError, match="No parts to merge"):
            fast_merge_audio_files([], "output.mp3")

    def test_merge_single_file(self, temp_dir):
        from TTS_ka.fast_audio import fast_merge_audio_files
        src = os.path.join(temp_dir, "input.mp3")
        dst = os.path.join(temp_dir, "output.mp3")
        with open(src, "wb") as f:
            f.write(b"dummy")
        fast_merge_audio_files([src], dst)
        assert os.path.exists(dst)

    def test_merge_multiple_with_pydub(self, temp_dir):
        from TTS_ka.fast_audio import fast_merge_audio_files, PydubMerger
        parts = []
        for i in range(3):
            p = os.path.join(temp_dir, f"p{i}.mp3")
            with open(p, "wb") as f:
                f.write(b"dummy")
            parts.append(p)
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', True), \
             patch.object(PydubMerger, 'merge') as mock_merge:
            fast_merge_audio_files(parts, out)
        mock_merge.assert_called_once_with(parts, out)

    def test_merge_multiple_no_pydub_ffmpeg(self, temp_dir):
        from TTS_ka.fast_audio import fast_merge_audio_files
        parts = []
        for i in range(2):
            p = os.path.join(temp_dir, f"p{i}.mp3")
            with open(p, "wb") as f:
                f.write(b"dummy")
            parts.append(p)
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0):
            fast_merge_audio_files(parts, out)

    # === play_audio ===
    def test_play_audio_no_raise(self):
        from TTS_ka.fast_audio import play_audio
        play_audio("nonexistent_file.mp3")  # must not raise

    # === Parametrized chunking ===
    @pytest.mark.parametrize("text,seconds", [
        ("", 60),
        ("word", 30),
        ("multiple words here", 45),
        (" ".join([f"w{i}" for i in range(10)]), 20),
        (" ".join([f"word{i}" for i in range(100)]), 120),
    ])
    def test_chunking_parametrized(self, text, seconds):
        result = split_text_into_chunks(text, seconds)
        if not text:
            assert result == []
        else:
            assert len(result) >= 1
            assert all(isinstance(c, str) for c in result)

    @pytest.mark.parametrize("text,seconds,expected", [
        ("any text", 0, False),
        ("any text", 1, True),
        ("any text", 60, True),
        ("", 60, True),
        ("", 0, False),
    ])
    def test_should_chunk_parametrized(self, text, seconds, expected):
        assert should_chunk_text(text, seconds) == expected

    # === Importable modules check ===
    def test_importable_modules(self):
        from TTS_ka import chunking, simple_help, fast_audio, constants
        assert hasattr(chunking, 'split_text_into_chunks')
        assert hasattr(simple_help, 'show_simple_help')
        assert hasattr(fast_audio, 'AudioGenerator')
        assert hasattr(fast_audio, 'AudioMerger')
        assert hasattr(fast_audio, 'MergerFactory')
        assert hasattr(constants, 'VOICE_MAP')

    def test_chunking_edge_cases(self):
        assert split_text_into_chunks("   ", 60) == []
        long_word = "a" * 1000
        assert split_text_into_chunks(long_word, 60) == [long_word]
        assert should_chunk_text("text", -1) is False
        assert should_chunk_text("text", 0) is False
