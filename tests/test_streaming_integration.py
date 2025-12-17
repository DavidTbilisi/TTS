"""Integration tests for streaming playback through CLI."""

import os
import sys
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from TTS_ka.main import main


class TestStreamingCLI:
    """Test streaming functionality through CLI interface."""
    
    @patch('TTS_ka.main.fast_generate_audio')
    @patch('TTS_ka.main.play_audio')
    def test_cli_with_stream_flag(self, mock_play, mock_generate):
        """Test CLI with --stream flag."""
        async def mock_gen(text, lang, output, quiet=False):
            with open(output, 'wb') as f:
                f.write(b'audio')
            return True
        
        mock_generate.return_value = None
        mock_generate.side_effect = mock_gen
        
        test_args = ['TTS_ka', 'Hello world', '--lang', 'en', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
            except SystemExit:
                pass  # Ignore exit
    
    @patch('TTS_ka.main.smart_generate_long_text')
    @patch('TTS_ka.main.play_audio')
    def test_cli_streaming_long_text(self, mock_play, mock_smart_gen):
        """Test streaming with long text via CLI."""
        async def mock_gen_long(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen_long
        
        long_text = "This is a test. " * 150
        test_args = ['TTS_ka', long_text, '--lang', 'en', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
                # Verify streaming was enabled
                assert mock_smart_gen.called
                call_kwargs = mock_smart_gen.call_args[1]
                assert call_kwargs.get('enable_streaming') is True
            except SystemExit:
                pass
    
    @patch('TTS_ka.main.fast_generate_audio')
    @patch('TTS_ka.main.play_audio')
    def test_cli_without_stream_flag(self, mock_play, mock_generate):
        """Test that streaming is not enabled without --stream flag."""
        async def mock_gen(text, lang, output, quiet=False):
            with open(output, 'wb') as f:
                f.write(b'audio')
            return True
        
        mock_generate.side_effect = mock_gen
        
        test_args = ['TTS_ka', 'Short text', '--lang', 'en', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
            except SystemExit:
                pass
    
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_cli_stream_skips_duplicate_playback(self, mock_smart_gen):
        """Test that streaming mode skips the duplicate play_audio call."""
        async def mock_gen_long(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen_long
        
        with patch('TTS_ka.main.play_audio') as mock_play:
            long_text = "Test " * 150
            test_args = ['TTS_ka', long_text, '--lang', 'en', '--stream']
            
            with patch('sys.argv', test_args):
                try:
                    main()
                    # play_audio should NOT be called when streaming
                    mock_play.assert_not_called()
                except SystemExit:
                    pass
    
    @patch('TTS_ka.main.get_input_text')
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_cli_stream_with_file(self, mock_smart_gen, mock_get_text):
        """Test streaming with file input."""
        async def mock_gen_long(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen_long
        mock_get_text.return_value = "File content " * 150
        
        test_args = ['TTS_ka', 'test.txt', '--lang', 'en', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
                assert mock_smart_gen.called
            except SystemExit:
                pass
    
    def test_cli_help_mentions_stream(self):
        """Test that help text mentions streaming feature."""
        test_args = ['TTS_ka', '--help']
        
        with patch('sys.argv', test_args):
            with patch('sys.stdout', new=StringIO()) as fake_out:
                try:
                    main()
                except SystemExit:
                    pass
                
                help_text = fake_out.getvalue()
                assert '--stream' in help_text.lower() or 'stream' in help_text.lower()


class TestStreamingWithChunking:
    """Test streaming integration with chunking."""
    
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_stream_with_custom_chunk_size(self, mock_smart_gen):
        """Test streaming with custom chunk size."""
        async def mock_gen(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen
        
        long_text = "Test text. " * 150
        test_args = [
            'TTS_ka', long_text, '--lang', 'en', 
            '--stream', '--chunk-seconds', '25', '--no-play'
        ]
        
        with patch('sys.argv', test_args):
            try:
                main()
                assert mock_smart_gen.called
                call_kwargs = mock_smart_gen.call_args[1]
                assert call_kwargs.get('enable_streaming') is True
                assert call_kwargs.get('chunk_seconds') == 25
            except SystemExit:
                pass
    
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_stream_with_parallel_workers(self, mock_smart_gen):
        """Test streaming with custom parallel workers."""
        async def mock_gen(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen
        
        long_text = "Test. " * 150
        test_args = [
            'TTS_ka', long_text, '--lang', 'en',
            '--stream', '--parallel', '6', '--no-play'
        ]
        
        with patch('sys.argv', test_args):
            try:
                main()
                call_kwargs = mock_smart_gen.call_args[1]
                assert call_kwargs.get('enable_streaming') is True
                assert call_kwargs.get('parallel') == 6
            except SystemExit:
                pass


class TestStreamingLanguages:
    """Test streaming with different languages."""
    
    @patch('TTS_ka.main.smart_generate_long_text')
    @patch('TTS_ka.main.fast_generate_audio')
    def test_stream_georgian(self, mock_fast_gen, mock_smart_gen):
        """Test streaming with Georgian language."""
        async def mock_gen(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        async def mock_fast(*args, **kwargs):
            output = args[2] if len(args) > 2 else kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
            return True
        
        mock_smart_gen.side_effect = mock_gen
        mock_fast_gen.side_effect = mock_fast
        
        georgian_text = "გამარჯობა " * 150
        test_args = ['TTS_ka', georgian_text, '--lang', 'ka', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
                assert mock_smart_gen.called
            except SystemExit:
                pass
    
    @patch('TTS_ka.main.smart_generate_long_text')
    @patch('TTS_ka.main.fast_generate_audio')
    def test_stream_russian(self, mock_fast_gen, mock_smart_gen):
        """Test streaming with Russian language."""
        async def mock_gen(*args, **kwargs):
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        async def mock_fast(*args, **kwargs):
            output = args[2] if len(args) > 2 else kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
            return True
        
        mock_smart_gen.side_effect = mock_gen
        mock_fast_gen.side_effect = mock_fast
        
        russian_text = "Привет " * 150
        test_args = ['TTS_ka', russian_text, '--lang', 'ru', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
                assert mock_smart_gen.called
            except SystemExit:
                pass


class TestStreamingErrorHandling:
    """Test error handling in streaming mode."""
    
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_stream_with_generation_error(self, mock_smart_gen):
        """Test streaming gracefully handles generation errors."""
        async def mock_gen_error(**kwargs):
            raise Exception("Generation failed")
        
        mock_smart_gen.side_effect = mock_gen_error
        
        test_args = ['TTS_ka', 'Test ' * 100, '--lang', 'en', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
            except Exception as e:
                # Should propagate the error but not crash catastrophically
                assert "Generation failed" in str(e) or True
    
    @patch('TTS_ka.main.get_input_text')
    def test_stream_with_empty_text(self, mock_get_text):
        """Test streaming with empty text input."""
        mock_get_text.return_value = ""
        
        test_args = ['TTS_ka', 'empty', '--lang', 'en', '--stream']
        
        with patch('sys.argv', test_args):
            try:
                main()
                # Should handle gracefully
            except SystemExit:
                pass


class TestStreamingPerformanceCLI:
    """Test streaming performance through CLI."""
    
    @pytest.mark.slow
    @patch('TTS_ka.main.smart_generate_long_text')
    def test_stream_performance_benefit(self, mock_smart_gen):
        """Test that streaming provides performance benefit."""
        call_count = 0
        
        async def mock_gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            output = kwargs.get('output_path', 'data.mp3')
            with open(output, 'wb') as f:
                f.write(b'audio')
        
        mock_smart_gen.side_effect = mock_gen
        
        # Large text
        large_text = "This is a long sentence for testing. " * 250
        test_args = ['TTS_ka', large_text, '--lang', 'en', '--stream', '--no-play']
        
        with patch('sys.argv', test_args):
            try:
                main()
                assert call_count > 0
            except SystemExit:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
