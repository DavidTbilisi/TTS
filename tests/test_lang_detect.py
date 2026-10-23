"""--lang auto: script-based language detection."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka.fast_audio import EdgeTTSGenerator, generate_audio_with_subs
from TTS_ka.lang_detect import detect_lang, resolve_lang
from TTS_ka.voices import validate_lang_voice


class TestDetectLang:
    @pytest.mark.parametrize("text, lang", [
        ("გამარჯობა, როგორ ხარ?", "ka"),
        ("ᲒᲐᲛᲐᲠᲯᲝᲑᲐ", "ka"),              # Mtavruli capitals
        ("Привет, как дела?", "ru"),
        ("Hello, how are you?", "en"),
        ("Café déjà vu", "en"),
    ])
    def test_single_script(self, text, lang):
        assert detect_lang(text) == lang

    def test_majority_script_wins(self):
        # Georgian sentence with an English product name stays Georgian.
        assert detect_lang("გახსენი Visual Studio Code და დაელოდე") == "ka"
        assert detect_lang("Open the файл now please") == "en"

    def test_no_letters_returns_fallback(self):
        assert detect_lang("42 — 7.5%") == "en"
        assert detect_lang("123", fallback="ka") == "ka"
        assert detect_lang("") == "en"

    def test_resolve_lang_passes_explicit_lang_through(self):
        assert resolve_lang("ka-m", "Hello") == "ka-m"
        assert resolve_lang("auto", "Привет") == "ru"


class TestValidation:
    def test_auto_is_a_valid_lang(self):
        assert validate_lang_voice("auto", None) is None

    def test_auto_with_voice_is_valid(self):
        assert validate_lang_voice("auto", "en-US-JennyNeural") is None


def _mock_edge():
    mock_edge = MagicMock()
    mock_edge.Communicate = MagicMock(return_value=AsyncMock())
    return mock_edge


class TestGeneratorResolvesAuto:
    @pytest.mark.parametrize("text, voice", [
        ("გამარჯობა", "ka-GE-EkaNeural"),
        ("Привет", "ru-RU-SvetlanaNeural"),
        ("Hello", "en-GB-SoniaNeural"),
    ])
    async def test_auto_picks_default_voice_per_text(self, temp_dir, text, voice):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = _mock_edge()
        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            assert await EdgeTTSGenerator().generate(text, "auto", out, quiet=True)
        assert mock_edge.Communicate.call_args[0][1] == voice

    async def test_explicit_voice_beats_auto(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = _mock_edge()
        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            assert await EdgeTTSGenerator().generate(
                "გამარჯობა", "auto", out, quiet=True, voice="en-US-JennyNeural")
        assert mock_edge.Communicate.call_args[0][1] == "en-US-JennyNeural"

    async def test_subs_path_resolves_auto(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        comm = MagicMock()

        async def _stream():
            yield {"type": "audio", "data": b"\xff\xfb"}

        comm.stream = _stream
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=comm)
        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            await generate_audio_with_subs("Привет", "auto", out)
        assert mock_edge.Communicate.call_args[0][1] == "ru-RU-SvetlanaNeural"


class TestCli:
    def test_lang_auto_reaches_generator(self):
        with patch("sys.argv", ["TTS_ka", "გამარჯობა", "--lang", "auto", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        args, _ = mfa.call_args
        assert args[1] == "auto"

    def test_voice_with_lang_auto_is_not_a_conflict(self):
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "auto",
                                "--voice", "ka-GE-GiorgiNeural", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        args, kwargs = mfa.call_args
        assert args[1] == "ka"
        assert kwargs.get("voice") == "ka-GE-GiorgiNeural"


class TestLiveSwitchesVoicePerSentence:
    async def test_mixed_stream_uses_one_voice_per_sentence(self, temp_dir):
        from TTS_ka.live_stream import live_loop

        async def reader():
            for item in ("გამარჯობა მეგობარო. ", "Hello there. ", "Привет всем. ", None):
                yield item

        mock_edge = _mock_edge()
        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            await live_loop(lang="auto", input_reader=reader(), player=MagicMock(),
                            tmp_dir=temp_dir, max_concurrent=1)
        voices = [c[0][1] for c in mock_edge.Communicate.call_args_list]
        assert voices == ["ka-GE-EkaNeural", "en-GB-SoniaNeural", "ru-RU-SvetlanaNeural"]
