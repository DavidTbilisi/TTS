"""FEAT-2: speech rate / pitch / volume via SSML prosody."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka import prosody


class TestParseValues:
    def test_rate_signed_percent(self):
        assert prosody.parse_rate("+30%") == "+30%"
        assert prosody.parse_rate("-20%") == "-20%"

    def test_rate_default_when_none(self):
        assert prosody.parse_rate(None) == "+0%"

    def test_rate_zero(self):
        assert prosody.parse_rate("+0%") == "+0%"

    def test_rate_clamp_above_max(self, capsys):
        result = prosody.parse_rate("+500%")
        assert result == f"+{prosody.RATE_MAX}%"
        assert "clamped" in capsys.readouterr().err.lower()

    def test_rate_invalid_format(self, capsys):
        with pytest.raises(SystemExit) as exc:
            prosody.parse_rate("banana")
        assert exc.value.code == 2
        assert "invalid" in capsys.readouterr().err.lower()

    def test_rate_missing_sign(self):
        with pytest.raises(SystemExit):
            prosody.parse_rate("30%")  # must be signed

    def test_pitch_hz(self):
        assert prosody.parse_pitch("+5Hz") == "+5Hz"
        assert prosody.parse_pitch("-10Hz") == "-10Hz"

    def test_pitch_percent_converted_to_hz(self):
        # +10% gets mapped onto +10Hz (rough approximation)
        assert prosody.parse_pitch("+10%") == "+10Hz"

    def test_pitch_default_when_none(self):
        assert prosody.parse_pitch(None) == "+0Hz"

    def test_pitch_invalid(self):
        with pytest.raises(SystemExit):
            prosody.parse_pitch("badpitch")

    def test_pitch_clamps(self, capsys):
        result = prosody.parse_pitch("+9999Hz")
        assert result == f"+{prosody.PITCH_HZ_MAX}Hz"
        assert "clamped" in capsys.readouterr().err.lower()

    def test_volume_signed_percent(self):
        assert prosody.parse_volume("+10%") == "+10%"
        assert prosody.parse_volume("-25%") == "-25%"

    def test_volume_default_when_none(self):
        assert prosody.parse_volume(None) == "+0%"

    def test_volume_clamps(self, capsys):
        result = prosody.parse_volume("-500%")
        assert result == f"{prosody.VOLUME_MIN:+d}%"
        assert "clamped" in capsys.readouterr().err.lower()


class TestBuildOpts:
    def test_all_none_yields_default(self):
        opts = prosody.build_opts(None, None, None)
        assert opts.is_default()

    def test_any_value_makes_non_default(self):
        opts = prosody.build_opts("+30%", None, None)
        assert not opts.is_default()
        assert opts.rate == "+30%"
        assert opts.pitch == "+0Hz"


class TestSSMLOutput:
    """Generators wrap the text in <prosody> when opts are non-default."""

    async def test_no_prosody_no_prosody_tag(self, tmp_path):
        """Default opts must NOT introduce a <prosody> tag (no perf regression)."""
        from TTS_ka.fast_audio import HttpAudioGenerator
        captured = {}

        class FakeResp:
            status_code = 200
            async def aiter_bytes(self, chunk_size=8192):
                if False:
                    yield b""
                yield b"X"

        class FakeCM:
            def __init__(self, captured, content):
                captured["content"] = content
            async def __aenter__(self):
                return FakeResp()
            async def __aexit__(self, *exc):
                return False

        class FakeClient:
            def stream(self, method, url, headers=None, content=None):
                return FakeCM(captured, content)

        with patch("TTS_ka.fast_audio.get_http_client",
                   new=AsyncMock(return_value=FakeClient())):
            await HttpAudioGenerator().generate(
                "hi", "en", str(tmp_path / "a.mp3"),
                quiet=True, prosody=prosody.ProsodyOpts()
            )
        assert b"<prosody" not in captured["content"]

    async def test_prosody_attrs_appear_in_ssml(self, tmp_path):
        from TTS_ka.fast_audio import HttpAudioGenerator
        captured = {}

        class FakeResp:
            status_code = 200
            async def aiter_bytes(self, chunk_size=8192):
                if False:
                    yield b""
                yield b"X"

        class FakeCM:
            def __init__(self, captured, content):
                captured["content"] = content
            async def __aenter__(self):
                return FakeResp()
            async def __aexit__(self, *exc):
                return False

        class FakeClient:
            def stream(self, method, url, headers=None, content=None):
                return FakeCM(captured, content)

        opts = prosody.build_opts("+30%", "-5Hz", "+10%")
        with patch("TTS_ka.fast_audio.get_http_client",
                   new=AsyncMock(return_value=FakeClient())):
            await HttpAudioGenerator().generate(
                "hello", "en", str(tmp_path / "a.mp3"),
                quiet=True, prosody=opts
            )
        body = captured["content"]
        assert b"<prosody" in body
        assert b"rate='+30%'" in body
        assert b"pitch='-5Hz'" in body
        assert b"volume='+10%'" in body


class TestCLI:
    def test_cli_flags_build_prosody(self):
        # Negative-value flags require =-form so argparse doesn't mistake them
        # for new flags (standard Unix CLI behavior).
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en",
                                "--rate=+30%", "--pitch=-2Hz",
                                "--volume=+5%", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        _, kwargs = mfa.call_args
        opts = kwargs.get("prosody")
        assert opts is not None
        assert opts.rate == "+30%"
        assert opts.pitch == "-2Hz"
        assert opts.volume == "+5%"

    def test_invalid_rate_exits_before_http(self, capsys):
        with patch("sys.argv", ["TTS_ka", "hi", "--lang", "en",
                                "--rate", "garbage", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa:
                with pytest.raises(SystemExit) as exc:
                    from TTS_ka.main import main
                    main()
        assert exc.value.code == 2
        mfa.assert_not_called()  # never reached the network
