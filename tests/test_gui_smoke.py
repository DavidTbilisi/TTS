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


# A config with every playback flag on; the Speak-tab checkboxes start from it.
_CONFIG_ALL_ON = {"stream": True, "no_play": True, "no_gui": True, "chunk_seconds": 0, "parallel": 0}


def test_unchecked_boxes_beat_config_true(tmp_path) -> None:
    """Unticking Stream / Save-only must win over ``true`` in the config."""
    from TTS_ka import gui

    out = tmp_path / "out.mp3"
    out.write_bytes(b"mp3")
    with patch.object(gui, "get_optimal_settings", return_value={"chunk_seconds": 0, "parallel": 1}), \
         patch.object(gui, "fast_generate_audio", return_value=True) as synth, \
         patch.object(gui, "smart_generate_long_text") as long_text, \
         patch.object(gui, "play_audio", return_value=True) as play:
        assert gui._run_async_speak(
            "hello", "en", str(out), stream=False, vlc_gui=False, no_play=False, defs=_CONFIG_ALL_ON
        )
    synth.assert_called_once()
    long_text.assert_not_called()
    play.assert_called_once_with(str(out))


def test_checked_player_window_beats_config_no_gui(tmp_path) -> None:
    from TTS_ka import gui

    with patch.object(gui, "get_optimal_settings", return_value={"chunk_seconds": 0, "parallel": 1}), \
         patch.object(gui, "smart_generate_long_text") as long_text, \
         patch.object(gui, "play_audio") as play:
        gui._run_async_speak(
            "hello", "en", str(tmp_path / "o.mp3"), stream=True, vlc_gui=True, no_play=False,
            defs=_CONFIG_ALL_ON,
        )
    kw = long_text.call_args.kwargs
    assert kw["enable_streaming"] is True
    assert kw["show_gui"] is True
    play.assert_not_called()


def test_speak_tab_file_row_and_player_window_follow_their_toggles() -> None:
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")

    from TTS_ka import gui

    with patch("TTS_ka.deps.collect_dep_rows", return_value=[]), \
         patch("TTS_ka.deps.format_dep_report", return_value="ok"), \
         patch("TTS_ka.native_hotkeys.NativeHotkeyManager", MagicMock()), \
         patch.object(gui.TTSSpeakApp, "_run_setup_check_async"):
        app = gui.TTSSpeakApp({"lang": "en", "stream": False})
        try:
            assert not app._file_row.winfo_manager(), "file row hidden in type/paste mode"
            app.source_mode.set("file")
            assert app._file_row.winfo_manager() == "grid"
            app.source_mode.set("text")
            assert not app._file_row.winfo_manager()

            assert app._player_window_cb.instate(["disabled"])
            app.stream.set(True)
            assert not app._player_window_cb.instate(["disabled"])
        finally:
            app.root.destroy()


def test_setup_tab_fits_at_minimum_size() -> None:
    """At the window's minimum size, the last Setup step must still be on screen."""
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")

    from tkinter import ttk

    from TTS_ka import gui

    with patch("TTS_ka.deps.collect_dep_rows", return_value=[]), \
         patch("TTS_ka.deps.format_dep_report", return_value="ok"), \
         patch("TTS_ka.native_hotkeys.NativeHotkeyManager", MagicMock()), \
         patch.object(gui.TTSSpeakApp, "_run_setup_check_async"):
        app = gui.TTSSpeakApp({"lang": "en"})
        try:
            w, h = app.root.minsize()
            app.root.geometry(f"{w}x{h}")
            app.root.update()
            tab = app.root.nametowidget(app._nb.tabs()[0])
            go = next(
                c for c in tab.winfo_children()
                if isinstance(c, ttk.Button) and c.cget("text").startswith("Go to Speak")
            )
            assert go.winfo_y() + go.winfo_height() <= tab.winfo_height()
        finally:
            app.root.destroy()


def test_no_tab_cuts_off_text_at_the_minimum_window() -> None:
    """At the minimum size every label / button / check / radio gets its full size inside its tab.

    Text boxes and entries are left out: they are meant to shrink.
    """
    tk = pytest.importorskip("tkinter")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("no display available")

    from TTS_ka import gui

    fixed = {"TLabel", "TButton", "TCheckbutton", "TRadiobutton"}

    def descendants(w):
        for c in w.winfo_children():
            yield c
            yield from descendants(c)

    with patch("TTS_ka.deps.collect_dep_rows", return_value=[]), \
         patch("TTS_ka.deps.format_dep_report", return_value="ok"), \
         patch("TTS_ka.native_hotkeys.NativeHotkeyManager", MagicMock()), \
         patch.object(gui.TTSSpeakApp, "_run_setup_check_async"):
        app = gui.TTSSpeakApp({"lang": "en"})
        try:
            w, h = app.root.minsize()
            app.root.geometry(f"{w}x{h}")
            cut = []
            for tab_id in app._nb.tabs():
                app._nb.select(tab_id)
                app.root.update()
                tab = app.root.nametowidget(tab_id)
                right = tab.winfo_rootx() + tab.winfo_width()
                bottom = tab.winfo_rooty() + tab.winfo_height()
                for c in descendants(tab):
                    if c.winfo_class() not in fixed or not c.winfo_ismapped():
                        continue
                    if (
                        c.winfo_width() < c.winfo_reqwidth()
                        or c.winfo_height() < c.winfo_reqheight()
                        or c.winfo_rootx() + c.winfo_width() > right
                        or c.winfo_rooty() + c.winfo_height() > bottom
                    ):
                        cut.append((app._nb.tab(tab_id, "text"), c.winfo_class(), str(c.cget("text"))[:40]))
            assert not cut, cut
        finally:
            app.root.destroy()
