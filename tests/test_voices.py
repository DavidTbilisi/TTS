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
    """EdgeTTSGenerator must honor an explicit voice arg, else use VOICE_MAP."""

    async def _voice_used(self, tmp_path, voice):
        from TTS_ka.fast_audio import EdgeTTSGenerator
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            ok = await EdgeTTSGenerator().generate(
                "hello", "en", str(tmp_path / "a.mp3"), quiet=True, voice=voice
            )
        assert ok is True
        return mock_edge.Communicate.call_args[0][1]

    async def test_uses_explicit_voice(self, tmp_path):
        assert await self._voice_used(tmp_path, "en-US-JennyNeural") == "en-US-JennyNeural"

    async def test_falls_back_to_voice_map_when_voice_none(self, tmp_path):
        assert await self._voice_used(tmp_path, None) == "en-GB-SoniaNeural"
