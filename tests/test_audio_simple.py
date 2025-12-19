"""Tests for audio module functions."""

import os
from unittest.mock import MagicMock, patch

import pytest

from TTS_ka.audio import generate_audio, merge_audio_files, play_audio


class TestAudio:
    """Test cases for audio processing functions."""

    @pytest.mark.asyncio
    async def test_generate_audio_basic(self, temp_dir):
        """Test basic audio generation."""
        output_path = os.path.join(temp_dir, "test.mp3")

        with patch("edge_tts.Communicate") as mock_communicate:
            mock_instance = MagicMock()
            mock_communicate.return_value = mock_instance

            # Mock the stream method
            async def mock_stream():
                yield {"type": "audio", "data": b"fake_audio_data"}

            mock_instance.stream.return_value = mock_stream()

            with patch("builtins.open", create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file

                await generate_audio("Hello world", "en", output_path)

        mock_file.write.assert_called()

    def test_merge_audio_files_single_file(self, temp_dir):
        """Test merging a single audio file."""
        input_file = os.path.join(temp_dir, "input.mp3")
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input file
        with open(input_file, "wb") as f:
            f.write(b"fake_audio_data")

        with patch("shutil.move") as mock_move:
            merge_audio_files([input_file], output_file)

        mock_move.assert_called_once_with(input_file, output_file)

    def test_merge_audio_files_multiple_files(self, temp_dir):
        """Test merging multiple audio files."""
        input_files = [os.path.join(temp_dir, "input1.mp3"), os.path.join(temp_dir, "input2.mp3")]
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input files
        for input_file in input_files:
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
            mock_segment = MagicMock()
            mock_from_mp3.return_value = mock_segment

            with patch.object(mock_segment, "export"):
                merge_audio_files(input_files, output_file)

        assert mock_from_mp3.call_count == len(input_files)

    def test_play_audio_success(self, temp_dir):
        """Test successful audio playback."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        with patch("pygame.mixer.init"):
            with patch("pygame.mixer.music.load"):
                with patch("pygame.mixer.music.play"):
                    with patch("pygame.mixer.get_busy", return_value=False):
                        # Should not raise exception
                        play_audio(audio_file)

    def test_play_audio_file_not_found(self):
        """Test audio playback with non-existent file."""
        # Should not raise exception for non-existent file
        play_audio("nonexistent.mp3")
