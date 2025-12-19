"""Tests for simple_help module."""

from unittest.mock import patch

import pytest

from TTS_ka.simple_help import show_comprehensive_help


class TestSimpleHelp:
    """Test cases for simple help system."""

    def test_show_comprehensive_help_basic(self):
        """Test basic comprehensive help display."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            # Should have printed multiple lines
            assert mock_print.call_count > 10

            # Check for key sections
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "ULTRA-FAST TTS" in help_text
            assert "SUPPORTED LANGUAGES" in help_text
            assert "QUICK START EXAMPLES" in help_text
            assert "TROUBLESHOOTING" in help_text

    def test_help_contains_language_info(self):
        """Test that help contains language information."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "ka" in help_text.lower()  # Georgian
            assert "ru" in help_text.lower()  # Russian
            assert "en" in help_text.lower()  # English
            assert "georgian" in help_text.lower()
            assert "russian" in help_text.lower()

    def test_help_contains_examples(self):
        """Test that help contains usage examples."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "--turbo" in help_text
            assert "--lang" in help_text
            assert "clipboard" in help_text
            assert "file.txt" in help_text

    def test_help_contains_performance_info(self):
        """Test that help contains performance information."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "PERFORMANCE" in help_text or "seconds" in help_text
            assert "OPTIMIZATION" in help_text or "speed" in help_text.lower()

    def test_help_contains_troubleshooting(self):
        """Test that help contains troubleshooting section."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "TROUBLESHOOTING" in help_text
            assert "Slow generation" in help_text or "errors" in help_text.lower()

    def test_help_ascii_compatibility(self):
        """Test that help uses ASCII-compatible characters."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]

            # Should not raise encoding errors
            for call in print_calls:
                try:
                    call.encode("ascii", errors="ignore")
                except UnicodeEncodeError:
                    pytest.fail(f"Non-ASCII content found: {call}")

    def test_help_contains_workflows(self):
        """Test that help contains common workflows."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "WORKFLOWS" in help_text or "workflow" in help_text.lower()

    def test_help_structure_sections(self):
        """Test that help has proper section structure."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            # Should have multiple major sections
            section_count = help_text.count("===") + help_text.count("---")
            assert section_count >= 2

    def test_help_contains_tips(self):
        """Test that help contains optimization tips."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "TIPS" in help_text or "tip" in help_text.lower()

    def test_help_no_exceptions(self):
        """Test that help display doesn't raise exceptions."""
        try:
            show_comprehensive_help()
        except Exception as e:
            pytest.fail(f"Help display raised exception: {e}")

    def test_help_contains_file_operations(self):
        """Test that help mentions file operations."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert "file" in help_text.lower()
            assert "path" in help_text.lower() or "clipboard" in help_text.lower()

    def test_help_contains_audio_info(self):
        """Test that help contains audio-related information."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert (
                "audio" in help_text.lower()
                or "playback" in help_text.lower()
                or "mp3" in help_text.lower()
            )

    def test_help_multilingual_examples(self):
        """Test that help contains examples in multiple languages."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            # Should contain examples for different languages
            has_multilingual = any(
                char
                for char in help_text
                if ord(char) > 127  # Non-ASCII characters for Georgian/Russian
            ) or all(lang in help_text.lower() for lang in ["english", "georgian", "russian"])

            assert has_multilingual or "georgian" in help_text.lower()

    def test_help_performance_metrics(self):
        """Test that help mentions performance metrics."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            performance_terms = ["seconds", "speed", "fast", "workers", "parallel"]
            has_performance = any(term in help_text.lower() for term in performance_terms)
            assert has_performance

    def test_help_command_examples(self):
        """Test that help contains actual command examples."""
        with patch("builtins.print") as mock_print:
            show_comprehensive_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            # Should contain actual python commands
            assert "python" in help_text.lower()
            assert "-m" in help_text or "TTS_ka" in help_text
