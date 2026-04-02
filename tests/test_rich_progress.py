"""Tests for rich_progress module."""

import pytest
import time
from unittest.mock import MagicMock, patch
from TTS_ka.rich_progress import (
    RichProgressDisplay,
    ProgressStats,
    create_progress_display,
    animate_loading,
    SPINNER_FRAMES,
    PULSE_FRAMES,
)


class TestProgressStats:
    def test_default_values(self):
        s = ProgressStats(total_chunks=5)
        assert s.total_chunks == 5
        assert s.completed_chunks == 0
        assert s.total_words == 0

    def test_custom_values(self):
        s = ProgressStats(total_chunks=10, total_words=200, completed_chunks=3)
        assert s.total_chunks == 10
        assert s.total_words == 200
        assert s.completed_chunks == 3


class TestRichProgressDisplay:
    """Tests for RichProgressDisplay class."""

    def test_init_with_tqdm(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', True), \
             patch('TTS_ka.rich_progress.tqdm') as mock_tqdm:
            mock_tqdm.return_value = MagicMock()
            display = RichProgressDisplay(total_chunks=5, total_words=100, language="en")
        assert display.stats.total_chunks == 5
        assert display.stats.total_words == 100
        assert display.language == "en"

    def test_init_without_tqdm(self, capsys):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=3, language="ka")
        assert display.use_tqdm is False
        assert "3 chunks" in capsys.readouterr().out

    def test_update_increments_completed(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=5, language="en")
        display.update(chunk_words=10)
        assert display.stats.completed_chunks == 1
        assert display.stats.processed_words == 10

    def test_update_multiple_times(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=5, language="en")
        for _ in range(3):
            display.update(chunk_words=5)
        assert display.stats.completed_chunks == 3
        assert display.stats.processed_words == 15

    def test_update_with_tqdm(self):
        mock_pbar = MagicMock()
        with patch('TTS_ka.rich_progress.HAS_TQDM', True), \
             patch('TTS_ka.rich_progress.tqdm', return_value=mock_pbar):
            display = RichProgressDisplay(total_chunks=5, language="en")
            display.update(chunk_words=20)
        mock_pbar.update.assert_called_once_with(1)
        mock_pbar.set_postfix_str.assert_called()

    def test_update_calculates_speed(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=5, total_words=50, language="en")
        display.stats.start_time = time.perf_counter() - 2.0
        display.update(chunk_words=10)
        assert display.stats.chunks_per_second > 0

    def test_finish_success(self, capsys):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=2, total_words=20, language="en")
        display.stats.completed_chunks = 2
        display.stats.processed_words = 20
        display.stats.start_time = time.perf_counter() - 1.0
        display.finish(success=True)
        out = capsys.readouterr().out
        assert "Completed" in out or "✅" in out

    def test_finish_failure(self, capsys):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=2, language="en")
        display.finish(success=False)
        assert "Failed" in capsys.readouterr().out or "❌" in capsys.readouterr().out

    def test_finish_with_tqdm_success(self):
        mock_pbar = MagicMock()
        with patch('TTS_ka.rich_progress.HAS_TQDM', True), \
             patch('TTS_ka.rich_progress.tqdm', return_value=mock_pbar):
            display = RichProgressDisplay(total_chunks=2, language="en")
            display.finish(success=True)
        mock_pbar.close.assert_called_once()

    def test_finish_with_tqdm_failure(self):
        mock_pbar = MagicMock()
        with patch('TTS_ka.rich_progress.HAS_TQDM', True), \
             patch('TTS_ka.rich_progress.tqdm', return_value=mock_pbar):
            display = RichProgressDisplay(total_chunks=2, language="en")
            display.finish(success=False)
        mock_pbar.close.assert_called_once()

    def test_get_postfix_stats_empty_when_no_speed(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=5, language="en")
        result = display._get_postfix_stats()
        assert isinstance(result, str)

    def test_get_postfix_stats_with_speed(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=5, total_words=50, language="en")
        display.stats.chunks_per_second = 2.5
        display.stats.words_per_second = 20.0
        display.stats.time_remaining = 10.0
        result = display._get_postfix_stats()
        assert "ch/s" in result
        assert "w/s" in result

    def test_language_flags(self):
        for lang, flag in [("ka", "🇬🇪"), ("ru", "🇷🇺"), ("en", "🇬🇧")]:
            with patch('TTS_ka.rich_progress.HAS_TQDM', True), \
                 patch('TTS_ka.rich_progress.tqdm') as mock_tqdm:
                mock_tqdm.return_value = MagicMock()
                display = RichProgressDisplay(total_chunks=1, language=lang)
            # tqdm desc should contain the flag
            call_kwargs = mock_tqdm.call_args[1] if mock_tqdm.call_args else {}
            desc = call_kwargs.get('desc', '')
            assert flag in desc

    def test_print_custom_progress(self, capsys):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = RichProgressDisplay(total_chunks=4, language="en")
        display.stats.completed_chunks = 2
        display._print_custom_progress()
        assert "50.0%" in capsys.readouterr().out


class TestCreateProgressDisplay:
    def test_creates_display(self):
        chunks = ["hello world", "foo bar baz"]
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = create_progress_display(chunks, language="en")
        assert display.stats.total_chunks == 2
        assert display.stats.total_words == 5  # 2 + 3

    def test_empty_chunks(self):
        with patch('TTS_ka.rich_progress.HAS_TQDM', False):
            display = create_progress_display([], language="ka")
        assert display.stats.total_chunks == 0


class TestAnimateLoading:
    def test_runs_without_error(self, capsys):
        # Patch time.sleep so test runs instantly
        with patch('time.sleep'), \
             patch('time.perf_counter', side_effect=[0.0, 0.0, 0.5, 1.0, 1.1]):
            animate_loading("Testing", duration=1.0)
        out = capsys.readouterr().out
        assert "Testing" in out

    def test_prints_complete(self, capsys):
        with patch('time.sleep'), \
             patch('time.perf_counter', side_effect=[0.0, 2.0]):
            animate_loading("Loading", duration=1.0)
        assert "complete" in capsys.readouterr().out.lower()


class TestConstants:
    def test_spinner_frames_non_empty(self):
        assert len(SPINNER_FRAMES) > 0

    def test_pulse_frames_non_empty(self):
        assert len(PULSE_FRAMES) > 0
