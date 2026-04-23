"""Small GUI helpers (pip wrapper, docs URL) — no tkinter window."""

from __future__ import annotations

import importlib.metadata
import sys
from types import SimpleNamespace
from unittest.mock import patch


def test_run_pip_install_builds_python_m_pip() -> None:
    with patch("TTS_ka.gui.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        from TTS_ka.gui import run_pip_install

        r = run_pip_install("TTS_ka[hotkeys]")
        assert r.returncode == 0
        cmd = run.call_args[0][0]
        assert cmd[:4] == [sys.executable, "-m", "pip", "install"]
        assert cmd[4] == "TTS_ka[hotkeys]"


def test_hotkeys_dict_from_pairs_filters_empty_and_invalid_lang() -> None:
    from TTS_ka.gui import hotkeys_dict_from_combo_lang_pairs

    d = hotkeys_dict_from_combo_lang_pairs(
        [
            ("  <ctrl>+x  ", "en"),
            ("", "ru"),
            ("<alt>+z", "xx"),
            ("<ctrl>+y", "ka-m"),
        ]
    )
    assert d == {"<ctrl>+x": "en", "<ctrl>+y": "ka-m"}


def test_run_pip_uninstall_builds_command() -> None:
    with patch("TTS_ka.gui.subprocess.run") as run:
        run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        from TTS_ka.gui import run_pip_uninstall

        r = run_pip_uninstall("pynput")
        assert r.returncode == 0
        cmd = run.call_args[0][0]
        assert cmd[:5] == [sys.executable, "-m", "pip", "uninstall", "-y"]
        assert cmd[5] == "pynput"


def test_docs_url_fallback_when_not_installed() -> None:
    with patch(
        "TTS_ka.gui.importlib.metadata.metadata",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        from TTS_ka.gui import _docs_url

        u = _docs_url()
        assert "readme" in u.lower()
        assert u.startswith("http")
