"""Tests for rich_progress module."""

import pytest
import time
from unittest.mock import MagicMock, patch
from TTS_ka.rich_progress import ProgressTracker


class TestProgressTracker:
    """Test cases for ProgressTracker class."""

    def test_progress_tracker_init(self):
        """Test ProgressTracker initialization."""
        tracker = ProgressTracker(total=10, language="en")
        
        assert tracker.total == 10
        assert tracker.language == "en"
        assert tracker.completed == 0
        assert tracker.start_time is not None

    def test_progress_tracker_get_flag_en(self):
        """Test flag emoji for English."""
        tracker = ProgressTracker(total=5, language="en")
        flag = tracker._get_flag()
        assert flag == "🇬🇧"

    def test_progress_tracker_get_flag_ka(self):
        """Test flag emoji for Georgian."""
        tracker = ProgressTracker(total=5, language="ka")
        flag = tracker._get_flag()
        assert flag == "🇬🇪"

    def test_progress_tracker_get_flag_ru(self):
        """Test flag emoji for Russian."""
        tracker = ProgressTracker(total=5, language="ru")
        flag = tracker._get_flag()
        assert flag == "🇷🇺"

    def test_progress_tracker_get_flag_unknown(self):
        """Test flag emoji for unknown language."""
        tracker = ProgressTracker(total=5, language="unknown")
        flag = tracker._get_flag()
        assert flag == "🌐"

    def test_progress_tracker_update_basic(self):
        """Test basic progress update."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            tracker = ProgressTracker(total=5, language="en")
            tracker.update()
            
            assert tracker.completed == 1
            mock_pbar.update.assert_called_once_with(1)

    def test_progress_tracker_update_with_words(self):
        """Test progress update with word count."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            tracker = ProgressTracker(total=5, language="en")
            tracker.update(words_processed=10)
            
            assert tracker.completed == 1
            assert tracker.total_words == 10

    def test_progress_tracker_calculate_stats(self):
        """Test statistics calculation."""
        tracker = ProgressTracker(total=10, language="en")
        tracker.completed = 5
        tracker.total_words = 100
        tracker.start_time = time.time() - 10  # 10 seconds ago
        
        stats = tracker._calculate_stats()
        
        assert "ch/s" in stats
        assert "w/s" in stats
        assert "⏱️" in stats

    def test_progress_tracker_estimate_time(self):
        """Test ETA estimation."""
        tracker = ProgressTracker(total=10, language="en")
        tracker.completed = 2
        tracker.start_time = time.time() - 5  # 5 seconds ago
        
        eta = tracker._estimate_time()
        
        assert isinstance(eta, (int, float))
        assert eta > 0

    def test_progress_tracker_estimate_time_no_progress(self):
        """Test ETA estimation with no progress."""
        tracker = ProgressTracker(total=10, language="en")
        tracker.completed = 0
        
        eta = tracker._estimate_time()
        
        assert eta == 0

    def test_progress_tracker_format_time_seconds(self):
        """Test time formatting for seconds."""
        tracker = ProgressTracker(total=5, language="en")
        
        formatted = tracker._format_time(45)
        assert formatted == "45"

    def test_progress_tracker_format_time_minutes(self):
        """Test time formatting for minutes."""
        tracker = ProgressTracker(total=5, language="en")
        
        formatted = tracker._format_time(125)
        assert "2m" in formatted

    def test_progress_tracker_context_manager(self):
        """Test ProgressTracker as context manager."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            mock_tqdm.return_value.__exit__.return_value = None
            
            with ProgressTracker(total=5, language="en") as tracker:
                assert tracker is not None
                tracker.update()
            
            mock_tqdm.assert_called_once()

    def test_progress_tracker_fallback_mode(self):
        """Test ProgressTracker fallback when tqdm fails."""
        with patch('tqdm.tqdm', side_effect=ImportError("tqdm not available")):
            tracker = ProgressTracker(total=5, language="en")
            
            # Should not raise exception
            tracker.update()
            assert tracker.completed == 1

    def test_progress_tracker_final_stats(self):
        """Test final statistics display."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            tracker = ProgressTracker(total=5, language="en")
            tracker.total_words = 50
            tracker.completed = 5
            tracker.start_time = time.time() - 10
            
            with patch('builtins.print') as mock_print:
                tracker.show_final_stats()
                
            mock_print.assert_called()

    def test_progress_tracker_multiple_updates(self):
        """Test multiple progress updates."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            tracker = ProgressTracker(total=5, language="en")
            
            for i in range(3):
                tracker.update(words_processed=10)
            
            assert tracker.completed == 3
            assert tracker.total_words == 30

    @pytest.mark.parametrize("language,expected_flag", [
        ("en", "🇬🇧"),
        ("ka", "🇬🇪"), 
        ("ru", "🇷🇺"),
        ("fr", "🌐"),
        ("", "🌐"),
        (None, "🌐")
    ])
    def test_progress_tracker_flags(self, language, expected_flag):
        """Test flag selection for various languages."""
        tracker = ProgressTracker(total=5, language=language)
        flag = tracker._get_flag()
        assert flag == expected_flag

    def test_progress_tracker_performance_calculation(self):
        """Test performance metrics calculation."""
        tracker = ProgressTracker(total=10, language="en")
        tracker.completed = 8
        tracker.total_words = 160
        tracker.start_time = time.time() - 20  # 20 seconds ago
        
        stats = tracker._calculate_stats()
        
        # Should contain performance metrics
        assert any("ch/s" in stats for stats in [stats])
        assert any("w/s" in stats for stats in [stats])

    def test_progress_tracker_edge_cases(self):
        """Test edge cases for ProgressTracker."""
        # Zero total
        tracker = ProgressTracker(total=0, language="en")
        tracker.update()
        assert tracker.completed == 1

        # Negative total
        tracker = ProgressTracker(total=-1, language="en")
        tracker.update()
        assert tracker.completed == 1

    def test_progress_tracker_unicode_compatibility(self):
        """Test Unicode compatibility in progress display."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            # Test with Georgian text
            tracker = ProgressTracker(total=5, language="ka")
            tracker.update()
            
            # Should handle Unicode without errors
            assert tracker.completed == 1

    def test_progress_tracker_description_update(self):
        """Test progress bar description updates."""
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            tracker = ProgressTracker(total=5, language="en")
            tracker.update(words_processed=25)
            
            # Should update description with stats
            mock_pbar.set_description.assert_called()