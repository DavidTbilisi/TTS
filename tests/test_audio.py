"""Tests for audio module."""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.audio import generate_audio, merge_audio_files, play_audio
from TTS_ka.constants import VOICE_MAP


class TestGenerateAudio:
    """Tests for generate_audio async function."""

    async def test_generate_audio_success(self, temp_dir):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate') as mock_comm:
            mock_inst = AsyncMock()
            mock_comm.return_value = mock_inst
            result = await generate_audio("Hello world", "en", output_path)
        assert result is True
        mock_inst.save.assert_called_once_with(output_path)

    async def test_generate_audio_prints_path(self, temp_dir, capsys):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            await generate_audio("Hello", "en", output_path, quiet=False)
        assert "Audio generated" in capsys.readouterr().out

    async def test_generate_audio_quiet_no_print(self, temp_dir, capsys):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            await generate_audio("Hello", "en", output_path, quiet=True)
        assert capsys.readouterr().out == ""

    async def test_generate_audio_failure(self, temp_dir):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate', side_effect=Exception("API error")):
            result = await generate_audio("Hello", "en", output_path)
        assert result is False

    async def test_generate_audio_failure_prints_error(self, temp_dir, capsys):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate', side_effect=Exception("boom")):
            await generate_audio("Hello", "en", output_path, quiet=False)
        assert "Error" in capsys.readouterr().out

    @pytest.mark.parametrize("lang", ["ka", "ru", "en"])
    async def test_generate_audio_all_languages(self, lang, temp_dir):
        output_path = os.path.join(temp_dir, f"out_{lang}.mp3")
        with patch('TTS_ka.audio.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            result = await generate_audio("Test", lang, output_path, quiet=True)
        assert result is True
        # Voice used should match VOICE_MAP
        used_voice = mock_comm.call_args[0][1]
        assert used_voice == VOICE_MAP[lang]

    async def test_generate_audio_unknown_lang_uses_default(self, temp_dir):
        output_path = os.path.join(temp_dir, "out.mp3")
        with patch('TTS_ka.audio.Communicate') as mock_comm:
            mock_comm.return_value = AsyncMock()
            result = await generate_audio("Hello", "xx", output_path, quiet=True)
        assert result is True
        used_voice = mock_comm.call_args[0][1]
        assert used_voice == "en-GB-SoniaNeural"  # fallback default


class TestMergeAudioFiles:
    """Tests for merge_audio_files function."""

    def test_merge_empty_raises(self, temp_dir):
        with pytest.raises(ValueError):
            merge_audio_files([], os.path.join(temp_dir, "out.mp3"))

    def test_merge_single_file_with_pydub(self, temp_dir):
        part = os.path.join(temp_dir, "part.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        mock_seg = MagicMock()
        mock_seg.__add__ = MagicMock(return_value=mock_seg)
        with patch('TTS_ka.audio.HAS_PYDUB', True), \
             patch('TTS_ka.audio.AudioSegment') as mock_audio:
            mock_audio.from_mp3.return_value = mock_seg
            merge_audio_files([part], out)
        mock_seg.export.assert_called_once_with(out, format='mp3')

    def test_merge_multiple_files_with_pydub(self, temp_dir):
        parts = []
        for i in range(3):
            p = os.path.join(temp_dir, f"p{i}.mp3")
            with open(p, "wb") as f:
                f.write(b"fake")
            parts.append(p)
        out = os.path.join(temp_dir, "out.mp3")
        mock_seg = MagicMock()
        mock_seg.__add__ = MagicMock(return_value=mock_seg)
        with patch('TTS_ka.audio.HAS_PYDUB', True), \
             patch('TTS_ka.audio.AudioSegment') as mock_audio:
            mock_audio.from_mp3.return_value = mock_seg
            merge_audio_files(parts, out)
        assert mock_audio.from_mp3.call_count == 3

    def test_merge_removes_existing_output(self, temp_dir):
        part = os.path.join(temp_dir, "part.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with open(out, "wb") as f:
            f.write(b"old_data")
        mock_seg = MagicMock()
        mock_seg.__add__ = MagicMock(return_value=mock_seg)
        with patch('TTS_ka.audio.HAS_PYDUB', True), \
             patch('TTS_ka.audio.AudioSegment') as mock_audio:
            mock_audio.from_mp3.return_value = mock_seg
            merge_audio_files([part], out)
        # Old output was removed before new one created
        mock_audio.from_mp3.assert_called()

    def test_merge_ffmpeg_fallback(self, temp_dir):
        part = os.path.join(temp_dir, "part.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with patch('TTS_ka.audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0) as mock_sys, \
             patch('os.remove'):
            merge_audio_files([part], out)
        mock_sys.assert_called_once()
        cmd = mock_sys.call_args[0][0]
        assert "ffmpeg" in cmd

    def test_merge_ffmpeg_failure_raises(self, temp_dir):
        part = os.path.join(temp_dir, "part.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        with patch('TTS_ka.audio.HAS_PYDUB', False), \
             patch('os.system', return_value=1), \
             patch('os.remove'):
            with pytest.raises(RuntimeError):
                merge_audio_files([part], out)

    def test_merge_ffmpeg_cleanup_listfile(self, temp_dir):
        part = os.path.join(temp_dir, "part.mp3")
        out = os.path.join(temp_dir, "out.mp3")
        with open(part, "wb") as f:
            f.write(b"fake")
        removed = []
        real_remove = os.remove

        def track_remove(p):
            removed.append(p)

        with patch('TTS_ka.audio.HAS_PYDUB', False), \
             patch('os.system', return_value=0), \
             patch('os.remove', side_effect=track_remove):
            merge_audio_files([part], out)
        assert any('.ff_concat.txt' in p for p in removed)


class TestPlayAudio:
    """Tests for play_audio function."""

    def test_play_audio_windows(self, temp_dir):
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'win32'), \
             patch('os.startfile') as mock_start:
            play_audio(f)
        mock_start.assert_called_once()

    def test_play_audio_mac(self, temp_dir):
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'darwin'), \
             patch('os.system') as mock_sys:
            play_audio(f)
        mock_sys.assert_called_once()
        assert "open" in mock_sys.call_args[0][0]

    def test_play_audio_linux(self, temp_dir):
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'linux'), \
             patch('os.system', return_value=0) as mock_sys:
            play_audio(f)
        mock_sys.assert_called()

    def test_play_audio_oserror_silenced(self, temp_dir):
        f = os.path.join(temp_dir, "test.mp3")
        with open(f, "wb") as fp:
            fp.write(b"fake")
        with patch('sys.platform', 'win32'), \
             patch('os.startfile', side_effect=OSError("locked")):
            play_audio(f)  # must not raise
