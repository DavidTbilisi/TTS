"""Tests for fast_audio module."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from TTS_ka.fast_audio import generate_audio_ultra_fast, get_voice_for_language, validate_language


class TestFastAudio:
    """Test cases for fast audio generation."""

    def test_get_voice_for_language_ka(self):
        """Test voice selection for Georgian."""
        voice = get_voice_for_language("ka")
        assert voice in ["ka-GE-EkaNeural", "ka-GE-GiorgiNeural"]

    def test_get_voice_for_language_ru(self):
        """Test voice selection for Russian."""
        voice = get_voice_for_language("ru")
        assert voice in ["ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"]

    def test_get_voice_for_language_en(self):
        """Test voice selection for English."""
        voice = get_voice_for_language("en")
        assert voice in ["en-US-AriaNeural", "en-US-DavisNeural"]

    def test_get_voice_for_language_invalid(self):
        """Test voice selection for invalid language."""
        voice = get_voice_for_language("invalid")
        assert voice == "en-US-AriaNeural"  # Default fallback

    def test_validate_language_valid(self):
        """Test language validation for valid languages."""
        assert validate_language("ka") == True
        assert validate_language("ru") == True
        assert validate_language("en") == True

    def test_validate_language_invalid(self):
        """Test language validation for invalid languages."""
        assert validate_language("fr") == False
        assert validate_language("de") == False
        assert validate_language("invalid") == False
        assert validate_language("") == False
        assert validate_language(None) == False

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_success(self, mock_httpx_client, temp_dir):
        """Test successful audio generation via API."""
        output_path = f"{temp_dir}/test.mp3"
        
        # Mock successful API response
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.content = b"fake_audio_data"
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_httpx_client
            
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = await generate_audio_ultra_fast(
                    "Hello world", 
                    output_path, 
                    "en"
                )
        
        assert result == True
        mock_file.write.assert_called_once_with(b"fake_audio_data")

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_api_failure(self, mock_httpx_client, temp_dir, mock_communicate):
        """Test audio generation with API failure, falling back to edge-tts."""
        output_path = f"{temp_dir}/test.mp3"
        
        # Mock API failure
        mock_httpx_client.get.return_value.status_code = 500
        
        # Mock edge-tts success
        mock_communicate.stream.return_value = AsyncMock()
        mock_communicate.stream.return_value.__aiter__.return_value = [
            {"type": "audio", "data": b"fake_audio_chunk"}
        ]
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_httpx_client
            
            with patch('TTS_ka.fast_audio.edge_tts.Communicate', return_value=mock_communicate):
                with patch('builtins.open', create=True) as mock_open:
                    mock_file = MagicMock()
                    mock_open.return_value.__enter__.return_value = mock_file
                    
                    result = await generate_audio_ultra_fast(
                        "Hello world", 
                        output_path, 
                        "en"
                    )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_exception(self, temp_dir):
        """Test audio generation with exceptions."""
        output_path = f"{temp_dir}/test.mp3"
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            # Simulate exception in API call
            mock_client.side_effect = Exception("Network error")
            
            result = await generate_audio_ultra_fast(
                "Hello world", 
                output_path, 
                "en"
            )
        
        assert result == False

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_empty_text(self, temp_dir):
        """Test audio generation with empty text."""
        output_path = f"{temp_dir}/test.mp3"
        
        result = await generate_audio_ultra_fast("", output_path, "en")
        assert result == False

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_georgian(self, mock_httpx_client, temp_dir):
        """Test audio generation with Georgian text."""
        output_path = f"{temp_dir}/test.mp3"
        
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.content = b"fake_audio_data"
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_httpx_client
            
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = await generate_audio_ultra_fast(
                    "გამარჯობა", 
                    output_path, 
                    "ka"
                )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_russian(self, mock_httpx_client, temp_dir):
        """Test audio generation with Russian text."""
        output_path = f"{temp_dir}/test.mp3"
        
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.content = b"fake_audio_data"
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_httpx_client
            
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = await generate_audio_ultra_fast(
                    "Привет", 
                    output_path, 
                    "ru"
                )
        
        assert result == True

    @pytest.mark.parametrize("language", ["ka", "ru", "en"])
    @pytest.mark.asyncio
    async def test_generate_audio_all_languages(self, language, mock_httpx_client, temp_dir):
        """Test audio generation for all supported languages."""
        output_path = f"{temp_dir}/test_{language}.mp3"
        
        mock_httpx_client.get.return_value.status_code = 200
        mock_httpx_client.get.return_value.content = b"fake_audio_data"
        
        with patch('TTS_ka.fast_audio.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_httpx_client
            
            with patch('builtins.open', create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                result = await generate_audio_ultra_fast(
                    "Test text", 
                    output_path, 
                    language
                )
        
        assert result == True

    @pytest.mark.asyncio
    async def test_generate_audio_ultra_fast_invalid_language(self, temp_dir):
        """Test audio generation with invalid language."""
        output_path = f"{temp_dir}/test.mp3"
        
        result = await generate_audio_ultra_fast(
            "Hello world", 
            output_path, 
            "invalid"
        )
        
        assert result == False

    def test_voice_mapping_completeness(self):
        """Test that all supported languages have voice mappings."""
        supported_languages = ["ka", "ru", "en"]
        
        for lang in supported_languages:
            voice = get_voice_for_language(lang)
            assert voice is not None
            assert isinstance(voice, str)
            assert len(voice) > 0