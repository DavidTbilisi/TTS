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
def _isolated_tempdir(tmp_path, monkeypatch):
    """Point ``tempfile`` at a per-test dir so run dirs and temp MP3s never pile up in /tmp."""
    scratch = tmp_path / "_tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))


@pytest.fixture(autouse=True)
def _no_mpv_ipc(monkeypatch):
    """Keep StreamingAudioPlayer on the stubbable stdin-playlist path; IPC tests opt back in."""
    monkeypatch.setenv("TTS_KA_MPV_IPC", "0")


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


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)
