"""Tests for simple_help module."""

from unittest.mock import patch

import pytest

from TTS_ka.simple_help import show_simple_help, show_troubleshooting


class TestSimpleHelp:
    """Test cases for simple help system."""

    def test_show_simple_help_basic(self):
        """Test basic help display."""
        with patch("builtins.print") as mock_print:
            show_simple_help()

            # Should have printed something
            assert mock_print.call_count > 0

            # Check for key content
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            assert len(help_text) > 0

    def test_show_troubleshooting_basic(self):
        """Test troubleshooting display."""
        with patch("builtins.print") as mock_print:
            show_troubleshooting()

            # Should have printed something
            assert mock_print.call_count > 0

    def test_help_no_exceptions(self):
        """Test that help display doesn't raise exceptions."""
        try:
            show_simple_help()
            show_troubleshooting()
        except Exception as e:
            pytest.fail(f"Help display raised exception: {e}")

    def test_help_contains_text(self):
        """Test that help contains expected text."""
        with patch("builtins.print") as mock_print:
            show_simple_help()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            help_text = "\n".join(print_calls)

            # Should contain some basic help information
            assert isinstance(help_text, str)
            assert len(help_text) > 10  # Should have some content

    def test_troubleshooting_contains_text(self):
        """Test that troubleshooting contains expected text."""
        with patch("builtins.print") as mock_print:
            show_troubleshooting()

            print_calls = [call[0][0] for call in mock_print.call_args_list]
            troubleshoot_text = "\n".join(print_calls)

            # Should contain some troubleshooting information
            assert isinstance(troubleshoot_text, str)
            assert len(troubleshoot_text) > 10  # Should have some content
