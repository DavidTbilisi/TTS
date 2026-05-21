"""FEAT-1: voice catalog + --voice / --list-voices / --preview-voice."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka import voices


class TestCatalog:
    def test_all_voices_nonempty(self):
        assert len(voices.all_voices()) > 0

    def test_voices_for_lang_filters(self):
        for code in ("ka", "ru", "en"):
            results = voices.voices_for_lang(code)
            assert results, f"no voices for {code!r}"
            assert all(v.lang == code for v in results)

    def test_voices_for_unknown_lang_empty(self):
        assert voices.voices_for_lang("zz") == []

    def test_get_voice_known(self):
        v = voices.get_voice("en-US-JennyNeural")
        assert v is not None
        assert v.lang == "en"
        assert v.gender == "Female"

    def test_get_voice_unknown(self):
        assert voices.get_voice("zz-ZZ-NobodyNeural") is None

    def test_lang_for_voice(self):
        assert voices.lang_for_voice("ka-GE-EkaNeural") == "ka"
        assert voices.lang_for_voice("missing") is None

    def test_catalog_includes_existing_defaults(self):
        """The pre-existing three defaults must still be in the catalog."""
        defaults = ("ka-GE-EkaNeural", "ru-RU-SvetlanaNeural", "en-GB-SoniaNeural")
        for d in defaults:
            assert voices.get_voice(d) is not None, d

    def test_format_table_header(self):
        out = voices.format_table(voices.all_voices())
        assert "ID" in out and "Locale" in out and "Gender" in out

    def test_format_table_empty(self):
        out = voices.format_table([])
        assert "no voices" in out.lower()


class TestListVoicesCLI:
    def test_list_voices_prints_all(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--list-voices"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert "en-US-JennyNeural" in out
        assert "ka-GE-EkaNeural" in out

    def test_list_voices_with_lang_filters(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--list-voices", "--lang", "ka"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        assert "ka-GE-EkaNeural" in out
        # Russian voice must NOT appear in --lang ka filter
        assert "ru-RU-SvetlanaNeural" not in out

    def test_list_voices_no_lang_shows_all(self, capsys):
        """Without an explicit --lang, --list-voices shows every voice."""
        with patch("sys.argv", ["TTS_ka", "--list-voices"]):
            from TTS_ka.main import main
            main()
        out = capsys.readouterr().out
        # Every language appears
        assert "ka-GE-EkaNeural" in out
        assert "ru-RU-SvetlanaNeural" in out
        assert "en-GB-SoniaNeural" in out


class TestVoiceFlag:
    def test_voice_id_passed_to_generator(self):
        """--voice ID is threaded down to fast_generate_audio."""
        with patch("sys.argv", ["TTS_ka", "hi", "--voice", "en-US-JennyNeural", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        _, kwargs = mfa.call_args
        assert kwargs.get("voice") == "en-US-JennyNeural"

    def test_voice_lang_inferred_from_voice_locale(self):
        """--voice with no --lang updates args.lang to the voice's lang."""
        with patch("sys.argv", ["TTS_ka", "Привет", "--voice", "ru-RU-DmitryNeural", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        args, _ = mfa.call_args
        # second positional is language; should now be "ru"
        assert args[1] == "ru"

    def test_voice_lang_mismatch_errors(self, capsys):
        """--lang en + --voice ka-GE-* must error with exit 2."""
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en",
                                "--voice", "ka-GE-EkaNeural", "--no-play"]):
            with pytest.raises(SystemExit) as exc:
                from TTS_ka.main import main
                main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "ka" in err and "en" in err

    def test_unknown_voice_errors(self, capsys):
        with patch("sys.argv", ["TTS_ka", "hi", "--voice", "zz-ZZ-Nope", "--no-play"]):
            with pytest.raises(SystemExit) as exc:
                from TTS_ka.main import main
                main()
        assert exc.value.code == 2
        assert "unknown voice" in capsys.readouterr().err.lower()


class TestPreviewVoice:
    def test_preview_voice_generates_sample_and_plays(self, tmp_path):
        with patch("sys.argv", ["TTS_ka", "--preview-voice", "en-US-JennyNeural"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.play_audio") as mpa:
                from TTS_ka.main import main
                main()
        # generation called with the requested voice
        _, kwargs = mfa.call_args
        assert kwargs.get("voice") == "en-US-JennyNeural"
        mpa.assert_called_once()

    def test_preview_unknown_voice_errors(self, capsys):
        with patch("sys.argv", ["TTS_ka", "--preview-voice", "zz-ZZ-Nope"]):
            with pytest.raises(SystemExit) as exc:
                from TTS_ka.main import main
                main()
        assert exc.value.code == 2
        assert "unknown voice" in capsys.readouterr().err.lower()


class TestGeneratorVoiceOverride:
    """HttpAudioGenerator / EdgeTTSGenerator must honor an explicit voice arg."""

    async def test_http_generator_uses_explicit_voice(self, tmp_path):
        from TTS_ka.fast_audio import HttpAudioGenerator
        gen = HttpAudioGenerator()
        out = tmp_path / "a.mp3"

        captured = {}

        class FakeResponse:
            status_code = 200

            async def aiter_bytes(self, chunk_size=8192):
                if False:
                    yield b""
                yield b"FAKE"

        class FakeStreamCM:
            def __init__(self, captured, content):
                captured["content"] = content

            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, *exc):
                return False

        class FakeClient:
            def stream(self, method, url, headers=None, content=None):
                return FakeStreamCM(captured, content)

        with patch("TTS_ka.fast_audio.get_http_client", new=AsyncMock(return_value=FakeClient())):
            ok = await gen.generate("hello", "en", str(out),
                                    quiet=True, voice="en-US-JennyNeural")
        assert ok is True
        # SSML must reference the explicit voice, not the default en-GB-SoniaNeural
        assert b"en-US-JennyNeural" in captured["content"]
        assert b"en-GB-SoniaNeural" not in captured["content"]

    async def test_http_generator_falls_back_to_voice_map_when_voice_none(self, tmp_path):
        from TTS_ka.fast_audio import HttpAudioGenerator
        gen = HttpAudioGenerator()
        out = tmp_path / "a.mp3"
        captured = {}

        class FakeResponse:
            status_code = 200
            async def aiter_bytes(self, chunk_size=8192):
                if False:
                    yield b""
                yield b"FAKE"

        class FakeStreamCM:
            def __init__(self, captured, content):
                captured["content"] = content
            async def __aenter__(self):
                return FakeResponse()
            async def __aexit__(self, *exc):
                return False

        class FakeClient:
            def stream(self, method, url, headers=None, content=None):
                return FakeStreamCM(captured, content)

        with patch("TTS_ka.fast_audio.get_http_client",
                   new=AsyncMock(return_value=FakeClient())):
            await gen.generate("hello", "en", str(out), quiet=True)
        # No --voice given: falls back to VOICE_MAP['en']
        assert b"en-GB-SoniaNeural" in captured["content"]
