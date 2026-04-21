"""Final comprehensive test suite for achieving high coverage."""

import pytest
import os
import inspect
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text
from TTS_ka.constants import VOICE_MAP
from TTS_ka.main import get_input_text
from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestFinalCoverage:
    """Final test suite focused on achievable high coverage."""

    # === Chunking ===
    def test_chunking_complete_coverage(self):
        assert split_text_into_chunks("", 60) == []
        assert split_text_into_chunks("word", 60) == ["word"]

        text_100 = " ".join([f"word{i}" for i in range(100)])
        for secs in (1, 60, 300):
            chunks = split_text_into_chunks(text_100, secs)
            assert len(chunks) >= 1

        assert should_chunk_text("any", 0) is False
        assert should_chunk_text("any", 1) is True

    # === Help ===
    def test_help_complete_coverage(self):
        count = 0
        def inc(*a, **k):
            nonlocal count
            count += 1

        with patch('builtins.print', side_effect=inc):
            show_simple_help()
            help_n = count
            count = 0
            show_troubleshooting()
            trouble_n = count

        assert help_n > 0
        assert trouble_n > 0

    # === Main input handling ===
    def test_main_get_input_text_complete(self, temp_dir):
        assert get_input_text("hello") == "hello"
        assert get_input_text("") == ""

        with patch('TTS_ka.main._read_clipboard', return_value="clipboard content"):
            assert get_input_text("clipboard") == "clipboard content"

        with patch('TTS_ka.main._read_clipboard', return_value=""):
            assert get_input_text("clipboard") == ""

        with patch('TTS_ka.main._read_clipboard', return_value="   \t \n  "):
            assert get_input_text("clipboard") == ""

        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("file content\nline 2")
        result = get_input_text(test_file)
        assert "file content" in result

        assert get_input_text("nonexistent.txt") == "nonexistent.txt"
        assert get_input_text(temp_dir) == temp_dir

    # === Fallback audio generator ===
    @pytest.mark.asyncio
    async def test_fallback_generate_success(self, temp_dir):
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_inst = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=mock_inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=True)
        assert result is True
        mock_inst.save.assert_called_with(output_path)

    @pytest.mark.asyncio
    async def test_fallback_generate_verbose(self, temp_dir, capsys):
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_inst = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=mock_inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=False)
        assert result is True
        assert capsys.readouterr().out != ""

    @pytest.mark.asyncio
    async def test_fallback_generate_exception(self, temp_dir, capsys):
        from TTS_ka.fast_audio import fallback_generate_audio
        output_path = os.path.join(temp_dir, "test.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(side_effect=Exception("Network error"))
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("test", "en", output_path, quiet=False)
        assert result is False
        assert capsys.readouterr().out != ""

    # === Voice mapping (constants) ===
    def test_audio_voice_mapping(self):
        expected = {
            "ka": "ka-GE-EkaNeural",
            "en": "en-GB-SoniaNeural",
            "ru": "ru-RU-SvetlanaNeural",
            "en-US": "en-US-SteffanNeural",
        }
        for lang, voice in expected.items():
            assert VOICE_MAP.get(lang) == voice
        assert VOICE_MAP.get("unknown", "en-GB-SoniaNeural") == "en-GB-SoniaNeural"

    def test_fast_merge_empty_raises(self):
        from TTS_ka.fast_audio import fast_merge_audio_files
        with pytest.raises(ValueError, match="No parts to merge"):
            fast_merge_audio_files([], "output.mp3")

    def test_play_audio_no_file_no_raise(self):
        from TTS_ka.fast_audio import play_audio
        play_audio("nonexistent_file.mp3")  # must not raise

    # === Module attributes ===
    def test_all_module_imports(self):
        for mod in ["TTS_ka.chunking", "TTS_ka.main", "TTS_ka.simple_help",
                    "TTS_ka.fast_audio", "TTS_ka.constants"]:
            __import__(mod)

    def test_module_attributes(self):
        import importlib
        from TTS_ka import fast_audio, chunking, simple_help, constants
        main_mod = importlib.import_module('TTS_ka.main')
        assert hasattr(fast_audio, 'fast_generate_audio')
        assert hasattr(fast_audio, 'fast_merge_audio_files')
        assert hasattr(fast_audio, 'play_audio')
        assert hasattr(fast_audio, 'AudioGenerator')
        assert hasattr(fast_audio, 'AudioMerger')
        assert hasattr(fast_audio, 'MergerFactory')
        assert hasattr(chunking, 'split_text_into_chunks')
        assert hasattr(main_mod, 'get_input_text')
        assert hasattr(simple_help, 'show_simple_help')
        assert hasattr(constants, 'VOICE_MAP')

    # === Parametrized ===
    @pytest.mark.parametrize("text,seconds,expected_behavior", [
        ("", 60, "empty"),
        ("single", 60, "single"),
        ("word1 word2 word3 word4 word5", 30, "chunks"),
        (" ".join([f"w{i}" for i in range(50)]), 15, "chunks"),
    ])
    def test_chunking_parametrized(self, text, seconds, expected_behavior):
        result = split_text_into_chunks(text, seconds)
        if expected_behavior == "empty":
            assert result == []
        elif expected_behavior == "single":
            assert len(result) == 1
        else:
            assert len(result) >= 1

    @pytest.mark.parametrize("input_text,expected", [
        ("direct text", "direct text"),
        ("", ""),
        ("unicode გამარჯობა", "unicode გამარჯობა"),
        ("multiple\nlines\nhere", "multiple\nlines\nhere"),
    ])
    def test_main_input_parametrized(self, input_text, expected):
        assert get_input_text(input_text) == expected

    @pytest.mark.parametrize("language,expected_voice", [
        ("ka", "ka-GE-EkaNeural"),
        ("en", "en-GB-SoniaNeural"),
        ("ru", "ru-RU-SvetlanaNeural"),
        ("en-US", "en-US-SteffanNeural"),
    ])
    def test_voice_mapping_parametrized(self, language, expected_voice):
        assert VOICE_MAP.get(language) == expected_voice

    # === Edge cases ===
    def test_edge_cases_comprehensive(self):
        assert split_text_into_chunks("   ", 60) == []
        assert should_chunk_text("", -1) is False
        assert get_input_text("   ") == "   "
        assert isinstance(VOICE_MAP, dict)
        assert len(VOICE_MAP) >= 4

    def test_function_signatures(self):
        sig1 = inspect.signature(split_text_into_chunks)
        assert 'text' in sig1.parameters
        assert 'approx_seconds' in sig1.parameters

        sig2 = inspect.signature(should_chunk_text)
        assert 'text' in sig2.parameters
        assert 'chunk_seconds' in sig2.parameters

        sig3 = inspect.signature(get_input_text)
        assert 'text_input' in sig3.parameters
