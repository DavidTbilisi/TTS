"""Unicode font selection for the tkinter GUI."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _tk_root():
    import os
    import sys
    import tkinter as tk

    if sys.platform == "linux" and not os.environ.get("DISPLAY", "").strip():
        pytest.skip("no DISPLAY for tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"tkinter unavailable: {e}")
    root.withdraw()
    return root


def test_pick_unicode_font_prefers_noto_georgian() -> None:
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch(
            "tkinter.font.families",
            return_value=("Noto Sans Georgian", "Segoe UI", "Arial"),
        ):
            got = _pick_unicode_font_family(root)
        assert got is not None
        assert got[0] == "Noto Sans Georgian"
    finally:
        root.destroy()


def test_pick_unicode_font_falls_back_to_segoe() -> None:
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch(
            "tkinter.font.families",
            return_value=("Segoe UI", "Arial"),
        ):
            got = _pick_unicode_font_family(root)
        assert got is not None
        assert got[0] == "Segoe UI"
    finally:
        root.destroy()


def test_pick_unicode_font_none_when_no_match() -> None:
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch("tkinter.font.families", return_value=("SomeObscureFont123",)):
            assert _pick_unicode_font_family(root) is None
    finally:
        root.destroy()
