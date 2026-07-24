"""Tests for study_session — pure-logic state machine."""

import pytest

from TTS_ka.study_session import StudySession, DEFAULT_CHUNK_WORDS
from TTS_ka.subtitles import WordEvent


def _events(*pairs):
    """Helper: build WordEvents from (text, start_ms, duration_ms) tuples."""
    return [WordEvent(text=t, start_ms=s, duration_ms=d) for t, s, d in pairs]


class TestStudySession:
    def test_empty_session(self):
        s = StudySession([])
        assert s.total_duration_ms == 0
        assert s.wpm == 0.0
        assert s.current_word_at(0) is None
        assert s.current_word_index(500) == -1
        assert s.chunk_boundaries() == []
        assert s.chunk_text(0) == ""

    def test_rejects_non_positive_chunk_size(self):
        with pytest.raises(ValueError):
            StudySession([], chunk_size_words=0)
        with pytest.raises(ValueError):
            StudySession([], chunk_size_words=-5)

    def test_current_word_lookup_basic(self):
        s = StudySession(_events(("hello", 0, 300), ("world", 300, 400), ("now", 700, 300)))
        assert s.current_word_at(0).text == "hello"
        assert s.current_word_at(200).text == "hello"
        assert s.current_word_at(300).text == "world"
        assert s.current_word_at(699).text == "world"
        assert s.current_word_at(700).text == "now"
        assert s.current_word_at(10_000).text == "now"  # sticks on last word

    def test_current_word_before_start(self):
        # pos_ms before the first word's start_ms returns no current word.
        s = StudySession(_events(("a", 50, 100), ("b", 200, 100)))
        assert s.current_word_index(0) == -1
        assert s.current_word_at(49) is None

    def test_peripheral_window(self):
        s = StudySession(_events(
            ("w0", 0, 100), ("w1", 100, 100), ("w2", 200, 100),
            ("w3", 300, 100), ("w4", 400, 100),
        ))
        view = s.peripheral(220, span=2)
        assert view.current.text == "w2"
        assert [e.text for e in view.prev] == ["w0", "w1"]
        assert [e.text for e in view.next] == ["w3", "w4"]

    def test_peripheral_clamps_at_edges(self):
        s = StudySession(_events(("a", 0, 100), ("b", 100, 100), ("c", 200, 100)))
        left = s.peripheral(0, span=3)
        assert [e.text for e in left.prev] == []
        right = s.peripheral(200, span=3)
        assert [e.text for e in right.next] == []

    def test_total_duration_and_wpm(self):
        # 60 words spanning 30s → 120 wpm.
        evs = [WordEvent(text=f"w{i}", start_ms=i * 500, duration_ms=500) for i in range(60)]
        s = StudySession(evs)
        assert s.total_duration_ms == 60 * 500
        assert s.wpm == pytest.approx(120.0, rel=1e-6)

    def test_chunk_boundaries(self):
        evs = [WordEvent(text=f"w{i}", start_ms=i, duration_ms=1) for i in range(450)]
        s = StudySession(evs, chunk_size_words=200)
        bounds = s.chunk_boundaries()
        assert bounds == [(0, 200), (200, 400), (400, 450)]

    def test_chunk_index_at(self):
        evs = [WordEvent(text=f"w{i}", start_ms=i * 10, duration_ms=10) for i in range(20)]
        s = StudySession(evs, chunk_size_words=5)
        assert s.chunk_index_at(0) == 0
        assert s.chunk_index_at(45) == 0   # word index 4
        assert s.chunk_index_at(50) == 1   # word index 5 → chunk 1
        assert s.chunk_index_at(190) == 3  # word index 19 → chunk 3

    def test_chunk_text_round_trip(self):
        words = ["the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog"]
        evs = [WordEvent(text=w, start_ms=i * 100, duration_ms=100) for i, w in enumerate(words)]
        s = StudySession(evs, chunk_size_words=4)
        assert s.chunk_text(0) == "the quick brown fox"
        assert s.chunk_text(1) == "jumps over lazy dog"
        assert s.chunk_text(99) == ""

    def test_chunk_start_and_end_ms(self):
        evs = [WordEvent(text=f"w{i}", start_ms=i * 100, duration_ms=100) for i in range(10)]
        s = StudySession(evs, chunk_size_words=3)
        assert s.chunk_start_ms(0) == 0
        assert s.chunk_start_ms(1) == 300
        assert s.chunk_end_ms(0) == 300  # words 0..2 → last end_ms = 200+100

    def test_default_chunk_size_constant(self):
        # Sanity-check that the documented default did not silently drift.
        assert DEFAULT_CHUNK_WORDS == 200
