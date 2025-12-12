"""Integration tests for TTS system."""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import patch, MagicMock


class TestTTSIntegration:
    """Integration test cases for the complete TTS system."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_english_generation(self, temp_dir):
        """Test complete English TTS generation flow."""
        from TTS_ka.main import main
        
        test_args = ["test_script", "Hello world integration test", "--lang", "en", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_audio_ultra_fast') as mock_generate:
                mock_generate.return_value = True
                
                with patch('builtins.print') as mock_print:
                    await main()
                
                # Should have called audio generation
                mock_generate.assert_called_once()
                
                # Should have printed completion message
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("Completed" in call for call in print_calls)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_georgian_turbo(self, temp_dir):
        """Test complete Georgian TTS with turbo mode."""
        from TTS_ka.main import main
        
        test_args = ["test_script", "გამარჯობა მსოფლიო", "--lang", "ka", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_turbo:
                mock_turbo.return_value = True
                
                with patch('builtins.print') as mock_print:
                    await main()
                
                # Should use turbo generation
                mock_turbo.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_end_to_end_russian_chunking(self, temp_dir):
        """Test complete Russian TTS with chunking."""
        from TTS_ka.main import main
        
        long_text = "Это очень длинный текст для тестирования системы. " * 20
        test_args = ["test_script", long_text, "--lang", "ru", "--turbo", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_tts_turbo') as mock_turbo:
                mock_turbo.return_value = True
                
                with patch('TTS_ka.ultra_fast.determine_strategy') as mock_strategy:
                    mock_strategy.return_value = ("smart generation", 5, 4)
                    
                    with patch('builtins.print'):
                        await main()
                
                mock_turbo.assert_called_once()

    @pytest.mark.integration
    def test_cli_help_integration(self):
        """Test CLI help system integration."""
        from TTS_ka.main import create_parser
        
        parser = create_parser()
        
        # Test that parser can handle all expected arguments
        test_cases = [
            ["test text"],
            ["test text", "--lang", "ka"],
            ["test text", "--turbo"],
            ["test text", "--no-play"],
            ["test text", "--parallel", "4"],
            ["test text", "--chunk-seconds", "30"]
        ]
        
        for args in test_cases:
            try:
                parsed = parser.parse_args(args)
                assert parsed is not None
            except SystemExit:
                pytest.fail(f"Parser failed for args: {args}")

    @pytest.mark.integration
    def test_chunking_integration(self):
        """Test text chunking integration with different sizes."""
        from TTS_ka.chunking import smart_chunk_text, adaptive_chunk_text
        
        test_texts = [
            "Short text",
            "Medium length text with multiple sentences. This should be chunked appropriately.",
            "Very long text that definitely needs chunking. " * 50
        ]
        
        for text in test_texts:
            # Test smart chunking
            smart_chunks = smart_chunk_text(text, max_length=100)
            assert len(smart_chunks) >= 1
            assert all(isinstance(chunk, str) for chunk in smart_chunks)
            
            # Test adaptive chunking
            adaptive_chunks = adaptive_chunk_text(text, target_seconds=30)
            assert len(adaptive_chunks) >= 1
            assert all(isinstance(chunk, str) for chunk in adaptive_chunks)

    @pytest.mark.integration
    def test_language_validation_integration(self):
        """Test language validation across modules."""
        from TTS_ka.fast_audio import validate_language, get_voice_for_language
        
        valid_languages = ["ka", "ru", "en"]
        invalid_languages = ["fr", "de", "zh", "invalid"]
        
        # Test validation
        for lang in valid_languages:
            assert validate_language(lang) == True
            voice = get_voice_for_language(lang)
            assert voice is not None
            assert isinstance(voice, str)
        
        for lang in invalid_languages:
            assert validate_language(lang) == False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_audio_generation_pipeline(self, temp_dir):
        """Test complete audio generation pipeline."""
        from TTS_ka.ultra_fast import generate_tts_turbo
        from TTS_ka.chunking import smart_chunk_text
        
        text = "Integration test for audio generation pipeline."
        output_path = os.path.join(temp_dir, "integration_test.mp3")
        
        # Mock the actual audio generation
        with patch('TTS_ka.fast_audio.generate_audio_ultra_fast') as mock_gen:
            mock_gen.return_value = True
            
            result = await generate_tts_turbo(text, output_path, "en", max_workers=2)
        
        assert result == True

    @pytest.mark.integration
    def test_progress_tracking_integration(self, temp_dir):
        """Test progress tracking integration."""
        from TTS_ka.rich_progress import ProgressTracker
        
        with patch('tqdm.tqdm') as mock_tqdm:
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__.return_value = mock_pbar
            
            # Test progress tracking workflow
            with ProgressTracker(total=5, language="en") as progress:
                for i in range(5):
                    progress.update(words_processed=10)
                
                progress.show_final_stats()
            
            # Should have updated progress 5 times
            assert mock_pbar.update.call_count == 5

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_clipboard_integration(self, temp_dir):
        """Test clipboard integration flow."""
        from TTS_ka.main import main
        
        test_args = ["test_script", "clipboard", "--lang", "en", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('pyperclip.paste') as mock_paste:
                mock_paste.return_value = "Clipboard content for integration test"
                
                with patch('TTS_ka.main.generate_audio_ultra_fast') as mock_gen:
                    mock_gen.return_value = True
                    
                    with patch('builtins.print'):
                        await main()
                
                mock_gen.assert_called_once()
                # Should have used clipboard content
                call_args = mock_gen.call_args[0]
                assert "Clipboard content" in call_args[0]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_file_input_integration(self, sample_text_file):
        """Test file input integration flow."""
        from TTS_ka.main import main
        
        test_args = ["test_script", sample_text_file, "--lang", "en", "--no-play"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.generate_audio_ultra_fast') as mock_gen:
                mock_gen.return_value = True
                
                with patch('builtins.print'):
                    await main()
            
            mock_gen.assert_called_once()
            # Should have read file content
            call_args = mock_gen.call_args[0]
            assert len(call_args[0]) > 0

    @pytest.mark.integration
    def test_error_handling_integration(self):
        """Test error handling across the system."""
        from TTS_ka.main import main
        
        # Test invalid language
        test_args = ["test_script", "test", "--lang", "invalid"]
        
        with patch('sys.argv', test_args):
            with patch('TTS_ka.main.validate_language') as mock_validate:
                mock_validate.return_value = False
                
                with pytest.raises(SystemExit):
                    asyncio.run(main())

    @pytest.mark.integration
    @pytest.mark.slow
    def test_performance_benchmarks(self):
        """Test performance benchmarks for different text sizes."""
        import time
        from TTS_ka.chunking import smart_chunk_text
        
        test_cases = [
            ("Small", "Hello world"),
            ("Medium", "This is a medium text. " * 10),
            ("Large", "This is a large text for testing. " * 100)
        ]
        
        for name, text in test_cases:
            start_time = time.time()
            chunks = smart_chunk_text(text, max_length=100)
            end_time = time.time()
            
            duration = end_time - start_time
            
            # Chunking should be fast (under 1 second even for large text)
            assert duration < 1.0, f"{name} text chunking took too long: {duration}s"
            assert len(chunks) >= 1

    @pytest.mark.integration
    def test_unicode_handling_integration(self):
        """Test Unicode handling across the system."""
        from TTS_ka.chunking import smart_chunk_text
        from TTS_ka.fast_audio import get_voice_for_language
        
        unicode_texts = [
            "გამარჯობა მსოფლიო",  # Georgian
            "Привет мир",         # Russian  
            "Hello world 🌍",     # English with emoji
        ]
        
        for text in unicode_texts:
            # Should handle Unicode text without errors
            chunks = smart_chunk_text(text, max_length=50)
            assert len(chunks) >= 1
            assert all(isinstance(chunk, str) for chunk in chunks)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, temp_dir):
        """Test concurrent TTS operations."""
        from TTS_ka.ultra_fast import generate_tts_turbo
        
        texts = [
            "First concurrent text",
            "Second concurrent text", 
            "Third concurrent text"
        ]
        
        with patch('TTS_ka.fast_audio.generate_audio_ultra_fast') as mock_gen:
            mock_gen.return_value = True
            
            # Run multiple TTS operations concurrently
            tasks = []
            for i, text in enumerate(texts):
                output_path = os.path.join(temp_dir, f"concurrent_{i}.mp3")
                task = generate_tts_turbo(text, output_path, "en", max_workers=1)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(results)
        assert mock_gen.call_count == len(texts)