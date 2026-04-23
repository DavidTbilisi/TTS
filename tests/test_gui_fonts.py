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


def test_pick_unicode_font_prefers_noto_georgian_without_segoe() -> None:
    """When Windows UI fonts are absent, Noto Sans Georgian is used."""
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch(
            "tkinter.font.families",
            return_value=("Noto Sans Georgian", "DejaVu Sans", "Arial"),
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


def test_pick_unicode_font_prefers_sylfaen_over_segoe_ui_variable() -> None:
    """Sylfaen carries Mkhedruli reliably in Tk Text; prefer it over Segoe UI Variable."""
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch(
            "tkinter.font.families",
            return_value=("Segoe UI Variable", "Sylfaen", "Arial"),
        ):
            got = _pick_unicode_font_family(root)
        assert got is not None
        assert got[0] == "Sylfaen"
    finally:
        root.destroy()


def test_pick_unicode_font_segoe_before_noto_symbols2() -> None:
    """Symbol fonts lack Mkhedruli; Segoe UI must win when both are installed."""
    pytest.importorskip("tkinter")

    from TTS_ka.gui import _pick_unicode_font_family

    root = _tk_root()
    try:
        with patch(
            "tkinter.font.families",
            return_value=("Noto Sans Symbols 2", "Segoe UI", "Arial"),
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
