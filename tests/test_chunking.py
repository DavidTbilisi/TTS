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
        # Verify all text is preserved
        reconstructed = ' '.join(chunks)
        original_words = text.split()
        reconstructed_words = reconstructed.split()
        assert len(original_words) == len(reconstructed_words)

    def test_smart_chunk_text_short_text(self):
        """Test chunking with text shorter than max_length."""
        text = "Short text"
        chunks = smart_chunk_text(text, max_length=50)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_smart_chunk_text_empty_text(self):
        """Test chunking with empty text."""
        chunks = smart_chunk_text("", max_length=50)
        assert chunks == [""]

    def test_smart_chunk_text_whitespace_only(self):
        """Test chunking with whitespace only."""
        chunks = smart_chunk_text("   \n\t  ", max_length=50)
        assert len(chunks) == 1

    def test_smart_chunk_text_no_punctuation(self):
        """Test chunking text without punctuation."""
        text = "word1 word2 word3 word4 word5 word6 word7 word8"
        chunks = smart_chunk_text(text, max_length=15)
        
        assert len(chunks) > 1
        assert all(len(chunk) <= 20 for chunk in chunks)

    def test_smart_chunk_text_long_word(self):
        """Test chunking with very long words."""
        text = "supercalifragilisticexpialidocious is a long word"
        chunks = smart_chunk_text(text, max_length=20)
        
        assert len(chunks) >= 1
        # Long words should be preserved even if they exceed max_length

    def test_smart_chunk_text_multiple_sentences(self):
        """Test chunking with multiple sentences."""
        text = "First sentence. Second sentence! Third sentence? Fourth sentence."
        chunks = smart_chunk_text(text, max_length=25)
        
        assert len(chunks) > 1
        # Should prefer breaking at sentence boundaries

    def test_adaptive_chunk_text_basic(self):
        """Test basic adaptive chunking."""
        text = "This is a test sentence for adaptive chunking algorithm."
        chunks = adaptive_chunk_text(text, target_seconds=30)
        
        assert len(chunks) >= 1
        assert "".join(chunks).strip() == text

    def test_adaptive_chunk_text_short(self):
        """Test adaptive chunking with short text."""
        text = "Short"
        chunks = adaptive_chunk_text(text, target_seconds=30)
        
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_adaptive_chunk_text_long(self):
        """Test adaptive chunking with long text."""
        text = "This is a very long text that should be chunked. " * 20
        chunks = adaptive_chunk_text(text, target_seconds=10)
        
        assert len(chunks) > 5
        assert all(len(chunk) > 0 for chunk in chunks)

    def test_adaptive_chunk_text_empty(self):
        """Test adaptive chunking with empty text."""
        chunks = adaptive_chunk_text("", target_seconds=30)
        assert chunks == [""]

    def test_adaptive_chunk_text_different_targets(self):
        """Test adaptive chunking with different target seconds."""
        text = "This is a test sentence. " * 10
        
        chunks_10 = adaptive_chunk_text(text, target_seconds=10)
        chunks_30 = adaptive_chunk_text(text, target_seconds=30)
        
        # Longer target should result in fewer chunks
        assert len(chunks_10) >= len(chunks_30)

    @pytest.mark.parametrize("max_length", [10, 50, 100, 200])
    def test_smart_chunk_text_various_lengths(self, max_length):
        """Test smart chunking with various max lengths."""
        text = "This is a longer text with multiple sentences. " * 5
        chunks = smart_chunk_text(text, max_length=max_length)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    @pytest.mark.parametrize("target_seconds", [5, 15, 30, 60])
    def test_adaptive_chunk_text_various_targets(self, target_seconds):
        """Test adaptive chunking with various target seconds."""
        text = "This is a test sentence for chunking. " * 10
        chunks = adaptive_chunk_text(text, target_seconds=target_seconds)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_chunk_preservation_smart(self):
        """Test that smart chunking preserves original text."""
        original = "Hello world! This is a test. How are you today?"
        chunks = smart_chunk_text(original, max_length=20)
        reconstructed = "".join(chunks)
        
        # Remove extra spaces that might be added
        assert reconstructed.strip() == original

    def test_chunk_preservation_adaptive(self):
        """Test that adaptive chunking preserves original text."""
        original = "Hello world! This is a test. How are you today?"
        chunks = adaptive_chunk_text(original, target_seconds=15)
        reconstructed = "".join(chunks)
        
        assert reconstructed.strip() == original

    def test_smart_chunk_text_georgian(self):
        """Test smart chunking with Georgian text."""
        text = "გამარჯობა მსოფლიო. ეს არის ტესტი."
        chunks = smart_chunk_text(text, max_length=20)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_adaptive_chunk_text_russian(self):
        """Test adaptive chunking with Russian text."""
        text = "Привет мир. Это тест системы."
        chunks = adaptive_chunk_text(text, target_seconds=20)
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)