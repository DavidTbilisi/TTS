"""Light tests for GUI helpers (no mainloop)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from TTS_ka.gui import _gui_output_path


def test_gui_output_path_name() -> None:
    p = _gui_output_path()
    assert p.endswith("tts_ka_gui_last.mp3")


def test_setup_tab_builds_with_voices() -> None:
    """The Setup tab constructs and is the first tab. Skips without a display."""
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")

    from TTS_ka import gui

    # Keep construction fast/deterministic: stub the background dep check and
    # any platform hotkey manager.
    with patch("TTS_ka.deps.collect_dep_rows", return_value=[]), \
         patch("TTS_ka.deps.format_dep_report", return_value="ok"), \
         patch("TTS_ka.native_hotkeys.NativeHotkeyManager", MagicMock()):
        app = gui.TTSSpeakApp({"lang": "en"})
        try:
            # Setup is the first tab and the voice list is populated.
            assert app._nb.tabs(), "notebook has tabs"
            first_tab_text = app._nb.tab(app._nb.tabs()[0], "text")
            assert first_tab_text == "Setup"
            assert len(app._setup_voices) > 0
        finally:
            app.root.destroy()
