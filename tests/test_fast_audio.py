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
    PydubMerger,
    EdgeTTSGenerator,
)
from TTS_ka.constants import VOICE_MAP, SSML_LANG_MAP


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

    def test_voice_map_has_ka_male(self):
        assert "ka-m" in VOICE_MAP
        assert "GiorgiNeural" in VOICE_MAP["ka-m"]

    def test_voice_map_has_ru(self):
        assert "ru" in VOICE_MAP
        assert "SvetlanaNeural" in VOICE_MAP["ru"]

    def test_voice_map_has_en(self):
        assert "en" in VOICE_MAP
        assert "SoniaNeural" in VOICE_MAP["en"]

    def test_voice_map_invalid_language_returns_none(self):
        assert VOICE_MAP.get("fr") is None

    def test_ssml_lang_georgian_locale(self):
        assert SSML_LANG_MAP["ka"] == "ka-GE"
        assert SSML_LANG_MAP["ka-m"] == "ka-GE"


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
             patch.object(EdgeTTSGenerator, 'generate', new_callable=AsyncMock, return_value=True) as mock_fb:
            result = await fast_generate_audio("Hello", "en", out, quiet=True)
        assert result is True
        mock_fb.assert_called_once()

    async def test_tts_ka_skip_http_skips_bing_request(self, temp_dir, monkeypatch):
        monkeypatch.setenv("TTS_KA_SKIP_HTTP", "1")
        out = os.path.join(temp_dir, "out.mp3")
        with patch("TTS_ka.fast_audio.get_http_client", new=AsyncMock()) as mock_http, \
             patch.object(
                 EdgeTTSGenerator, "generate", new_callable=AsyncMock, return_value=True
             ) as mock_edge:
            await fast_generate_audio("Hi", "en", out, quiet=True)
        mock_http.assert_not_called()
        mock_edge.assert_called_once()

    async def test_http_error_falls_back(self, temp_dir):
        import httpx
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.side_effect = httpx.HTTPError("timeout")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)), \
             patch.object(EdgeTTSGenerator, 'generate', new_callable=AsyncMock, return_value=True) as mock_fb:
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

    @pytest.mark.parametrize("lang", ["ka", "ka-m", "ru", "en"])
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
        mock_comm_inst = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=mock_comm_inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("Hello world", "en", out, quiet=True)
        assert result is True
        mock_comm_inst.save.assert_called_once_with(out)

    async def test_prints_path_when_not_quiet(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            await fallback_generate_audio("Hello", "en", out, quiet=False)
        assert capsys.readouterr().out != ""

    async def test_failure_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(side_effect=Exception("fail"))
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await fallback_generate_audio("Hello", "en", out, quiet=True)
        assert result is False

    async def test_invalid_language_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        result = await fallback_generate_audio("Hello", "zz", out, quiet=True)
        assert result is False

    @pytest.mark.parametrize("lang", ["ka", "ka-m", "ru", "en"])
    async def test_all_languages(self, lang, temp_dir):
        out = os.path.join(temp_dir, f"out_{lang}.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
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
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        out = os.path.join(temp_dir, "out.mp3")
        for p in parts:
            with open(p, "wb") as f:
                f.write(b"fake")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', True), \
             patch.object(PydubMerger, 'merge') as mock_merge:
            fast_merge_audio_files(parts, out)
        mock_merge.assert_called_once_with(parts, out)

    def test_merge_ffmpeg_fallback(self, temp_dir):
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        out = os.path.join(temp_dir, "out.mp3")
        for p in parts:
            with open(p, "wb") as f:
                f.write(b"fake")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0) as mock_sys:
            fast_merge_audio_files(parts, out)
        mock_sys.assert_called_once()

    def test_removes_existing_output(self, temp_dir):
        part = os.path.join(temp_dir, "p.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with open(out, "wb") as f:
            f.write(b"old")
        # Single-part merge copies src to dst, overwriting old content
        fast_merge_audio_files([part], out)
        assert os.path.exists(out)


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
        with patch('sys.platform', 'win32'), patch('os.startfile', create=True) as m:
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
        with patch('sys.platform', 'win32'), patch('os.startfile', side_effect=OSError, create=True):
            play_audio(f)  # must not raise


# ---------------------------------------------------------------------------
# MergerFactory
# ---------------------------------------------------------------------------

class TestMergerFactory:
    def test_creates_ffmpeg_when_no_optional_deps(self):
        from TTS_ka.fast_audio import MergerFactory, FFmpegMerger
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False):
            merger = MergerFactory.create()
        assert isinstance(merger, FFmpegMerger)

    def test_creates_pydub_when_available(self):
        from TTS_ka.fast_audio import MergerFactory, PydubMerger
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', True):
            merger = MergerFactory.create()
        assert isinstance(merger, PydubMerger)

    def test_creates_soundfile_when_available(self):
        from TTS_ka.fast_audio import MergerFactory, SoundFileMerger
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', True):
            merger = MergerFactory.create()
        assert isinstance(merger, SoundFileMerger)


# ---------------------------------------------------------------------------
# FFmpegMerger fallback and all-mergers-fail path
# ---------------------------------------------------------------------------

class TestFFmpegMergerFallback:
    def test_nonzero_rc_copies_first_part(self, temp_dir):
        """When ffmpeg fails (non-zero rc), first part is copied to output."""
        from TTS_ka.fast_audio import FFmpegMerger
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        for p in parts:
            with open(p, "wb") as f:
                f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('os.system', return_value=1), \
             patch('os.remove'):
            FFmpegMerger().merge(parts, out)
        assert os.path.exists(out)

    def test_all_mergers_fail_raises(self, temp_dir):
        """When all merger strategies fail, RuntimeError is raised."""
        from TTS_ka.fast_audio import fast_merge_audio_files, SoundFileMerger, FFmpegMerger
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        for p in parts:
            with open(p, "wb") as f:
                f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', True), \
             patch.object(SoundFileMerger, 'merge', side_effect=Exception("sf fail")), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch.object(FFmpegMerger, 'merge', side_effect=Exception("ffmpeg fail")):
            with pytest.raises(RuntimeError, match="All merge strategies failed"):
                fast_merge_audio_files(parts, out)


# ---------------------------------------------------------------------------
# fast_generate_audio verbose (quiet=False) success path
# ---------------------------------------------------------------------------

class TestFastGenerateAudioVerbose:
    async def test_success_quiet_false_prints(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(200, b"data")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)):
            result = await fast_generate_audio("Hello", "en", out, quiet=False)
        assert result is True
        assert capsys.readouterr().out != ""


# ---------------------------------------------------------------------------
# HttpAudioGenerator direct — cover quiet=False branches
# ---------------------------------------------------------------------------

class TestHttpAudioGeneratorDirect:
    async def test_invalid_lang_quiet_false_prints(self, temp_dir, capsys):
        from TTS_ka.fast_audio import HttpAudioGenerator
        out = os.path.join(temp_dir, "out.mp3")
        result = await HttpAudioGenerator().generate("Hello", "xx", out, quiet=False)
        assert result is False
        assert "not supported" in capsys.readouterr().out

    async def test_success_quiet_false_prints_in_generator(self, temp_dir, capsys):
        from TTS_ka.fast_audio import HttpAudioGenerator
        out = os.path.join(temp_dir, "out.mp3")
        mock_client = MagicMock()
        mock_client.stream.return_value = _make_stream_cm(200, b"audiodata")
        with patch('TTS_ka.fast_audio.get_http_client', new=AsyncMock(return_value=mock_client)):
            result = await HttpAudioGenerator().generate("Hello", "en", out, quiet=False)
        assert result is True
        assert capsys.readouterr().out != ""


# ---------------------------------------------------------------------------
# FFmpegMerger edge cases
# ---------------------------------------------------------------------------

class TestFFmpegMergerEdgeCases:
    def test_nonexistent_first_part_raises(self, temp_dir):
        """When ffmpeg fails and first part doesn't exist, raise RuntimeError."""
        from TTS_ka.fast_audio import FFmpegMerger
        parts = ["/nonexistent/a.mp3", "/nonexistent/b.mp3"]
        out = os.path.join(temp_dir, "out.mp3")
        with patch('os.system', return_value=1), \
             patch('os.remove'):
            with pytest.raises(RuntimeError, match="no valid parts"):
                FFmpegMerger().merge(parts, out)

    def test_listfile_removal_oserror_silenced(self, temp_dir):
        """OSError during listfile cleanup is silenced."""
        from TTS_ka.fast_audio import FFmpegMerger
        parts = [os.path.join(temp_dir, "p.mp3")]
        with open(parts[0], "wb") as f:
            f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('os.system', return_value=0), \
             patch('os.remove', side_effect=OSError("locked")):
            # Must not raise — the OSError in finally block is caught
            FFmpegMerger().merge(parts, out)
