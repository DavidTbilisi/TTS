"""Tests for chunking module."""

import pytest
from TTS_ka.chunking import split_text_into_chunks, should_chunk_text


class TestSplitTextIntoChunks:
    def test_basic_split(self):
        text = "Hello world. This is a test. Another sentence here."
        chunks = split_text_into_chunks(text, approx_seconds=30)
        assert len(chunks) >= 1
        assert all(isinstance(c, str) for c in chunks)

    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = split_text_into_chunks(text, approx_seconds=60)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        text = "word " * 500
        chunks = split_text_into_chunks(text, approx_seconds=10)
        assert len(chunks) > 1

    def test_all_words_preserved(self):
        text = "The quick brown fox jumps over the lazy dog"
        chunks = split_text_into_chunks(text, approx_seconds=60)
        reconstructed = " ".join(chunks)
        assert set(reconstructed.split()) == set(text.split())
        assert len(reconstructed.split()) == len(text.split())

    def test_empty_text(self):
        chunks = split_text_into_chunks("", approx_seconds=30)
        assert chunks == []

    def test_whitespace_only(self):
        chunks = split_text_into_chunks("   ", approx_seconds=30)
        assert chunks == []

    def test_chunk_size_respected(self):
        # At 160 WPM = 2.67 w/s, 10s ≈ 26-27 words per chunk
        text = "word " * 200
        chunks = split_text_into_chunks(text, approx_seconds=10)
        # Each chunk should not have drastically more words than target
        for chunk in chunks:
            word_count = len(chunk.split())
            assert word_count <= 50  # generous upper bound

    def test_approx_seconds_affects_chunk_count(self):
        text = "word " * 200
        chunks_10 = split_text_into_chunks(text, approx_seconds=10)
        chunks_60 = split_text_into_chunks(text, approx_seconds=60)
        assert len(chunks_10) >= len(chunks_60)

    def test_georgian_text(self):
        text = "გამარჯობა მსოფლიო. ეს არის ტესტი. " * 5
        chunks = split_text_into_chunks(text, approx_seconds=5)
        assert len(chunks) >= 1

    def test_russian_text(self):
        text = "Привет мир это тест. " * 10
        chunks = split_text_into_chunks(text, approx_seconds=5)
        assert len(chunks) >= 1

    def test_single_word(self):
        chunks = split_text_into_chunks("Hello", approx_seconds=30)
        assert len(chunks) == 1
        assert chunks[0] == "Hello"

    @pytest.mark.parametrize("approx_seconds", [5, 15, 30, 60, 120])
    def test_various_approx_seconds(self, approx_seconds):
        text = "This is a test sentence. " * 20
        chunks = split_text_into_chunks(text, approx_seconds=approx_seconds)
        assert len(chunks) >= 1
        assert all(c.strip() for c in chunks)


class TestShouldChunkText:
    def test_chunk_seconds_zero_returns_false(self):
        assert should_chunk_text("any text", chunk_seconds=0) is False

    def test_chunk_seconds_positive_returns_true(self):
        assert should_chunk_text("any text", chunk_seconds=30) is True

    def test_chunk_seconds_negative_returns_false(self):
        # Negative means "auto", not user-requested
        assert should_chunk_text("any text", chunk_seconds=-1) is False

    def test_ignores_text_length(self):
        long_text = "word " * 1000
        assert should_chunk_text(long_text, chunk_seconds=0) is False
        assert should_chunk_text(long_text, chunk_seconds=30) is True

    def test_default_chunk_seconds(self):
        # Default is 0
        assert should_chunk_text("some text") is False
