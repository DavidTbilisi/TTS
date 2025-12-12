"""Tests for main module CLI functionality."""

import pytest
import sys
import argparse
from unittest.mock import MagicMock, patch, AsyncMock
from io import StringIO
from TTS_ka.main import create_parser, main


class TestMain:
    """Test cases for main CLI functionality."""

    def test_create_parser_basic(self):
        """Test basic parser creation."""
        parser = create_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_create_parser_help_text(self):
        """Test parser help text contains expected elements."""
        parser = create_parser()
        help_text = parser.format_help()
        
        assert "Ultra-Fast TTS" in help_text
        assert "--lang" in help_text
        assert "--turbo" in help_text
        assert "ka,ru,en" in help_text

    def test_parse_args_default(self):
        """Test parsing with default arguments."""
        parser = create_parser()
        args = parser.parse_args(["test text"])
        
        assert args.text == "test text"
        assert args.lang == "en"  # Default language
        assert args.turbo == False
        assert args.no_play == False

    def test_parse_args_georgian(self):
        """Test parsing with Georgian language."""
        parser = create_parser()
        args = parser.parse_args(["გამარჯობა", "--lang", "ka"])
        
        assert args.text == "გამარჯობა"
        assert args.lang == "ka"

    def test_parse_args_russian(self):
        """Test parsing with Russian language."""
        parser = create_parser()
        args = parser.parse_args(["Привет", "--lang", "ru"])
        
        assert args.text == "Привет"
        assert args.lang == "ru"

    def test_parse_args_turbo_mode(self):
        """Test parsing with turbo mode."""
        parser = create_parser()
        args = parser.parse_args(["test", "--turbo"])
        
        assert args.turbo == True

    def test_parse_args_no_play(self):
        """Test parsing with no-play option."""
        parser = create_parser()
        args = parser.parse_args(["test", "--no-play"])
        
        assert args.no_play == True

    def test_parse_args_parallel_workers(self):
        """Test parsing with parallel workers."""
        parser = create_parser()
        args = parser.parse_args(["test", "--parallel", "4"])
        
        assert args.parallel == 4

    def test_parse_args_chunk_seconds(self):
        """Test parsing with chunk seconds."""
        parser = create_parser()
        args = parser.parse_args(["test", "--chunk-seconds", "30"])
        
        assert args.chunk_seconds == 30

    def test_parse_args_help_full(self):
        """Test parsing help-full flag."""
        parser = create_parser()
        args = parser.parse_args(["test", "--help-full"])
        
        assert args.help_full == True

    def test_parse_args_invalid_language(self):
        """Test parsing with invalid language."""
        parser = create_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["test", "--lang", "invalid"])

    @pytest.mark.asyncio
    async def test_main_simple_text(self, temp_dir):
        """Test main function with simple text."""
        test_args = ["test_script", "Hello world", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                mock_generate.return_value = True
                
                with patch('TTS_ka.main.validate_language') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('builtins.print') as mock_print:
                        await main()
                
                mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_clipboard_input(self):
        """Test main function with clipboard input."""
        test_args = ["test_script", "clipboard", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('pyperclip.paste') as mock_paste:
                mock_paste.return_value = "clipboard text"
                
                with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                    mock_generate.return_value = True
                    
                    with patch('TTS_ka.main.validate_language') as mock_validate:
                        mock_validate.return_value = True
                        
                        with patch('builtins.print') as mock_print:
                            await main()
                
                mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_file_input(self, sample_text_file):
        """Test main function with file input."""
        test_args = ["test_script", sample_text_file, "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                mock_generate.return_value = True
                
                with patch('TTS_ka.main.validate_language') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('builtins.print') as mock_print:
                        await main()
                
                mock_generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_invalid_language(self):
        """Test main function with invalid language."""
        test_args = ["test_script", "test", "--lang", "fr"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.validate_language') as mock_validate:
                mock_validate.return_value = False
                
                with patch('builtins.print') as mock_print:
                    with pytest.raises(SystemExit):
                        await main()

    @pytest.mark.asyncio 
    async def test_main_file_not_found(self):
        """Test main function with non-existent file."""
        test_args = ["test_script", "nonexistent.txt", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.validate_language') as mock_validate:
                mock_validate.return_value = True
                
                with patch('builtins.print') as mock_print:
                    with pytest.raises(SystemExit):
                        await main()

    @pytest.mark.asyncio
    async def test_main_help_full(self):
        """Test main function with help-full flag."""
        test_args = ["test_script", "test", "--help-full"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.show_comprehensive_help') as mock_help:
                with pytest.raises(SystemExit):
                    await main()
                
                mock_help.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_generation_failure(self):
        """Test main function when generation fails."""
        test_args = ["test_script", "test", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                mock_generate.return_value = False
                
                with patch('TTS_ka.main.validate_language') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('builtins.print') as mock_print:
                        with pytest.raises(SystemExit):
                            await main()

    @pytest.mark.asyncio
    async def test_main_audio_playback(self, temp_dir):
        """Test main function with audio playback."""
        test_args = ["test_script", "test", "--turbo"]  # No --no-play
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                mock_generate.return_value = True
                
                with patch('TTS_ka.main.validate_language') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('TTS_ka.main.play_audio') as mock_play:
                        with patch('builtins.print') as mock_print:
                            await main()
                        
                        mock_play.assert_called_once()

    def test_main_word_count_calculation(self):
        """Test word count calculation for different texts."""
        from TTS_ka.main import count_words
        
        assert count_words("Hello world") == 2
        assert count_words("One") == 1
        assert count_words("") == 0
        assert count_words("Word1 word2 word3") == 3

    @pytest.mark.parametrize("text_input,expected_words", [
        ("Hello world", 2),
        ("Single", 1), 
        ("", 0),
        ("One two three four five", 5),
        ("გამარჯობა მსოფლიო", 2),
        ("Привет мир тест", 3)
    ])
    def test_word_counting_various_inputs(self, text_input, expected_words):
        """Test word counting with various inputs."""
        from TTS_ka.main import count_words
        result = count_words(text_input)
        assert result == expected_words

    @pytest.mark.asyncio
    async def test_main_performance_display(self):
        """Test performance metrics display."""
        test_args = ["test_script", "Hello world test", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_generate:
                mock_generate.return_value = True
                
                with patch('TTS_ka.main.validate_language') as mock_validate:
                    mock_validate.return_value = True
                    
                    with patch('time.time') as mock_time:
                        mock_time.side_effect = [1000.0, 1002.5]  # 2.5 second duration
                        
                        with patch('builtins.print') as mock_print:
                            await main()
                        
                        # Should print performance info
                        print_calls = [call[0][0] for call in mock_print.call_args_list]
                        performance_printed = any("⚡ Completed" in call for call in print_calls)
                        assert performance_printed

    @pytest.mark.asyncio
    async def test_main_different_strategies(self):
        """Test main function with different generation strategies."""
        # Test both turbo and non-turbo modes
        for turbo_flag in [True, False]:
            test_args = ["test_script", "test text"]
            if turbo_flag:
                test_args.append("--turbo")
            test_args.append("--no-play")
            
            with patch('sys.argv', test_args):
                with patch('TTS_ka.main.generate_tts_turbo') as mock_turbo:
                    with patch('TTS_ka.main.generate_audio_ultra_fast') as mock_regular:
                        mock_turbo.return_value = True
                        mock_regular.return_value = True
                        
                        with patch('TTS_ka.main.validate_language') as mock_validate:
                            mock_validate.return_value = True
                            
                            with patch('builtins.print'):
                                await main()
                        
                        if turbo_flag:
                            mock_turbo.assert_called_once()
                        else:
                            mock_regular.assert_called_once()