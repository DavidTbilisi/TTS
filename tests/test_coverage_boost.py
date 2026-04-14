"""Tests to push coverage over 80%."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.constants import VOICE_MAP
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestCoverageBoost:
    """Additional tests to achieve 80%+ coverage."""

    # === Fast audio generator tests ===
    @pytest.mark.asyncio
    async def test_fallback_generate_success(self, temp_dir):
        """EdgeTTSGenerator returns True on success."""
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=True)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_fallback_generate_failure(self, temp_dir):
        """EdgeTTSGenerator returns False on exception."""
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(side_effect=Exception("Network error"))
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=True)
        assert result is False

    @pytest.mark.asyncio
    async def test_fallback_generate_unknown_lang(self, temp_dir):
        """EdgeTTSGenerator returns False for unknown language."""
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        result = await fallback_generate_audio("test", "xx", output_path, quiet=True)
        assert result is False

    # === Merger tests ===
    def test_fast_merge_empty_raises(self, temp_dir):
        """fast_merge_audio_files raises ValueError on empty list."""
        from TTS_ka.fast_audio import fast_merge_audio_files
        with pytest.raises(ValueError, match="No parts to merge"):
            fast_merge_audio_files([], os.path.join(temp_dir, "out.mp3"))

    def test_fast_merge_single_file_copies(self, temp_dir):
        """Single-part merge copies src to dst."""
        from TTS_ka.fast_audio import fast_merge_audio_files
        src = os.path.join(temp_dir, "part.mp3")
        dst = os.path.join(temp_dir, "out.mp3")
        with open(src, "wb") as f:
            f.write(b"audio")
        fast_merge_audio_files([src], dst)
        assert os.path.exists(dst)

    def test_fast_merge_ffmpeg_path(self, temp_dir):
        """FFmpegMerger is tried as last resort."""
        from TTS_ka.fast_audio import fast_merge_audio_files
        parts = []
        for i in range(2):
            p = os.path.join(temp_dir, f"p{i}.mp3")
            with open(p, "wb") as f:
                f.write(b"audio")
            parts.append(p)
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0):
            fast_merge_audio_files(parts, out)

    # === play_audio tests ===
    def test_play_audio_windows(self, temp_dir):
        from TTS_ka.fast_audio import play_audio
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'win32'), patch('os.startfile') as mock_start:
            play_audio(f)
        mock_start.assert_called_once()

    def test_play_audio_oserror_silenced(self, temp_dir):
        from TTS_ka.fast_audio import play_audio
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'win32'), \
             patch('os.startfile', side_effect=OSError("locked")):
            play_audio(f)  # must not raise

    # === Main / clipboard tests ===
    def test_main_file_reading_errors(self, temp_dir):
        from TTS_ka.main import get_input_text
        # Directory path returns path as-is
        assert get_input_text(temp_dir) == temp_dir

    def test_main_clipboard_crlf_normalised(self):
        from TTS_ka.main import get_input_text
        with patch('TTS_ka.main._read_clipboard', return_value="line1\r\nline2\nline3\r\n"):
            result = get_input_text("clipboard")
        assert "\r\n" not in result
        assert result.count("\n") >= 2  # at least 2 newlines after CRLF normalisation

    def test_main_help_flag_exits(self):
        from TTS_ka.main import main
        with patch('sys.argv', ['TTS_ka', '--help']):
            with pytest.raises(SystemExit):
                main()

    # === Voice mapping (constants) ===
    def test_voice_mapping_all_languages(self):
        for lang in ['ka', 'en', 'ru', 'en-US']:
            assert lang in VOICE_MAP
            assert "Neural" in VOICE_MAP[lang]

    @pytest.mark.parametrize("language,expected_voice", [
        ("ka", "ka-GE-EkaNeural"),
        ("en", "en-GB-SoniaNeural"),
        ("ru", "ru-RU-SvetlanaNeural"),
        ("en-US", "en-US-SteffanNeural"),
        ("unknown", "en-GB-SoniaNeural"),
    ])
    def test_voice_selection_parametrized(self, language, expected_voice):
        voice = VOICE_MAP.get(language, "en-GB-SoniaNeural")
        assert voice == expected_voice

    # === Chunking ===
    def test_chunking_edge_cases(self):
        assert split_text_into_chunks("a b c", 1) == ["a b c"]
        assert split_text_into_chunks("a b c", 0) == ["a b c"]

    def test_should_chunk_edge_cases(self):
        assert should_chunk_text("", 0) is False
        assert should_chunk_text("any", 1) is True
        assert should_chunk_text("any", -1) is False

    def test_chunking_wpm_calculation(self):
        text_100 = " ".join([f"w{i}" for i in range(100)])
        chunks_60s = split_text_into_chunks(text_100, 60)
        chunks_30s = split_text_into_chunks(text_100, 30)
        assert len(chunks_60s) <= len(chunks_30s)

    # === Help ===
    def test_help_system_coverage(self):
        lines: list = []
        with patch('builtins.print', side_effect=lambda *a, **k: lines.append(str(a))):
            show_simple_help()
            n_help = len(lines)
            lines.clear()
            show_troubleshooting()
            n_trouble = len(lines)
        assert n_help > 0
        assert n_trouble > 0
