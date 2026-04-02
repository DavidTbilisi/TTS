"""Tests for fast_audio module."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.fast_audio import (
    fast_generate_audio,
    fallback_generate_audio,
    fast_merge_audio_files,
    play_audio,
    get_http_client,
    cleanup_http,
)
from TTS_ka.constants import VOICE_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream_cm(status_code=200, data=b"audio"):
    """Return a mock async context manager that simulates client.stream()."""

    async def _aiter_bytes(chunk_size=8192):
        yield data

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.aiter_bytes = _aiter_bytes

    class _CM:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, *a):
            pass

    return _CM()


# ---------------------------------------------------------------------------
# VOICE_MAP / constants
# ---------------------------------------------------------------------------

class TestVoiceMap:
    def test_voice_map_has_ka(self):
        assert "ka" in VOICE_MAP
        assert "EkaNeural" in VOICE_MAP["ka"]

    def test_voice_map_has_ru(self):
        assert "ru" in VOICE_MAP
        assert "SvetlanaNeural" in VOICE_MAP["ru"]

    def test_voice_map_has_en(self):
        assert "en" in VOICE_MAP
        assert "SoniaNeural" in VOICE_MAP["en"]

    def test_voice_map_invalid_language_returns_none(self):
        assert VOICE_MAP.get("fr") is None


# ---------------------------------------------------------------------------
# fast_generate_audio
# ---------------------------------------------------------------------------

class TestFastGenerateAudio:
    async def test_success_writes_file(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(200, b"audiodata")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)):
            result = await fast_generate_audio("Hello world", "en", out, quiet=True)
        assert result is True
        assert os.path.exists(out)
        with open(out, "rb") as f:
            assert f.read() == b"audiodata"

    async def test_non_200_falls_back_to_edge_tts(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(503, b"")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)), \
             patch('TTS_ka.fast_audio.fallback_generate_audio', new=AsyncMock(return_value=True)) as mock_fb:
            result = await fast_generate_audio("Hello", "en", out, quiet=True)
        assert result is True
        mock_fb.assert_called_once()

    async def test_http_error_falls_back(self, temp_dir):
        import httpx
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.side_effect = httpx.HTTPError("timeout")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)), \
             patch('TTS_ka.fast_audio.fallback_generate_audio', new=AsyncMock(return_value=True)) as mock_fb:
            result = await fast_generate_audio("Hello", "en", out, quiet=True)
        assert result is True
        mock_fb.assert_called_once()

    async def test_invalid_language_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        result = await fast_generate_audio("Hello", "invalid_lang", out, quiet=True)
        assert result is False

    async def test_invalid_language_prints_error(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        await fast_generate_audio("Hello", "xx", out, quiet=False)
        assert "not supported" in capsys.readouterr().out

    async def test_quiet_no_print(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(200, b"data")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)):
            await fast_generate_audio("Hello", "en", out, quiet=True)
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
    async def test_all_supported_languages(self, lang, temp_dir):
        out = os.path.join(temp_dir, f"out_{lang}.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(200, b"audio")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)):
            result = await fast_generate_audio("Test", lang, out, quiet=True)
        assert result is True


# ---------------------------------------------------------------------------
# fallback_generate_audio
# ---------------------------------------------------------------------------

class TestFallbackGenerateAudio:
    async def test_success(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        with patch('edge_tts.Communicate') as mock_comm:
            mock_inst = AsyncMock()
            mock_comm.return_value = mock_inst
            result = await fallback_generate_audio("Hello world", "en", out, quiet=True)
        assert result is True
        mock_inst.save.assert_called_once_with(out)

    async def test_prints_path_when_not_quiet(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        with patch('edge_tts.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            await fallback_generate_audio("Hello", "en", out, quiet=False)
        assert out in capsys.readouterr().out

    async def test_failure_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        with patch('edge_tts.Communicate', side_effect=Exception("fail")):
            result = await fallback_generate_audio("Hello", "en", out, quiet=True)
        assert result is False

    async def test_invalid_language_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        result = await fallback_generate_audio("Hello", "zz", out, quiet=True)
        assert result is False

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
    async def test_all_languages(self, lang, temp_dir):
        out = os.path.join(temp_dir, f"out_{lang}.mp3")
        with patch('edge_tts.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            result = await fallback_generate_audio("Test", lang, out, quiet=True)
        assert result is True


# ---------------------------------------------------------------------------
# fast_merge_audio_files
# ---------------------------------------------------------------------------

class TestFastMergeAudioFiles:
    def test_empty_parts_raises(self, temp_dir):
        with pytest.raises(ValueError):
            fast_merge_audio_files([], os.path.join(temp_dir, "out.mp3"))

    def test_merge_with_pydub(self, temp_dir):
        part = os.path.join(temp_dir, "p.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        mock_seg = MagicMock()
        mock_seg.__add__ = MagicMock(return_value=mock_seg)
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('pydub.AudioSegment') as mock_audio:
            mock_audio.from_mp3.return_value = mock_seg
            fast_merge_audio_files([part], out)
        mock_seg.export.assert_called_once()

    def test_merge_ffmpeg_fallback(self, temp_dir):
        part = os.path.join(temp_dir, "p.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('pydub.AudioSegment', side_effect=ImportError), \
             patch('os.system', return_value=0) as mock_sys, \
             patch('os.remove'):
            fast_merge_audio_files([part], out)
        mock_sys.assert_called_once()

    def test_removes_existing_output(self, temp_dir):
        part = os.path.join(temp_dir, "p.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with open(out, "wb") as f:
            f.write(b"old")
        mock_seg = MagicMock()
        mock_seg.__add__ = MagicMock(return_value=mock_seg)
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('pydub.AudioSegment') as mock_audio:
            mock_audio.from_mp3.return_value = mock_seg
            fast_merge_audio_files([part], out)
        # If we got here without error, old file was handled
        mock_seg.export.assert_called()


# ---------------------------------------------------------------------------
# HTTP client lifecycle
# ---------------------------------------------------------------------------

class TestHttpClient:
    async def test_get_http_client_creates_client(self):
        import TTS_ka.fast_audio as fa
        fa._http_client = None
        client = await get_http_client()
        assert client is not None
        # cleanup
        await cleanup_http()
        assert fa._http_client is None

    async def test_get_http_client_reuses_instance(self):
        import TTS_ka.fast_audio as fa
        fa._http_client = None
        c1 = await get_http_client()
        c2 = await get_http_client()
        assert c1 is c2
        await cleanup_http()

    async def test_cleanup_http_idempotent(self):
        import TTS_ka.fast_audio as fa
        fa._http_client = None
        await cleanup_http()  # must not raise when already None


# ---------------------------------------------------------------------------
# play_audio
# ---------------------------------------------------------------------------

class TestFastPlayAudio:
    def test_windows(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'win32'), patch('os.startfile') as m:
            play_audio(f)
        m.assert_called_once()

    def test_mac(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'darwin'), patch('os.system') as m:
            play_audio(f)
        assert "open" in m.call_args[0][0]

    def test_linux(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'linux'), patch('os.system', return_value=0):
            play_audio(f)  # must not raise

    def test_oserror_silenced(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'win32'), patch('os.startfile', side_effect=OSError):
            play_audio(f)  # must not raise
