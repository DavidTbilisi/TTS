"""Tests for ultra_fast module."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.ultra_fast import (
    process_chunks_parallel, 
    calculate_optimal_workers, 
    determine_strategy,
    generate_tts_turbo
)


class TestUltraFast:
    """Test cases for ultra-fast TTS processing."""

    def test_calculate_optimal_workers_small_chunks(self):
        """Test optimal workers calculation for small chunk count."""
        workers = calculate_optimal_workers(2, max_workers=8)
        assert workers == 2

    def test_calculate_optimal_workers_large_chunks(self):
        """Test optimal workers calculation for large chunk count."""
        workers = calculate_optimal_workers(20, max_workers=8)
        assert workers == 8

    def test_calculate_optimal_workers_zero_chunks(self):
        """Test optimal workers calculation for zero chunks."""
        workers = calculate_optimal_workers(0, max_workers=8)
        assert workers == 1

    def test_calculate_optimal_workers_default_max(self):
        """Test optimal workers calculation with default max."""
        workers = calculate_optimal_workers(10)
        assert 1 <= workers <= 6

    def test_determine_strategy_short_text(self):
        """Test strategy determination for short text."""
        strategy, chunks, workers = determine_strategy(
            "Short text", language="en", max_workers=4
        )
        assert strategy == "direct generation"
        assert chunks == 1
        assert workers == 1

    def test_determine_strategy_medium_text(self):
        """Test strategy determination for medium text."""
        text = "This is a medium length text. " * 10
        strategy, chunks, workers = determine_strategy(
            text, language="en", max_workers=4
        )
        # Could be either direct or smart depending on exact length
        assert strategy in ["direct generation", "smart generation"]
        assert chunks >= 1
        assert workers >= 1

    def test_determine_strategy_long_text(self):
        """Test strategy determination for long text."""
        text = "This is a very long text that should be chunked. " * 50
        strategy, chunks, workers = determine_strategy(
            text, language="en", max_workers=8
        )
        assert strategy == "smart generation"
        assert chunks > 1
        assert workers > 1

    def test_determine_strategy_empty_text(self):
        """Test strategy determination for empty text."""
        strategy, chunks, workers = determine_strategy(
            "", language="en", max_workers=4
        )
        assert strategy == "direct generation"
        assert chunks == 1
        assert workers == 1

    @pytest.mark.asyncio
    async def test_process_chunks_parallel_success(self, temp_dir):
        """Test successful parallel chunk processing."""
        chunks = ["Hello world", "This is a test"]
        output_path = f"{temp_dir}/test.mp3"
        
        # Mock the audio generation function
        async def mock_generate_audio(text, path, lang):
            return True
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.ProgressTracker') as mock_tracker:
                mock_progress = MagicMock()
                mock_tracker.return_value.__enter__.return_value = mock_progress
                
                with patch('TTS_ka.ultra_fast.concatenate_audio_files') as mock_concat:
                    mock_concat.return_value = True
                    
                    result = await process_chunks_parallel(
                        chunks, output_path, "en", max_workers=2
                    )
        
        assert result == True
        assert mock_progress.update.call_count == len(chunks)

    @pytest.mark.asyncio
    async def test_process_chunks_parallel_single_chunk(self, temp_dir):
        """Test parallel processing with single chunk."""
        chunks = ["Single chunk text"]
        output_path = f"{temp_dir}/test.mp3"
        
        async def mock_generate_audio(text, path, lang):
            return True
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            result = await process_chunks_parallel(
                chunks, output_path, "en", max_workers=1
            )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_process_chunks_parallel_failure(self, temp_dir):
        """Test parallel processing with generation failure."""
        chunks = ["Hello world", "This is a test"]
        output_path = f"{temp_dir}/test.mp3"
        
        async def mock_generate_audio(text, path, lang):
            return False  # Simulate failure
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.ProgressTracker') as mock_tracker:
                mock_progress = MagicMock()
                mock_tracker.return_value.__enter__.return_value = mock_progress
                
                result = await process_chunks_parallel(
                    chunks, output_path, "en", max_workers=2
                )
        
        assert result == False

    @pytest.mark.asyncio
    async def test_process_chunks_parallel_empty_chunks(self, temp_dir):
        """Test parallel processing with empty chunks."""
        chunks = []
        output_path = f"{temp_dir}/test.mp3"
        
        result = await process_chunks_parallel(
            chunks, output_path, "en", max_workers=2
        )
        
        assert result == False

    @pytest.mark.asyncio
    async def test_generate_tts_turbo_direct(self, sample_text, temp_dir):
        """Test turbo TTS generation with direct strategy."""
        output_path = f"{temp_dir}/test.mp3"
        
        async def mock_generate_audio(text, path, lang):
            return True
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
                mock_strategy.return_value = ("direct generation", 1, 1)
                
                result = await generate_tts_turbo(
                    sample_text, output_path, "en", max_workers=4
                )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_tts_turbo_smart(self, sample_long_text, temp_dir):
        """Test turbo TTS generation with smart strategy."""
        output_path = f"{temp_dir}/test.mp3"
        
        with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
            mock_strategy.return_value = ("smart generation", 5, 4)
            
            with patch('TTS_ka.ultra_fast.smart_chunk_text') as mock_chunk:
                mock_chunk.return_value = ["chunk1", "chunk2", "chunk3"]
                
                with patch('TTS_ka.ultra_fast.process_chunks_parallel') as mock_process:
                    mock_process.return_value = True
                    
                    result = await generate_tts_turbo(
                        sample_long_text, output_path, "en", max_workers=4
                    )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_tts_turbo_failure(self, sample_text, temp_dir):
        """Test turbo TTS generation with failure."""
        output_path = f"{temp_dir}/test.mp3"
        
        async def mock_generate_audio(text, path, lang):
            return False
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
                mock_strategy.return_value = ("direct generation", 1, 1)
                
                result = await generate_tts_turbo(
                    sample_text, output_path, "en", max_workers=4
                )
        
        assert result == False

    @pytest.mark.parametrize("chunk_count,max_workers,expected_min", [
        (1, 4, 1),
        (5, 4, 4),
        (10, 8, 6),
        (20, 6, 6)
    ])
    def test_calculate_optimal_workers_parametrized(self, chunk_count, max_workers, expected_min):
        """Test optimal workers calculation with various parameters."""
        workers = calculate_optimal_workers(chunk_count, max_workers)
        assert workers >= 1
        assert workers <= max_workers
        if chunk_count > 0:
            assert workers <= chunk_count

    @pytest.mark.parametrize("text_multiplier", [1, 5, 10, 20, 50])
    def test_determine_strategy_scaling(self, text_multiplier):
        """Test strategy determination with different text sizes."""
        base_text = "This is a test sentence. "
        text = base_text * text_multiplier
        
        strategy, chunks, workers = determine_strategy(
            text, language="en", max_workers=8
        )
        
        assert strategy in ["direct generation", "smart generation"]
        assert chunks >= 1
        assert workers >= 1
        assert workers <= 8

    def test_strategy_consistency(self):
        """Test that strategy determination is consistent."""
        text = "This is a consistent test text."
        
        strategy1, chunks1, workers1 = determine_strategy(text, "en", 4)
        strategy2, chunks2, workers2 = determine_strategy(text, "en", 4)
        
        assert strategy1 == strategy2
        assert chunks1 == chunks2
        assert workers1 == workers2

    @pytest.mark.asyncio
    async def test_generate_tts_turbo_georgian(self, sample_georgian_text, temp_dir):
        """Test turbo generation with Georgian text."""
        output_path = f"{temp_dir}/test_ka.mp3"
        
        async def mock_generate_audio(text, path, lang):
            assert lang == "ka"
            return True
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
                mock_strategy.return_value = ("direct generation", 1, 1)
                
                result = await generate_tts_turbo(
                    sample_georgian_text, output_path, "ka", max_workers=4
                )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_tts_turbo_russian(self, sample_russian_text, temp_dir):
        """Test turbo generation with Russian text."""
        output_path = f"{temp_dir}/test_ru.mp3"
        
        async def mock_generate_audio(text, path, lang):
            assert lang == "ru"
            return True
        
        with patch('TTS_ka.ultra_fast.generate_audio_ultra_fast', side_effect=mock_generate_audio):
            with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
                mock_strategy.return_value = ("direct generation", 1, 1)
                
                result = await generate_tts_turbo(
                    sample_russian_text, output_path, "ru", max_workers=4
                )
        
        assert result == True