"""Tests for chunking module."""

import pytest
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text


class TestChunking:
    """Test cases for text chunking functions."""

    def test_split_text_into_chunks_basic(self):
        """Test basic text chunking functionality."""
        text = "Hello world. This is a test. Another sentence here."
        chunks = split_text_into_chunks(text, approx_seconds=30)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_split_text_into_chunks_short_text(self):
        """Test chunking with text shorter than chunk size."""
        text = "Short text"
        chunks = split_text_into_chunks(text, approx_seconds=60)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_text_into_chunks_empty_text(self):
        """Test chunking with empty text."""
        chunks = split_text_into_chunks("", approx_seconds=60)
        assert chunks == []

    def test_split_text_into_chunks_long_text(self):
        """Test chunking with long text."""
        text = "This is a very long text that should be chunked. " * 50
        chunks = split_text_into_chunks(text, approx_seconds=15)
        
        assert len(chunks) > 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    @pytest.mark.parametrize("seconds", [15, 30, 60, 120])
    def test_split_text_various_durations(self, seconds):
        """Test chunking with various duration targets."""
        text = "This is a test sentence for chunking. " * 20
        chunks = split_text_into_chunks(text, approx_seconds=seconds)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_should_chunk_text_zero_seconds(self):
        """Test should_chunk_text with zero seconds."""
        text = "Any text"
        assert should_chunk_text(text, chunk_seconds=0) == False

    def test_should_chunk_text_positive_seconds(self):
        """Test should_chunk_text with positive seconds."""
        text = "Any text"
        assert should_chunk_text(text, chunk_seconds=30) == True

    def test_should_chunk_text_various_inputs(self):
        """Test should_chunk_text with various inputs."""
        text = "Test text"
        
        assert should_chunk_text(text, chunk_seconds=0) == False
        assert should_chunk_text(text, chunk_seconds=1) == True
        assert should_chunk_text(text, chunk_seconds=60) == True
        assert should_chunk_text("", chunk_seconds=30) == True

    def test_chunking_preserves_words(self):
        """Test that chunking preserves all words."""
        text = "Word1 word2 word3 word4 word5 word6 word7 word8 word9 word10"
        chunks = split_text_into_chunks(text, approx_seconds=30)
        
        # Count words in original vs reconstructed
        original_words = text.split()
        reconstructed_words = []
        for chunk in chunks:
            reconstructed_words.extend(chunk.split())
        
        assert len(original_words) == len(reconstructed_words)
        assert original_words == reconstructed_words