"""Tests for fast_audio module."""

import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.fast_audio import (
    fast_generate_audio,
    fast_merge_audio_files,
    play_audio,
    PydubMerger,
    EdgeTTSGenerator,
)
from TTS_ka.constants import VOICE_MAP


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



# ---------------------------------------------------------------------------
# fast_generate_audio
# ---------------------------------------------------------------------------

class TestFastGenerateAudio:
    async def test_delegates_to_edge_tts_with_voice_and_prosody(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        prosody = MagicMock()
        with patch.object(EdgeTTSGenerator, 'generate', new_callable=AsyncMock,
                          return_value=True) as mock_edge:
            result = await fast_generate_audio("Hello", "en", out, quiet=True,
                                               voice="en-US-JennyNeural", prosody=prosody)
        assert result is True
        mock_edge.assert_awaited_once_with("Hello", "en", out, True,
                                           voice="en-US-JennyNeural", prosody=prosody)

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
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            assert await fast_generate_audio("Hello", "en", out, quiet=True) is True
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# EdgeTTSGenerator
# ---------------------------------------------------------------------------

class TestEdgeTTSGenerator:
    async def test_success(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_comm_inst = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=mock_comm_inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await EdgeTTSGenerator().generate("Hello world", "en", out, quiet=True)
        assert result is True
        mock_comm_inst.save.assert_called_once_with(out)

    async def test_prints_path_when_not_quiet(self, temp_dir, capsys):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            await EdgeTTSGenerator().generate("Hello", "en", out, quiet=False)
        assert capsys.readouterr().out != ""

    async def test_failure_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(side_effect=Exception("fail"))
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await EdgeTTSGenerator().generate("Hello", "en", out, quiet=True)
        assert result is False

    async def test_invalid_language_returns_false(self, temp_dir):
        out = os.path.join(temp_dir, "out.mp3")
        result = await EdgeTTSGenerator().generate("Hello", "zz", out, quiet=True)
        assert result is False

    @pytest.mark.parametrize("lang", ["ka", "ka-m", "ru", "en"])
    async def test_all_languages(self, lang, temp_dir):
        out = os.path.join(temp_dir, f"out_{lang}.mp3")
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=AsyncMock())
        with patch.dict('sys.modules', {'edge_tts': mock_edge}):
            result = await EdgeTTSGenerator().generate("Test", lang, out, quiet=True)
        assert result is True
        assert mock_edge.Communicate.call_args[0][1] == VOICE_MAP[lang]


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
             patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=0)) as mock_run:
            fast_merge_audio_files(parts, out)
        mock_run.assert_called_once()
        # argv list-form, no shell
        argv = mock_run.call_args.args[0]
        assert isinstance(argv, list) and argv[0] == "ffmpeg"

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
# play_audio
# ---------------------------------------------------------------------------

class TestFastPlayAudio:
    def test_windows(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'win32'), patch('os.startfile', create=True) as m:
            assert play_audio(f) is True
        m.assert_called_once()

    def test_mac(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'darwin'), \
             patch('TTS_ka.fast_audio.subprocess.Popen') as m:
            play_audio(f)
        m.assert_called_once()
        argv = m.call_args.args[0]
        assert argv[0] == "open"

    def test_linux(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'linux'), \
             patch('TTS_ka.fast_audio.shutil.which', return_value='/usr/bin/mpv'), \
             patch('TTS_ka.fast_audio.subprocess.Popen'):
            assert play_audio(f) is True  # must not raise

    def test_oserror_silenced(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'win32'), patch('os.startfile', side_effect=OSError, create=True):
            assert play_audio(f) is False  # must not raise; reports failure

    def test_linux_no_player_returns_false(self, temp_dir):
        f = os.path.join(temp_dir, "t.mp3")
        with open(f, "wb") as fp:
            fp.write(b"x")
        with patch('sys.platform', 'linux'), \
             patch('TTS_ka.fast_audio.shutil.which', return_value=None):
            assert play_audio(f) is False


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
        with patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=1)):
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
# FFmpegMerger edge cases
# ---------------------------------------------------------------------------

class TestFFmpegMergerEdgeCases:
    def test_nonexistent_first_part_raises(self, temp_dir):
        """When ffmpeg fails and first part doesn't exist, raise RuntimeError."""
        from TTS_ka.fast_audio import FFmpegMerger
        parts = ["/nonexistent/a.mp3", "/nonexistent/b.mp3"]
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=1)):
            with pytest.raises(RuntimeError, match="no valid parts"):
                FFmpegMerger().merge(parts, out)

    def test_listfile_removal_oserror_silenced(self, temp_dir):
        """OSError during listfile cleanup is silenced."""
        from TTS_ka.fast_audio import FFmpegMerger
        parts = [os.path.join(temp_dir, "p.mp3")]
        with open(parts[0], "wb") as f:
            f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=0)), \
             patch('os.remove', side_effect=OSError("locked")) as mock_remove:
            # Must not raise — the OSError in finally block is caught
            FFmpegMerger().merge(parts, out)
        listfile = mock_remove.call_args[0][0]
        os.remove(listfile)  # the real cleanup the mock blocked

    def test_listfile_is_temp_file_and_removed(self, temp_dir):
        """The concat list lives in the temp dir (not CWD) and is deleted afterwards."""
        import tempfile
        from TTS_ka.fast_audio import FFmpegMerger
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        for part in parts:
            with open(part, "wb") as f:
                f.write(b"dummy")
        seen = {}

        def fake_run(argv, **kw):
            listfile = argv[argv.index("-i") + 1]
            seen["dir"] = os.path.dirname(listfile)
            with open(listfile, encoding="utf-8") as f:
                seen["body"] = f.read()
            seen["path"] = listfile
            return MagicMock(returncode=0)

        with patch('TTS_ka.fast_audio.subprocess.run', side_effect=fake_run):
            FFmpegMerger().merge(parts, os.path.join(temp_dir, "out.mp3"))
        assert seen["dir"] == tempfile.gettempdir()
        assert seen["body"].count("file '") == 2
        assert not os.path.exists(seen["path"])


# ---------------------------------------------------------------------------
# EdgeTTSGenerator transient-error retry/backoff
# ---------------------------------------------------------------------------

class TestEdgeTTSRetry:
    async def test_transient_retries_then_succeeds(self, temp_dir):
        from TTS_ka.fast_audio import EdgeTTSGenerator
        out = os.path.join(temp_dir, "o.mp3")
        bad = AsyncMock()
        bad.save = AsyncMock(side_effect=Exception("403 Forbidden"))
        good = AsyncMock()
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(side_effect=[bad, good])
        with patch.dict('sys.modules', {'edge_tts': mock_edge}), \
             patch('TTS_ka.fast_audio.asyncio.sleep', new=AsyncMock()) as msleep:
            result = await EdgeTTSGenerator().generate("hi", "en", out, quiet=True)
        assert result is True
        assert mock_edge.Communicate.call_count == 2   # retried once
        msleep.assert_awaited_once()                    # backed off between tries

    async def test_transient_all_fail_prints_hint(self, temp_dir, capsys):
        from TTS_ka.fast_audio import EdgeTTSGenerator
        out = os.path.join(temp_dir, "o.mp3")
        inst = AsyncMock()
        inst.save = AsyncMock(side_effect=Exception("429 Too Many Requests"))
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}), \
             patch('TTS_ka.fast_audio.asyncio.sleep', new=AsyncMock()) as msleep:
            result = await EdgeTTSGenerator().generate("hi", "en", out, quiet=False)
        assert result is False
        assert mock_edge.Communicate.call_count == 3   # exhausted all retries
        assert msleep.await_count == 2                 # slept between the 3 attempts
        assert "403" in capsys.readouterr().out        # actionable hint shown

    async def test_non_transient_breaks_immediately(self, temp_dir):
        from TTS_ka.fast_audio import EdgeTTSGenerator
        out = os.path.join(temp_dir, "o.mp3")
        inst = AsyncMock()
        inst.save = AsyncMock(side_effect=Exception("disk full"))
        mock_edge = MagicMock()
        mock_edge.Communicate = MagicMock(return_value=inst)
        with patch.dict('sys.modules', {'edge_tts': mock_edge}), \
             patch('TTS_ka.fast_audio.asyncio.sleep', new=AsyncMock()) as msleep:
            result = await EdgeTTSGenerator().generate("hi", "en", out, quiet=True)
        assert result is False
        assert mock_edge.Communicate.call_count == 1   # no retry on non-transient
        msleep.assert_not_awaited()
