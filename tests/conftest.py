"""Test configuration and fixtures for TTS_ka tests."""

import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch

# Add src to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def _popen_argv_head(argv):
    if not argv:
        return ""
    return os.path.basename(os.fsdecode(argv[0])).lower()


@pytest.fixture(autouse=True)
def _silence_windows_real_media_players():
    """Do not spawn VLC / media players for fake ``*.mp3`` paths during tests (Windows).

    A blanket ``Popen`` mock would break tests that really run helper binaries, so we
    only stub Popen for real player binaries.
    """
    if not sys.platform.startswith("win"):
        yield
        return

    import subprocess as _sp

    _real_popen = _sp.Popen

    def _selective_popen(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args", ())
        if isinstance(argv, (list, tuple)) and argv:
            head = _popen_argv_head(argv)
            if head in (
                "where.exe", "where", "which", "which.exe",
                "bash", "bash.exe",  # needed by completion-script syntax-check tests
            ):
                return _real_popen(*args, **kwargs)
        mock_proc = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.terminate = MagicMock()
        return mock_proc

    with patch.object(_sp, "Popen", side_effect=_selective_popen), \
         patch("TTS_ka.fast_audio.os.startfile", create=True):
        yield


@pytest.fixture(autouse=True)
def _isolate_http_health(tmp_path, monkeypatch):
    """Keep the HTTP circuit breaker from reading/writing real on-disk state.

    Points the marker at a per-test path and resets the in-process memo so test
    order never matters and a real "down" verdict cannot leak into mocked tests.
    """
    monkeypatch.setenv("TTS_KA_HTTP_STATE", str(tmp_path / "http_health.json"))
    try:
        from TTS_ka.fast_audio import _reset_http_health
        _reset_http_health()
        yield
        _reset_http_health()
    except Exception:
        yield


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)
