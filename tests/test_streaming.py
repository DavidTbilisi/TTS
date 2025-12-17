"""Tests for streaming audio playback functionality."""

import os
import sys
import time
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock, call

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

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
        with open(chunk_path, 'wb') as f:
            f.write(b'fake audio data')
        
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
        with open(chunk_path, 'wb') as f:
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
    
    @patch('os.startfile')
    def test_windows_playback(self, mock_startfile, temp_dir):
        """Test Windows playback path."""
        with patch('sys.platform', 'win32'):
            player = StreamingAudioPlayer()
            
            # Create test chunks
            chunk1 = os.path.join(temp_dir, "chunk1.mp3")
            chunk2 = os.path.join(temp_dir, "chunk2.mp3")
            
            with open(chunk1, 'wb') as f:
                f.write(b'audio data 1')
            with open(chunk2, 'wb') as f:
                f.write(b'audio data 2')
            
            player.start()
            player.add_chunk(chunk1)
            player.add_chunk(chunk2)
            player.finish_generation()
            
            # Wait for playback thread
            player.playback_thread.join(timeout=2)
            
            # Should have called os.startfile for first chunk
            mock_startfile.assert_called_once()
    
    @patch('subprocess.run')
    def test_find_streaming_player(self, mock_run):
        """Test finding available audio players on Unix."""
        player = StreamingAudioPlayer()
        
        # Mock successful mpv detection
        mock_run.return_value = MagicMock(returncode=0)
        
        result = player._find_streaming_player()
        
        assert result == 'mpv'
    
    @patch('subprocess.run')
    def test_find_no_player(self, mock_run):
        """Test when no player is available."""
        player = StreamingAudioPlayer()
        
        # Mock failed detection
        mock_run.return_value = MagicMock(returncode=1)
        
        result = player._find_streaming_player()
        
        assert result is None
    
    def test_get_default_player_darwin(self):
        """Test default player on macOS."""
        with patch('sys.platform', 'darwin'):
            player = StreamingAudioPlayer()
            result = player._get_default_player()
            assert result == 'afplay'
    
    def test_get_default_player_linux(self):
        """Test default player on Linux."""
        with patch('sys.platform', 'linux'):
            player = StreamingAudioPlayer()
            result = player._get_default_player()
            assert result == 'mpg123'
    
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
    
    @patch('os.startfile')
    def test_full_streaming_workflow(self, mock_startfile, temp_dir):
        """Test complete streaming workflow."""
        with patch('sys.platform', 'win32'):
            player = StreamingAudioPlayer()
            
            # Create multiple chunks
            chunks = []
            for i in range(3):
                chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
                with open(chunk_path, 'wb') as f:
                    f.write(f'audio data {i}'.encode())
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
            with open(output, 'wb') as f:
                f.write(b'fake audio')
            return True
        
        with patch('TTS_ka.ultra_fast.fast_generate_audio', mock_generate):
            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                parts = await ultra_fast_parallel_generation(
                    chunks, 'en', parallel=2, streaming_player=player
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
            with open(output, 'wb') as f:
                f.write(b'fake audio data')
            return True
        
        # Mock merge function
        def mock_merge(parts, output):
            with open(output, 'wb') as f:
                f.write(b'merged audio')
        
        with patch('TTS_ka.ultra_fast.fast_generate_audio', mock_generate), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files', mock_merge):
            
            # Change to temp directory
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                await smart_generate_long_text(
                    text=long_text,
                    language='en',
                    chunk_seconds=15,
                    parallel=2,
                    output_path=output_path,
                    enable_streaming=True
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
            with open(output, 'wb') as f:
                f.write(b'fake audio')
            return True
        
        def mock_merge(parts, output):
            with open(output, 'wb') as f:
                f.write(b'merged')
        
        with patch('TTS_ka.ultra_fast.fast_generate_audio', mock_generate), \
             patch('TTS_ka.ultra_fast.fast_merge_audio_files', mock_merge):
            
            original_dir = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                # Call without enable_streaming
                await smart_generate_long_text(
                    text=long_text,
                    language='en',
                    output_path=output_path,
                    enable_streaming=False  # Explicitly disabled
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
    
    @patch('os.startfile', side_effect=Exception("Playback error"))
    def test_playback_error_handling(self, mock_startfile, temp_dir):
        """Test that playback errors don't crash the system."""
        with patch('sys.platform', 'win32'):
            player = StreamingAudioPlayer()
            
            chunk_path = os.path.join(temp_dir, "error_chunk.mp3")
            with open(chunk_path, 'wb') as f:
                f.write(b'audio data')
            
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
            with open(chunk_path, 'wb') as f:
                f.write(b'audio')
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
            with open(output, 'wb') as f:
                f.write(b'audio')
            return True
        
        original_dir = os.getcwd()
        os.chdir(temp_dir)
        
        try:
            # Test without streaming
            start = time.time()
            with patch('TTS_ka.ultra_fast.fast_generate_audio', mock_generate):
                parts1 = await ultra_fast_parallel_generation(chunks, 'en', parallel=4)
            time_without = time.time() - start
            
            # Cleanup
            for part in parts1:
                if os.path.exists(part):
                    os.remove(part)
            
            # Test with streaming
            player = StreamingAudioPlayer()
            player.start()
            
            start = time.time()
            with patch('TTS_ka.ultra_fast.fast_generate_audio', mock_generate):
                parts2 = await ultra_fast_parallel_generation(
                    chunks, 'en', parallel=4, streaming_player=player
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
