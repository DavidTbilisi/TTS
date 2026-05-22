"""Tests for rich_progress module."""

import time
from unittest.mock import MagicMock, patch

from TTS_ka.rich_progress import (
    LANG_FLAG,
    ProgressStats,
    RichProgressDisplay,
    create_progress_display,
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

    def _make_display(self, total_chunks=5, total_words=50, language="en"):
        """Create a display with all UI backends mocked out."""
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0
        with patch("TTS_ka.rich_progress.HAS_RICH", True), \
             patch("TTS_ka.rich_progress.Progress", return_value=mock_progress):
            d = RichProgressDisplay(total_chunks=total_chunks, total_words=total_words, language=language)
        return d, mock_progress

    def test_init_stores_stats(self):
        d, _ = self._make_display(total_chunks=5, total_words=100)
        assert d.stats.total_chunks == 5
        assert d.stats.total_words == 100

    def test_init_no_rich_no_tqdm_prints_fallback(self, capsys):
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", False):
            RichProgressDisplay(total_chunks=3, language="ka")
        combined = capsys.readouterr().out + capsys.readouterr().err
        # Fallback prints to stderr; captured.err has the message
        # (we just verify it doesn't crash)

    def test_update_increments_completed(self):
        d, _ = self._make_display(total_chunks=5)
        d.update(chunk_words=10)
        assert d.stats.completed_chunks == 1
        assert d.stats.processed_words == 10

    def test_update_multiple_times(self):
        d, _ = self._make_display(total_chunks=5)
        for _ in range(3):
            d.update(chunk_words=5)
        assert d.stats.completed_chunks == 3
        assert d.stats.processed_words == 15

    def test_update_with_tqdm_pbar(self):
        """When tqdm is active (rich absent), update calls pbar methods."""
        mock_pbar = MagicMock()
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", True), \
             patch("TTS_ka.rich_progress.tqdm", return_value=mock_pbar):
            d = RichProgressDisplay(total_chunks=5, language="en")
            d.update(chunk_words=20)
        mock_pbar.update.assert_called_once_with(1)
        mock_pbar.set_postfix_str.assert_called()

    def test_update_calculates_speed(self):
        d, _ = self._make_display(total_chunks=5, total_words=50)
        d.stats.start_time = time.perf_counter() - 2.0
        d.update(chunk_words=10)
        assert d.stats.chunks_per_second > 0

    def test_finish_success_rich(self, capsys):
        """finish(success=True) stops progress and prints completion line."""
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0
        with patch("TTS_ka.rich_progress.HAS_RICH", True), \
             patch("TTS_ka.rich_progress.Progress", return_value=mock_progress), \
             patch("TTS_ka.rich_progress.console") as mock_console:
            d = RichProgressDisplay(total_chunks=2, total_words=20, language="en")
            d.stats.start_time = time.perf_counter() - 1.0
            d.stats.processed_words = 20
            d.finish(success=True)
        mock_progress.stop.assert_called_once()
        mock_console.print.assert_called()
        printed = mock_console.print.call_args[0][0]
        assert "Completed" in printed

    def test_finish_failure_rich(self, capsys):
        """finish(success=False) shows failure message."""
        mock_progress = MagicMock()
        mock_progress.add_task.return_value = 0
        with patch("TTS_ka.rich_progress.HAS_RICH", True), \
             patch("TTS_ka.rich_progress.Progress", return_value=mock_progress), \
             patch("TTS_ka.rich_progress.console") as mock_console:
            d = RichProgressDisplay(total_chunks=2, language="en")
            d.finish(success=False)
        mock_progress.stop.assert_called_once()
        printed = mock_console.print.call_args[0][0]
        assert "failed" in printed.lower() or "✗" in printed

    def test_finish_with_tqdm_success(self):
        mock_pbar = MagicMock()
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", True), \
             patch("TTS_ka.rich_progress.tqdm", return_value=mock_pbar):
            d = RichProgressDisplay(total_chunks=2, language="en")
            d.finish(success=True)
        mock_pbar.close.assert_called_once()

    def test_finish_with_tqdm_failure(self):
        mock_pbar = MagicMock()
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", True), \
             patch("TTS_ka.rich_progress.tqdm", return_value=mock_pbar):
            d = RichProgressDisplay(total_chunks=2, language="en")
            d.finish(success=False)
        mock_pbar.close.assert_called_once()

    def test_language_flags_dict(self):
        assert LANG_FLAG["ka"] == "🇬🇪"
        assert LANG_FLAG["ka-m"] == "🇬🇪"
        assert LANG_FLAG["ru"] == "🇷🇺"
        assert LANG_FLAG["en"] == "🇬🇧"

    def test_language_flag_used_in_tqdm_desc(self):
        """When using tqdm, the language flag appears in the description."""
        for lang, flag in [("ka", "🇬🇪"), ("ru", "🇷🇺"), ("en", "🇬🇧")]:
            mock_pbar = MagicMock()
            with patch("TTS_ka.rich_progress.HAS_RICH", False), \
                 patch("TTS_ka.rich_progress.HAS_TQDM", True), \
                 patch("TTS_ka.rich_progress.tqdm", return_value=mock_pbar) as mt:
                RichProgressDisplay(total_chunks=1, language=lang)
            call_kwargs = mt.call_args[1] if mt.call_args else {}
            desc = call_kwargs.get("desc", "")
            assert flag in desc, f"Expected {flag} in tqdm desc for lang={lang}"

    def test_print_fallback_writes_to_stderr(self, capsys):
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", False):
            d = RichProgressDisplay(total_chunks=4, language="en")
        d.stats.completed_chunks = 2
        d._print_fallback()
        err = capsys.readouterr().err
        assert "50.0%" in err


class TestCreateProgressDisplay:
    def test_creates_display(self):
        chunks = ["hello world", "foo bar baz"]
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", False):
            d = create_progress_display(chunks, language="en")
        assert d.stats.total_chunks == 2
        assert d.stats.total_words == 5  # 2 + 3

    def test_empty_chunks(self):
        with patch("TTS_ka.rich_progress.HAS_RICH", False), \
             patch("TTS_ka.rich_progress.HAS_TQDM", False):
            d = create_progress_display([], language="ka")
        assert d.stats.total_chunks == 0
