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

class TestGenerationFailureHelpers:
    def test_message_trims_url_and_adds_403_hint(self):
        from TTS_ka.fast_audio import generation_failed
        err = Exception("403, message='Invalid response status', url='wss://x?TrustedClientToken=SECRET'")
        msg = str(generation_failed("Audio generation failed", err))
        assert msg.startswith("Audio generation failed: 403, message='Invalid response status'")
        assert "SECRET" not in msg
        assert "pip install -U edge-tts" in msg

    async def test_unsupported_language_becomes_reason(self, temp_dir):
        from TTS_ka.fast_audio import generation_failed
        assert await EdgeTTSGenerator().generate("hi", "xx", os.path.join(temp_dir, "o.mp3"),
                                                 quiet=True) is False
        assert "language 'xx' not supported" in str(generation_failed("failed"))

    def test_discard_empty_output_only_removes_empty_files(self, temp_dir):
        from TTS_ka.fast_audio import discard_empty_output
        empty, full = os.path.join(temp_dir, "e.mp3"), os.path.join(temp_dir, "f.mp3")
        open(empty, "wb").close()
        with open(full, "wb") as f:
            f.write(b"audio")
        discard_empty_output(empty)
        discard_empty_output(full)
        discard_empty_output(os.path.join(temp_dir, "missing.mp3"))  # no error
        assert not os.path.exists(empty)
        assert os.path.exists(full)


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
    def test_nonzero_rc_raises_instead_of_truncating(self, temp_dir):
        """A failed ffmpeg run raises; it never ships just the first part."""
        from TTS_ka.fast_audio import FFmpegMerger, MergeFailed
        parts = [os.path.join(temp_dir, f"p{i}.mp3") for i in range(2)]
        for p in parts:
            with open(p, "wb") as f:
                f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=1)):
            with pytest.raises(MergeFailed, match="exited with code 1"):
                FFmpegMerger().merge(parts, out)
        assert not os.path.exists(out)

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
    def test_missing_part_raises_before_running_ffmpeg(self, temp_dir):
        """A missing part is an error, not something to silently skip."""
        from TTS_ka.fast_audio import FFmpegMerger, MergeFailed
        part = os.path.join(temp_dir, "a.mp3")
        with open(part, "wb") as f:
            f.write(b"dummy")
        out = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.fast_audio.subprocess.run') as mrun:
            with pytest.raises(MergeFailed, match="missing or empty part /nonexistent/b.mp3"):
                FFmpegMerger().merge([part, "/nonexistent/b.mp3"], out)
        mrun.assert_not_called()

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


# ---------------------------------------------------------------------------
# Lossless MP3 concatenation and strict merging
# ---------------------------------------------------------------------------

# One MPEG-2 Layer III frame header (what edge-tts emits) plus filler bytes.
_FRAME = b"\xff\xf3\x64\xc4" + b"\x00" * 12


def _id3(payload: bytes = b"TIT2tag") -> bytes:
    size = len(payload)
    syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x04\x00\x00" + syncsafe + payload


def _write(path, data: bytes) -> str:
    with open(path, "wb") as f:
        f.write(data)
    return str(path)


class TestConcatMp3Merger:
    def test_mp3_parts_are_byte_concatenated(self, tmp_path):
        parts = [_write(tmp_path / f"p{i}.mp3", _FRAME + bytes([i])) for i in range(3)]
        out = tmp_path / "out.mp3"
        with patch('TTS_ka.fast_audio.subprocess.run') as mrun:
            fast_merge_audio_files(parts, str(out))
        assert out.read_bytes() == b"".join(_FRAME + bytes([i]) for i in range(3))
        mrun.assert_not_called()  # no ffmpeg, no re-encode

    def test_id3_kept_on_first_part_only(self, tmp_path):
        first = _write(tmp_path / "a.mp3", _id3() + _FRAME)
        second = _write(tmp_path / "b.mp3", _id3(b"TIT2other") + _FRAME + b"x")
        out = tmp_path / "out.mp3"
        fast_merge_audio_files([first, second], str(out))
        assert out.read_bytes() == _id3() + _FRAME + _FRAME + b"x"

    @pytest.mark.parametrize("bad", ["missing", "empty"])
    def test_missing_or_empty_part_raises_and_keeps_old_output(self, tmp_path, bad):
        from TTS_ka.fast_audio import MergeFailed
        good = _write(tmp_path / "a.mp3", _FRAME)
        bad_path = str(tmp_path / "b.mp3")
        if bad == "empty":
            _write(bad_path, b"")
        out = tmp_path / "out.mp3"
        out.write_bytes(b"previous run")
        with pytest.raises(MergeFailed, match="missing or empty part"):
            fast_merge_audio_files([good, bad_path], str(out))
        assert out.read_bytes() == b"previous run"
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".tts_ka_merge_")] == []

    def test_output_cannot_be_a_part(self, tmp_path):
        part = _write(tmp_path / "out.mp3", _FRAME)
        with pytest.raises(ValueError, match="also one of the parts"):
            fast_merge_audio_files([part, _write(tmp_path / "b.mp3", _FRAME)], part)

    def test_non_mp3_output_uses_reencoding_chain(self, tmp_path):
        parts = [_write(tmp_path / f"p{i}.mp3", _FRAME) for i in range(2)]
        out = str(tmp_path / "out.wav")
        with patch('TTS_ka.fast_audio.HAS_SOUNDFILE', False), \
             patch('TTS_ka.fast_audio.HAS_PYDUB', False), \
             patch('TTS_ka.fast_audio.subprocess.run',
                   return_value=MagicMock(returncode=0)) as mrun:
            fast_merge_audio_files(parts, out)
        argv = mrun.call_args.args[0]
        assert "copy" not in argv  # a .wav needs re-encoding, not an MP3 stream copy
        assert argv[-1] == out


class TestStrictLegacyMergers:
    def test_soundfile_unreadable_part_raises(self, tmp_path):
        from TTS_ka import fast_audio
        parts = [_write(tmp_path / f"p{i}.mp3", b"x") for i in range(2)]
        fake_sf = MagicMock()
        fake_sf.read.side_effect = [([0.0], 24000), RuntimeError("bad frame")]
        with patch.object(fast_audio, "sf", fake_sf, create=True):
            with pytest.raises(fast_audio.MergeFailed, match="cannot read .*p1.mp3"):
                fast_audio.SoundFileMerger().merge(parts, str(tmp_path / "out.wav"))
        fake_sf.write.assert_not_called()

    def test_pydub_missing_part_raises(self, tmp_path):
        from TTS_ka import fast_audio
        first = _write(tmp_path / "a.mp3", b"x")
        with patch.object(fast_audio, "AudioSegment", MagicMock(), create=True):
            with pytest.raises(fast_audio.MergeFailed, match="missing or empty part"):
                PydubMerger().merge([first, str(tmp_path / "gone.mp3")], str(tmp_path / "o.wav"))


# ---------------------------------------------------------------------------
# generate_audio_with_subs: word boundaries, retry, failure contract
# ---------------------------------------------------------------------------

class _RecordingCommunicate:
    """Fake edge_tts.Communicate that records kwargs and streams scripted chunks."""

    calls: list = []
    script: list = []

    def __init__(self, *args, **kwargs):
        type(self).calls.append(kwargs)

    async def stream(self):
        step = type(self).script.pop(0)
        if isinstance(step, Exception):
            yield {"type": "audio", "data": b"partial"}
            raise step
        for chunk in step:
            yield chunk


class TestGenerateAudioWithSubsContract:
    @pytest.fixture
    def fake_edge(self):
        _RecordingCommunicate.calls = []
        _RecordingCommunicate.script = []
        with patch.dict('sys.modules', {'edge_tts': MagicMock(Communicate=_RecordingCommunicate)}), \
             patch('TTS_ka.fast_audio.asyncio.sleep', new=AsyncMock()):
            yield _RecordingCommunicate

    async def test_requests_word_boundaries(self, tmp_path, fake_edge):
        """edge-tts >= 7 defaults to SentenceBoundary, which yields no word events."""
        from TTS_ka.fast_audio import generate_audio_with_subs
        fake_edge.script = [[
            {"type": "audio", "data": b"A"},
            {"type": "WordBoundary", "offset": 1_000_000, "duration": 2_000_000, "text": "hi"},
        ]]
        events = await generate_audio_with_subs("hi", "en", str(tmp_path / "o.mp3"))
        assert fake_edge.calls[0]["boundary"] == "WordBoundary"
        assert [(e.text, e.start_ms, e.duration_ms) for e in events] == [("hi", 100, 200)]

    async def test_transient_error_retried_without_duplicate_events(self, tmp_path, fake_edge):
        from TTS_ka.fast_audio import generate_audio_with_subs
        word = {"type": "WordBoundary", "offset": 0, "duration": 10_000, "text": "hi"}
        fake_edge.script = [Exception("429 Too Many Requests"),
                            [{"type": "audio", "data": b"A"}, word]]
        out = tmp_path / "o.mp3"
        events = await generate_audio_with_subs("hi", "en", str(out))
        assert len(fake_edge.calls) == 2
        assert len(events) == 1
        assert out.read_bytes() == b"A"  # the failed attempt's bytes are gone

    async def test_failure_raises_generation_failed_and_removes_file(self, tmp_path, fake_edge):
        from TTS_ka.fast_audio import GenerationFailed, generate_audio_with_subs
        fake_edge.script = [Exception("disk full")]
        out = tmp_path / "o.mp3"
        with pytest.raises(GenerationFailed, match="disk full"):
            await generate_audio_with_subs("hi", "en", str(out))
        assert not out.exists()
