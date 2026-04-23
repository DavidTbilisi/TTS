"""Light tests for GUI helpers (no mainloop)."""

from __future__ import annotations

from TTS_ka.gui import _gui_output_path


def test_gui_output_path_name() -> None:
    p = _gui_output_path()
    assert p.endswith("tts_ka_gui_last.mp3")
