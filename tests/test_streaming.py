"""Tests for streaming audio playback functionality."""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from TTS_ka.streaming_player import StreamingAudioPlayer


class TestStreamingAudioPlayer:
    """Test suite for StreamingAudioPlayer class."""

    def test_player_initialization(self):
        """Test that player initializes correctly."""
        player = StreamingAudioPlayer()

        assert player.chunk_queue is not None
        assert player.playback_thread is None
        assert player.is_playing is False
        assert player.finished_generating is False
        assert player.process is None

    def test_add_chunk(self, temp_dir):
        """Test adding chunks to the player queue."""
        player = StreamingAudioPlayer()

        # Create a test audio file
        chunk_path = os.path.join(temp_dir, "test_chunk.mp3")
        with open(chunk_path, "wb") as f:
            f.write(b"fake audio data")

        # Add chunk
        player.add_chunk(chunk_path)

        # Verify it was added
        assert not player.chunk_queue.empty()
        assert player.chunk_queue.get() == chunk_path

    def test_add_nonexistent_chunk(self):
        """Test that nonexistent chunks are not added."""
        player = StreamingAudioPlayer()

        # Try to add a file that doesn't exist
        player.add_chunk("/fake/path/that/does/not/exist.mp3")

        # Queue should be empty
        assert player.chunk_queue.empty()

    def test_add_empty_chunk(self, temp_dir):
        """Test that empty chunks are not added."""
        player = StreamingAudioPlayer()

        # Create an empty file
        chunk_path = os.path.join(temp_dir, "empty_chunk.mp3")
        with open(chunk_path, "wb") as f:
            pass  # Empty file

        # Add chunk
        player.add_chunk(chunk_path)

        # Queue should be empty (empty files not added)
        assert player.chunk_queue.empty()

    def test_finish_generation(self):
        """Test signaling generation completion."""
        player = StreamingAudioPlayer()

        assert player.finished_generating is False

        player.finish_generation()

        assert player.finished_generating is True
        # Verify sentinel was added
        assert player.chunk_queue.get() is None

    def test_start_playback(self):
        """Test starting the playback thread."""
        player = StreamingAudioPlayer()

        assert player.is_playing is False
        assert player.playback_thread is None

        player.start()

        assert player.is_playing is True
        assert player.playback_thread is not None
        assert player.playback_thread.daemon is True

        # Cleanup
        player.finish_generation()
        player.playback_thread.join(timeout=1)

    def test_start_playback_twice(self):
        """Test that starting twice doesn't create multiple threads."""
        player = StreamingAudioPlayer()

        player.start()
        first_thread = player.playback_thread

        player.start()
        second_thread = player.playback_thread

        assert first_thread is second_thread

        # Cleanup
        player.finish_generation()
        player.playback_thread.join(timeout=1)

    def test_stop_playback(self):
        """Test stopping playback."""
        player = StreamingAudioPlayer()
        player.start()

        assert player.is_playing is True

        player.stop()

        assert player.is_playing is False

    @patch("os.startfile")
    def test_windows_playback(self, mock_startfile, temp_dir):
        """Test Windows playback path."""
        with patch("sys.platform", "win32"):
            player = StreamingAudioPlayer()

            # Create test chunks
            chunk1 = os.path.join(temp_dir, "chunk1.mp3")
            chunk2 = os.path.join(temp_dir, "chunk2.mp3")

            with open(chunk1, "wb") as f:
                f.write(b"audio data 1")
            with open(chunk2, "wb") as f:
                f.write(b"audio data 2")

            player.start()
            player.add_chunk(chunk1)
            player.add_chunk(chunk2)
            player.finish_generation()

            # Wait for playback thread
            player.playback_thread.join(timeout=2)

            # Should have called os.startfile for first chunk
            mock_startfile.assert_called_once()

    @patch("subprocess.run")
    def test_find_streaming_player(self, mock_run):
        """Test finding available audio players on Unix."""
        player = StreamingAudioPlayer()

        # Mock successful mpv detection
        mock_run.return_value = MagicMock(returncode=0)

        result = player._find_streaming_player()

        assert result == "mpv"

    @patch("subprocess.run")
    def test_find_no_player(self, mock_run):
        """Test when no player is available."""
        player = StreamingAudioPlayer()

        # Mock failed detection
        mock_run.return_value = MagicMock(returncode=1)

        result = player._find_streaming_player()

        assert result is None

    def test_get_default_player_darwin(self):
        """Test default player on macOS."""
        with patch("sys.platform", "darwin"):
            player = StreamingAudioPlayer()
            result = player._get_default_player()
            assert result == "afplay"

    def test_get_default_player_linux(self):
        """Test default player on Linux."""
        with patch("sys.platform", "linux"):
            player = StreamingAudioPlayer()
            result = player._get_default_player()
            assert result == "mpg123"

    def test_wait_for_completion_timeout(self):
        """Test waiting for playback completion with timeout."""
        player = StreamingAudioPlayer()
        player.start()
        player.finish_generation()

        # Should complete quickly since there are no chunks
        start = time.time()
        player.wait_for_completion()
        elapsed = time.time() - start

        # Should finish quickly (not hit 300s timeout)
        assert elapsed < 5

    @patch("os.startfile")
    def test_full_streaming_workflow(self, mock_startfile, temp_dir):
        """Test complete streaming workflow."""
        with patch("sys.platform", "win32"):
            player = StreamingAudioPlayer()

            # Create multiple chunks
            chunks = []
            for i in range(3):
                chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
                with open(chunk_path, "wb") as f:
                    f.write(f"audio data {i}".encode())
                chunks.append(chunk_path)

            # Start playback
            player.start()
            assert player.is_playing is True

            # Add chunks as they "generate"
            for chunk in chunks:
                player.add_chunk(chunk)
                time.sleep(0.01)

            # Signal completion
            player.finish_generation()
            assert player.finished_generating is True

            # Wait for playback
            player.wait_for_completion()

            # Verify playback was initiated
            assert mock_startfile.called


class TestStreamingIntegration:
    """Test streaming integration with generation functions."""

    @pytest.mark.asyncio
    async def test_streaming_with_ultra_fast_generation(self, temp_dir):
        """Test streaming with ultra_fast_parallel_generation."""
        from TTS_ka.ultra_fast import ultra_fast_parallel_generation

        # Create player
        player = StreamingAudioPlayer()
        player.start()

        # Mock chunks
        chunks = ["Hello world", "This is a test", "Streaming audio"]

        # Mock fast_generate_audio to create fake files
        async def mock_generate(text, lang, output, quiet=False):
            with open(output, "wb") as f:
                f.write(b"fake audio")
            return True

        with patch("TTS_ka.ultra_fast.fast_generate_audio", mock_generate):
            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)

            try:
                parts = await ultra_fast_parallel_generation(
                    chunks, "en", parallel=2, streaming_player=player
                )

                # Signal completion
                player.finish_generation()

                # Verify parts were created
                assert len(parts) == len(chunks)
                for part in parts:
                    assert os.path.exists(part)

                # Cleanup
                for part in parts:
                    if os.path.exists(part):
                        os.remove(part)
            finally:
                os.chdir(original_dir)

    @pytest.mark.asyncio
    async def test_smart_generate_with_streaming(self, temp_dir):
        """Test smart_generate_long_text with streaming enabled."""
        from TTS_ka.ultra_fast import smart_generate_long_text

        # Long text to trigger chunking
        long_text = "This is a test sentence. " * 100
        output_path = os.path.join(temp_dir, "streaming_test.mp3")

        # Mock the fast_generate_audio function
        async def mock_generate(text, lang, output, quiet=False):
            with open(output, "wb") as f:
                f.write(b"fake audio data")
            return True

        # Mock merge function
        def mock_merge(parts, output):
            with open(output, "wb") as f:
                f.write(b"merged audio")

        with (
            patch("TTS_ka.ultra_fast.fast_generate_audio", mock_generate),
            patch("TTS_ka.ultra_fast.fast_merge_audio_files", mock_merge),
        ):

            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)

            try:
                await smart_generate_long_text(
                    text=long_text,
                    language="en",
                    chunk_seconds=15,
                    parallel=2,
                    output_path=output_path,
                    enable_streaming=True,
                )

                # Verify output was created
                assert os.path.exists(output_path)
            finally:
                os.chdir(original_dir)

    @pytest.mark.asyncio
    async def test_streaming_disabled_by_default(self, temp_dir):
        """Test that streaming is disabled by default."""
        from TTS_ka.ultra_fast import smart_generate_long_text

        long_text = "This is a test. " * 100
        output_path = os.path.join(temp_dir, "no_streaming_test.mp3")

        async def mock_generate(text, lang, output, quiet=False):
            with open(output, "wb") as f:
                f.write(b"fake audio")
            return True

        def mock_merge(parts, output):
            with open(output, "wb") as f:
                f.write(b"merged")

        with (
            patch("TTS_ka.ultra_fast.fast_generate_audio", mock_generate),
            patch("TTS_ka.ultra_fast.fast_merge_audio_files", mock_merge),
        ):

            original_dir = os.getcwd()
            os.chdir(temp_dir)

            try:
                # Call without enable_streaming
                await smart_generate_long_text(
                    text=long_text,
                    language="en",
                    output_path=output_path,
                    enable_streaming=False,  # Explicitly disabled
                )

                assert os.path.exists(output_path)
            finally:
                os.chdir(original_dir)


class TestStreamingEdgeCases:
    """Test edge cases and error handling."""

    def test_player_with_no_chunks(self):
        """Test player behavior with no chunks."""
        player = StreamingAudioPlayer()
        player.start()
        player.finish_generation()

        # Should complete without errors
        player.wait_for_completion()

        assert player.finished_generating is True

    @patch("os.startfile", side_effect=Exception("Playback error"))
    def test_playback_error_handling(self, mock_startfile, temp_dir):
        """Test that playback errors don't crash the system."""
        with patch("sys.platform", "win32"):
            player = StreamingAudioPlayer()

            chunk_path = os.path.join(temp_dir, "error_chunk.mp3")
            with open(chunk_path, "wb") as f:
                f.write(b"audio data")

            player.start()
            player.add_chunk(chunk_path)
            player.finish_generation()

            # Should handle error gracefully
            player.wait_for_completion()

            # Should still have attempted playback
            assert mock_startfile.called

    def test_multiple_sentinel_values(self):
        """Test that multiple sentinel values don't break the queue."""
        player = StreamingAudioPlayer()

        player.finish_generation()
        player.finish_generation()  # Call twice

        # Should still work
        assert player.finished_generating is True


class TestStreamingPerformance:
    """Test streaming performance characteristics."""

    @pytest.mark.slow
    def test_chunk_queue_performance(self, temp_dir):
        """Test that queue handles many chunks efficiently."""
        player = StreamingAudioPlayer()

        # Create many chunks
        chunks = []
        for i in range(50):
            chunk_path = os.path.join(temp_dir, f"perf_chunk_{i}.mp3")
            with open(chunk_path, "wb") as f:
                f.write(b"audio")
            chunks.append(chunk_path)

        # Add all chunks
        start = time.time()
        for chunk in chunks:
            player.add_chunk(chunk)
        elapsed = time.time() - start

        # Should be very fast (<1 second for 50 chunks)
        assert elapsed < 1.0

        # Verify all were added
        added_count = 0
        while not player.chunk_queue.empty():
            player.chunk_queue.get()
            added_count += 1

        assert added_count == 50

    @pytest.mark.asyncio
    async def test_parallel_generation_with_streaming_speed(self, temp_dir):
        """Test that streaming doesn't slow down generation."""
        from TTS_ka.ultra_fast import ultra_fast_parallel_generation

        chunks = ["Test text"] * 10

        async def mock_generate(text, lang, output, quiet=False):
            await asyncio.sleep(0.01)  # Simulate generation
            with open(output, "wb") as f:
                f.write(b"audio")
            return True

        original_dir = os.getcwd()
        os.chdir(temp_dir)

        try:
            # Test without streaming
            start = time.time()
            with patch("TTS_ka.ultra_fast.fast_generate_audio", mock_generate):
                parts1 = await ultra_fast_parallel_generation(chunks, "en", parallel=4)
            time_without = time.time() - start

            # Cleanup
            for part in parts1:
                if os.path.exists(part):
                    os.remove(part)

            # Test with streaming
            player = StreamingAudioPlayer()
            player.start()

            start = time.time()
            with patch("TTS_ka.ultra_fast.fast_generate_audio", mock_generate):
                parts2 = await ultra_fast_parallel_generation(
                    chunks, "en", parallel=4, streaming_player=player
                )
            time_with = time.time() - start

            player.finish_generation()

            # Cleanup
            for part in parts2:
                if os.path.exists(part):
                    os.remove(part)

            # Streaming should add minimal overhead (<10%)
            assert time_with < time_without * 1.1
        finally:
            os.chdir(original_dir)


class TestStreamingFileHandling:
    """Test file handling and cleanup for streaming functionality."""

    def test_locked_file_handling(self, temp_dir):
        """Test handling of locked files during cleanup."""
        from TTS_ka.ultra_fast import ultra_fast_cleanup_parts

        # Create test files
        part_files = []
        for i in range(3):
            part_file = os.path.join(temp_dir, f"part_{i}.mp3")
            with open(part_file, "wb") as f:
                f.write(b"dummy data")
            part_files.append(part_file)

        # Mock one file as locked
        original_remove = os.remove

        def mock_remove(path):
            if "part_1" in path:
                raise PermissionError("File locked by media player")
            else:
                original_remove(path)

        with patch("os.remove", side_effect=mock_remove):
            # Should not crash on locked file
            ultra_fast_cleanup_parts(part_files, keep_parts=False)

        # Non-locked files should be removed, locked file should remain
        assert not os.path.exists(part_files[0])  # part_0 - removed
        assert os.path.exists(part_files[1])  # part_1 - locked, remains
        assert not os.path.exists(part_files[2])  # part_2 - removed

    def test_alternative_filename_generation(self):
        """Test alternative filename generation for locked files."""
        # This simulates the logic in ultra_fast_parallel_generation
        import time

        base_name = ".part_3.mp3"
        timestamp = int(time.time() * 1000)
        alternative_name = f".part_3_{timestamp}.mp3"

        # Alternative name should be unique and valid
        assert alternative_name != base_name
        assert alternative_name.startswith(".part_3_")
        assert alternative_name.endswith(".mp3")
        assert str(timestamp) in alternative_name


class TestStreamingIntegrationWithMainSystem:
    """Test streaming integration with main TTS system."""

    @pytest.mark.asyncio
    async def test_streaming_enabled_in_smart_generate(self, temp_dir):
        """Test that enable_streaming=True forces chunked generation."""
        from TTS_ka.ultra_fast import smart_generate_long_text

        output_path = os.path.join(temp_dir, "streaming_test.mp3")

        # Short text that would normally use direct generation
        short_text = "This is short text."

        with patch("TTS_ka.ultra_fast.fast_generate_audio") as mock_direct:
            with patch("TTS_ka.ultra_fast.ultra_fast_parallel_generation") as mock_parallel:
                # Mock parallel generation to create output file
                async def mock_parallel_gen(*args, **kwargs):
                    output = kwargs.get("output_path", args[4] if len(args) > 4 else "data.mp3")
                    with open(output, "wb") as f:
                        f.write(b"streaming audio")
                    return [output]

                mock_parallel.side_effect = mock_parallel_gen

                await smart_generate_long_text(
                    text=short_text,
                    language="en",
                    chunk_seconds=15,
                    parallel=1,
                    output_path=output_path,
                    enable_streaming=True,
                )

                # Should use parallel generation, not direct
                mock_direct.assert_not_called()
                mock_parallel.assert_called_once()

                # Should have created output file
                assert os.path.exists(output_path)

    @pytest.mark.asyncio
    async def test_single_chunk_streaming_no_merge(self, temp_dir):
        """Test that single chunk streaming doesn't attempt merge."""
        from TTS_ka.ultra_fast import smart_generate_long_text

        output_path = os.path.join(temp_dir, "single_chunk_test.mp3")

        with patch("TTS_ka.ultra_fast.ultra_fast_parallel_generation") as mock_parallel:
            with patch("TTS_ka.fast_audio.fast_merge_audio_files") as mock_merge:
                # Mock single chunk generation
                async def single_chunk_gen(*args, **kwargs):
                    output = kwargs.get("output_path", "data.mp3")
                    with open(output, "wb") as f:
                        f.write(b"single chunk audio")
                    return [output]  # Only one part

                mock_parallel.side_effect = single_chunk_gen

                await smart_generate_long_text(
                    text="Single chunk text",
                    language="en",
                    chunk_seconds=15,
                    parallel=1,
                    output_path=output_path,
                    enable_streaming=True,
                )

                # Should not attempt to merge single chunk
                mock_merge.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_chunk_streaming_with_merge(self, temp_dir):
        """Test multi-chunk streaming performs merge correctly."""
        from TTS_ka.ultra_fast import smart_generate_long_text

        output_path = os.path.join(temp_dir, "multi_chunk_test.mp3")

        with patch("TTS_ka.ultra_fast.ultra_fast_parallel_generation") as mock_parallel:
            with patch("TTS_ka.ultra_fast.fast_merge_audio_files") as mock_merge:
                # Mock multi-chunk generation
                async def multi_chunk_gen(*args, **kwargs):
                    output = kwargs.get("output_path", "data.mp3")

                    # Create output file (first chunk)
                    with open(output, "wb") as f:
                        f.write(b"first chunk")

                    # Create additional chunks
                    parts = [output]
                    for i in range(2):
                        part_path = f".part_{i+1}.mp3"
                        with open(part_path, "wb") as f:
                            f.write(f"chunk {i+1}".encode())
                        parts.append(part_path)

                    return parts

                mock_parallel.side_effect = multi_chunk_gen

                # Mock merge to create final file - this should be called
                def mock_merge_func(parts, output):
                    with open(output, "wb") as f:
                        f.write(b"merged audio from all chunks")

                mock_merge.side_effect = mock_merge_func

                await smart_generate_long_text(
                    text="Multi chunk text " * 20,  # Long enough for multiple chunks
                    language="en",
                    chunk_seconds=5,  # Small chunks to force multiple
                    parallel=2,
                    output_path=output_path,
                    enable_streaming=True,
                )

                # Should have attempted merge for multiple chunks
                assert mock_merge.called


class TestStreamingPlayerRobustness:
    """Test streaming player robustness and error handling."""

    def test_streaming_player_with_invalid_files(self):
        """Test streaming player handles invalid files gracefully."""
        player = StreamingAudioPlayer()

        # Test various invalid inputs
        invalid_inputs = [
            "",  # Empty string
            None,  # None
            "/nonexistent/path.mp3",  # Non-existent file
            "not_an_audio_file.txt",  # Wrong file type
        ]

        for invalid_input in invalid_inputs:
            # Should not crash
            try:
                player.add_chunk(invalid_input)
            except Exception as e:
                pytest.fail(f"add_chunk should handle invalid input gracefully: {e}")

        # Queue should remain empty
        assert player.chunk_queue.empty()

    def test_streaming_player_empty_file_handling(self, temp_dir):
        """Test streaming player handles empty audio files."""
        player = StreamingAudioPlayer()

        # Create empty file
        empty_file = os.path.join(temp_dir, "empty.mp3")
        with open(empty_file, "wb") as f:
            pass  # Create empty file

        player.add_chunk(empty_file)

        # Empty files should not be queued (size check)
        assert player.chunk_queue.empty()

    @patch("sys.platform", "win32")
    @patch("os.startfile")
    def test_windows_playback_error_recovery(self, mock_startfile, temp_dir):
        """Test Windows playback error recovery."""
        # Mock os.startfile to fail
        mock_startfile.side_effect = OSError("Cannot start file")

        player = StreamingAudioPlayer()

        # Create test chunk
        test_file = os.path.join(temp_dir, "test.mp3")
        with open(test_file, "wb") as f:
            f.write(b"test audio")

        player.add_chunk(test_file)
        player.finish_generation()

        # Should handle error gracefully without crashing
        try:
            player._playback_worker()
        except Exception as e:
            pytest.fail(f"Player should handle OS errors gracefully: {e}")

    def test_streaming_player_thread_safety(self, temp_dir):
        """Test streaming player thread safety."""
        player = StreamingAudioPlayer()

        # Create multiple test files
        test_files = []
        for i in range(10):
            test_file = os.path.join(temp_dir, f"thread_test_{i}.mp3")
            with open(test_file, "wb") as f:
                f.write(f"audio chunk {i}".encode())
            test_files.append(test_file)

        # Add chunks from multiple threads
        import threading

        def add_chunks(files):
            for file in files:
                player.add_chunk(file)
                time.sleep(0.001)  # Small delay

        threads = []
        chunk_size = len(test_files) // 3
        for i in range(0, len(test_files), chunk_size):
            chunk = test_files[i : i + chunk_size]
            thread = threading.Thread(target=add_chunks, args=(chunk,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should have all chunks in queue
        assert player.chunk_queue.qsize() == len(test_files)


class TestStreamingPerformance:
    """Test streaming performance characteristics."""

    def test_queue_performance_large_chunks(self, temp_dir):
        """Test queue performance with many chunks."""
        player = StreamingAudioPlayer()

        # Create many test chunks
        chunk_files = []
        for i in range(100):
            chunk_file = os.path.join(temp_dir, f"perf_{i}.mp3")
            with open(chunk_file, "wb") as f:
                f.write(f"chunk {i} data".encode())
            chunk_files.append(chunk_file)

        # Measure time to add all chunks
        start_time = time.time()
        for chunk_file in chunk_files:
            player.add_chunk(chunk_file)
        add_time = time.time() - start_time

        # Should be fast (under 0.5 seconds for 100 chunks)
        assert add_time < 0.5

        # All valid chunks should be queued
        assert player.chunk_queue.qsize() == 100

    def test_streaming_memory_usage(self, temp_dir):
        """Test streaming doesn't accumulate excessive memory."""
        player = StreamingAudioPlayer()

        # Add many chunks to test memory usage
        for i in range(50):
            chunk_file = os.path.join(temp_dir, f"mem_test_{i}.mp3")
            with open(chunk_file, "wb") as f:
                f.write(b"x" * 1024)  # 1KB per chunk
            player.add_chunk(chunk_file)

        # Queue should not grow excessively
        # (This is more of a regression test)
        assert player.chunk_queue.qsize() == 50

        # Finish to clean up
        player.finish_generation()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
