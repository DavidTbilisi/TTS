"""Test configuration and fixtures for TTS_ka tests."""

import os
import sys
import tempfile
import shutil
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_text():
    """Sample text for testing."""
    return "Hello world, this is a test."


@pytest.fixture
def sample_georgian_text():
    """Sample Georgian text for testing."""
    return "გამარჯობა მსოფლიო"


@pytest.fixture
def sample_russian_text():
    """Sample Russian text for testing."""
    return "Привет мир"


@pytest.fixture
def sample_long_text():
    """Long text for chunking tests."""
    return "This is a very long text that should be split into multiple chunks. " * 50


@pytest.fixture
def sample_text_file(temp_dir, sample_text):
    """Create a temporary text file."""
    file_path = os.path.join(temp_dir, "test.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(sample_text)
    return file_path


@pytest.fixture
def mock_audio_response():
    """Mock audio response for edge-tts."""
    return b"fake_audio_data" * 1000


@pytest.fixture
def mock_communicate():
    """Mock edge-tts communicate."""
    with patch('edge_tts.Communicate') as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for fast audio."""
    with patch('httpx.AsyncClient') as mock:
        mock_client = MagicMock()
        mock.return_value.__aenter__.return_value = mock_client
        mock_client.get.return_value.status_code = 200
        mock_client.get.return_value.content = b"fake_audio_data"
        yield mock_client


@pytest.fixture
def mock_soundfile():
    """Mock soundfile for audio processing."""
    with patch('soundfile.write') as mock:
        yield mock


@pytest.fixture
def mock_pygame():
    """Mock pygame for audio playback."""
    with patch.dict('sys.modules', {'pygame': MagicMock()}):
        yield


@pytest.fixture
def mock_pyperclip():
    """Mock pyperclip for clipboard operations."""
    with patch('pyperclip.paste') as mock:
        mock.return_value = "clipboard text"
        yield mock