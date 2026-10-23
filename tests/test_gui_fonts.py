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


def test_unicode_fonts_leave_fixed_font_monospace() -> None:
    """The dependency report is column-aligned, so TkFixedFont must keep its family."""
    pytest.importorskip("tkinter")
    import tkinter.font as tkfont

    from TTS_ka.gui import apply_unicode_ui_fonts

    root = _tk_root()
    try:
        before = tkfont.nametofont("TkFixedFont").actual("family")
        with patch("tkinter.font.families", return_value=("Noto Sans Georgian",)):
            picked = apply_unicode_ui_fonts(root)
        assert picked == ("Noto Sans Georgian", 10)
        assert tkfont.nametofont("TkFixedFont").actual("family") == before
        assert tkfont.nametofont("TkDefaultFont").cget("family") == "Noto Sans Georgian"
    finally:
        root.destroy()


def test_heading_styles_are_bold_and_larger() -> None:
    pytest.importorskip("tkinter")
    from tkinter import ttk

    from TTS_ka.gui import configure_heading_styles

    root = _tk_root()
    try:
        configure_heading_styles(root, ("DejaVu Sans", 10))
        style = ttk.Style(root)
        assert root.tk.splitlist(style.lookup("Title.TLabel", "font")) == ("DejaVu Sans", "16", "bold")
        assert root.tk.splitlist(style.lookup("Heading.TLabel", "font")) == ("DejaVu Sans", "11", "bold")
    finally:
        root.destroy()


def test_gui_theme_classic_keeps_tk_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("tkinter")
    from tkinter import ttk

    from TTS_ka.gui import apply_gui_theme

    monkeypatch.setenv("TTS_KA_GUI_THEME", "classic")
    root = _tk_root()
    try:
        before = ttk.Style(root).theme_use()
        assert apply_gui_theme(root) is None
        assert ttk.Style(root).theme_use() == before
    finally:
        root.destroy()


def test_gui_theme_without_sv_ttk_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("tkinter")
    import sys

    from TTS_ka.gui import apply_gui_theme

    monkeypatch.delenv("TTS_KA_GUI_THEME", raising=False)
    monkeypatch.setitem(sys.modules, "sv_ttk", None)  # import raises ImportError
    root = _tk_root()
    try:
        assert apply_gui_theme(root) is None
    finally:
        root.destroy()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_gui_theme_env_picks_sun_valley_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    pytest.importorskip("tkinter")
    pytest.importorskip("sv_ttk")
    from tkinter import ttk

    from TTS_ka.gui import apply_gui_theme

    monkeypatch.setenv("TTS_KA_GUI_THEME", mode)
    root = _tk_root()
    try:
        assert apply_gui_theme(root) == mode
        assert ttk.Style(root).theme_use() == f"sun-valley-{mode}"
    finally:
        root.destroy()


def test_gui_theme_follows_system_dark_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("tkinter")
    pytest.importorskip("sv_ttk")
    import sys
    import types

    from TTS_ka.gui import apply_gui_theme

    monkeypatch.delenv("TTS_KA_GUI_THEME", raising=False)
    monkeypatch.setitem(sys.modules, "darkdetect", types.SimpleNamespace(theme=lambda: "Dark"))
    root = _tk_root()
    try:
        assert apply_gui_theme(root) == "dark"
    finally:
        root.destroy()


def test_sun_valley_fonts_use_the_unicode_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """sv-ttk asks for Segoe UI Variable; Georgian needs the family we picked."""
    pytest.importorskip("tkinter")
    pytest.importorskip("sv_ttk")
    import tkinter.font as tkfont

    from TTS_ka.gui import apply_gui_theme, apply_unicode_ui_fonts

    monkeypatch.setenv("TTS_KA_GUI_THEME", "light")
    root = _tk_root()
    try:
        apply_gui_theme(root)
        with patch("tkinter.font.families", return_value=("Noto Sans Georgian",)):
            apply_unicode_ui_fonts(root)
        assert tkfont.nametofont("SunValleyBodyFont").cget("family") == "Noto Sans Georgian"
        assert tkfont.nametofont("SunValleyBodyFont").cget("size") == -14
    finally:
        root.destroy()
