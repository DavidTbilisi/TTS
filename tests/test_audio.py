"""Tests for audio module."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from TTS_ka.audio import concatenate_audio_files, play_audio


class TestAudio:
    """Test cases for audio processing functions."""

    def test_concatenate_audio_files_single_file(self, temp_dir):
        """Test concatenating a single audio file."""
        input_file = os.path.join(temp_dir, "input.mp3")
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input file
        with open(input_file, "wb") as f:
            f.write(b"fake_audio_data")

        with patch("shutil.move") as mock_move:
            result = concatenate_audio_files([input_file], output_file)

        assert result == True
        mock_move.assert_called_once_with(input_file, output_file)

    def test_concatenate_audio_files_multiple_files(self, temp_dir):
        """Test concatenating multiple audio files."""
        input_files = [
            os.path.join(temp_dir, "input1.mp3"),
            os.path.join(temp_dir, "input2.mp3"),
            os.path.join(temp_dir, "input3.mp3"),
        ]
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input files
        for input_file in input_files:
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
            mock_segment = MagicMock()
            mock_from_mp3.return_value = mock_segment

            with patch.object(mock_segment, "export") as mock_export:
                result = concatenate_audio_files(input_files, output_file)

        assert result == True
        assert mock_from_mp3.call_count == len(input_files)
        mock_export.assert_called_once_with(output_file, format="mp3")

    def test_concatenate_audio_files_empty_list(self, temp_dir):
        """Test concatenating empty file list."""
        output_file = os.path.join(temp_dir, "output.mp3")

        result = concatenate_audio_files([], output_file)
        assert result == False

    def test_concatenate_audio_files_nonexistent_input(self, temp_dir):
        """Test concatenating with non-existent input files."""
        input_files = [os.path.join(temp_dir, "nonexistent.mp3")]
        output_file = os.path.join(temp_dir, "output.mp3")

        result = concatenate_audio_files(input_files, output_file)
        assert result == False

    def test_concatenate_audio_files_pydub_exception(self, temp_dir):
        """Test concatenating with pydub exception."""
        input_files = [os.path.join(temp_dir, "input1.mp3"), os.path.join(temp_dir, "input2.mp3")]
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input files
        for input_file in input_files:
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        with patch("pydub.AudioSegment.from_mp3", side_effect=Exception("Pydub error")):
            result = concatenate_audio_files(input_files, output_file)

        assert result == False

    def test_concatenate_audio_files_cleanup(self, temp_dir):
        """Test that temporary files are cleaned up."""
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
                with patch("os.remove") as mock_remove:
                    concatenate_audio_files(input_files, output_file)

        # Should remove temporary files
        assert mock_remove.call_count == len(input_files)

    def test_play_audio_pygame_success(self, temp_dir):
        """Test successful audio playback with pygame."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        with patch("pygame.mixer.init") as mock_init:
            with patch("pygame.mixer.music.load") as mock_load:
                with patch("pygame.mixer.music.play") as mock_play:
                    with patch("pygame.mixer.get_busy", return_value=False):
                        result = play_audio(audio_file)

        assert result == True
        mock_init.assert_called_once()
        mock_load.assert_called_once_with(audio_file)
        mock_play.assert_called_once()

    def test_play_audio_pygame_exception(self, temp_dir):
        """Test audio playback with pygame exception."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        with patch("pygame.mixer.init", side_effect=Exception("Pygame error")):
            result = play_audio(audio_file)

        assert result == False

    def test_play_audio_file_not_found(self):
        """Test audio playback with non-existent file."""
        result = play_audio("nonexistent.mp3")
        assert result == False

    def test_play_audio_playsound_fallback(self, temp_dir):
        """Test audio playback fallback to playsound."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        # Mock pygame failure, playsound success
        with patch("pygame.mixer.init", side_effect=ImportError("No pygame")):
            with patch("playsound.playsound") as mock_playsound:
                result = play_audio(audio_file)

        assert result == True
        mock_playsound.assert_called_once_with(audio_file)

    def test_play_audio_all_methods_fail(self, temp_dir):
        """Test audio playback when all methods fail."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        # Mock all playback methods to fail
        with patch("pygame.mixer.init", side_effect=ImportError("No pygame")):
            with patch("playsound.playsound", side_effect=ImportError("No playsound")):
                result = play_audio(audio_file)

        assert result == False

    def test_concatenate_audio_files_large_number(self, temp_dir):
        """Test concatenating large number of audio files."""
        input_files = []
        for i in range(10):
            input_file = os.path.join(temp_dir, f"input{i}.mp3")
            input_files.append(input_file)
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        output_file = os.path.join(temp_dir, "output.mp3")

        with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
            mock_segment = MagicMock()
            mock_from_mp3.return_value = mock_segment

            with patch.object(mock_segment, "export"):
                result = concatenate_audio_files(input_files, output_file)

        assert result == True
        assert mock_from_mp3.call_count == len(input_files)

    @pytest.mark.parametrize("file_count", [1, 2, 5, 10])
    def test_concatenate_various_file_counts(self, file_count, temp_dir):
        """Test concatenating various numbers of files."""
        input_files = []
        for i in range(file_count):
            input_file = os.path.join(temp_dir, f"input{i}.mp3")
            input_files.append(input_file)
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        output_file = os.path.join(temp_dir, "output.mp3")

        if file_count == 1:
            with patch("shutil.move") as mock_move:
                result = concatenate_audio_files(input_files, output_file)
            assert result == True
        else:
            with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
                mock_segment = MagicMock()
                mock_from_mp3.return_value = mock_segment

                with patch.object(mock_segment, "export"):
                    result = concatenate_audio_files(input_files, output_file)

            assert result == True

    def test_play_audio_wait_for_completion(self, temp_dir):
        """Test that play_audio waits for completion."""
        audio_file = os.path.join(temp_dir, "test.mp3")

        with open(audio_file, "wb") as f:
            f.write(b"fake_audio_data")

        # Mock pygame to simulate audio playing then finishing
        with patch("pygame.mixer.init"):
            with patch("pygame.mixer.music.load"):
                with patch("pygame.mixer.music.play"):
                    with patch("pygame.mixer.get_busy", side_effect=[True, True, False]):
                        with patch("time.sleep") as mock_sleep:
                            result = play_audio(audio_file)

        assert result == True
        assert mock_sleep.call_count >= 2  # Should sleep while audio is playing

    def test_concatenate_preserves_audio_quality(self, temp_dir):
        """Test that concatenation preserves audio parameters."""
        input_files = [os.path.join(temp_dir, "input1.mp3"), os.path.join(temp_dir, "input2.mp3")]
        output_file = os.path.join(temp_dir, "output.mp3")

        # Create fake input files
        for input_file in input_files:
            with open(input_file, "wb") as f:
                f.write(b"fake_audio_data")

        with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
            mock_segment = MagicMock()
            mock_segment.__add__ = MagicMock(return_value=mock_segment)  # For concatenation
            mock_from_mp3.return_value = mock_segment

            with patch.object(mock_segment, "export") as mock_export:
                result = concatenate_audio_files(input_files, output_file)

        assert result == True
        # Should export with mp3 format
        mock_export.assert_called_once_with(output_file, format="mp3")
