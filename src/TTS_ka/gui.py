"""Small desktop UI: paste text, pick language, generate and play (stdlib tkinter)."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

from .constants import STREAMING_CHUNK_SECONDS
from .fast_audio import cleanup_http, fast_generate_audio, play_audio
from .streaming_player import stop_active_streaming_player
from .ultra_fast import get_optimal_settings, smart_generate_long_text, OPTIMAL_WORKERS
from .user_config import (
    apply_env_from_config,
    argparse_defaults_from_config,
    load_user_config,
    resolved_playback_flags,
)


def _gui_output_path() -> str:
    return str(Path.home() / ".tts_ka_gui_last.mp3")


# Tk default fonts often miss Georgian (Mkhedruli) and sometimes Cyrillic. Pick the
# first installed family that usually covers Latin + Cyrillic + Georgian.
#
# IMPORTANT: Do not put "Noto Sans Symbols 2" / "Segoe UI Symbol" before full UI fonts.
# Symbol fonts often lack Mkhedruli; Tk then shows "?" for Georgian letters.
_UNICODE_FONT_PRIORITY = (
    "segoe ui variable",
    "segoe ui",
    "sylfaen",
    "noto sans georgian",
    "noto sans",
    "microsoft yahei ui",
    "microsoft sans serif",
    "tahoma",
    "dejavu sans",
    "liberation sans",
    "cantarell",
    "arial unicode ms",
    "arial",
    "segoe ui symbol",
    "noto sans symbols 2",
)


def _pick_unicode_font_family(root: Any) -> tuple[str, int] | None:
    import tkinter.font as tkfont

    canon: dict[str, str] = {}
    for fam in tkfont.families():
        canon[fam.lower()] = fam
    for want in _UNICODE_FONT_PRIORITY:
        if want in canon:
            return (canon[want], 10)
    return None


def apply_unicode_ui_fonts(root: Any, size: int = 10) -> tuple[str, int] | None:
    """Set Tk/ttk fonts to a Unicode-capable system family when one is available."""
    import tkinter.font as tkfont
    from tkinter import TclError, ttk

    picked = _pick_unicode_font_family(root)
    if not picked:
        return None
    family, _ = picked
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkHeadingFont",
        "TkMenuFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(name).configure(family=family, size=size)
        except TclError:
            pass
    style = ttk.Style(root)
    ft = (family, size)
    for elem in (
        "TLabel",
        "TButton",
        "TCheckbutton",
        "TRadiobutton",
        "TCombobox",
    ):
        try:
            style.configure(elem, font=ft)
        except TclError:
            pass
    return (family, size)


def _enable_input_methods(root: Any) -> None:
    """Allow system IME (Georgian, Russian, …) in Tk text fields where supported."""
    from tkinter import TclError

    try:
        root.tk.call("tk", "useinputmethods", 1)
    except TclError:
        pass


def _run_async_speak(
    text: str,
    lang: str,
    output_path: str,
    *,
    stream: bool,
    vlc_gui: bool,
    no_play: bool,
    defs: Dict[str, Any],
) -> None:
    """Blocking: runs async generation in a fresh event loop (worker thread)."""
    args_ns = SimpleNamespace(
        no_play=no_play,
        stream=stream,
        no_turbo=False,
        no_gui=not vlc_gui if stream else False,
    )
    flags = resolved_playback_flags(args_ns, defs)
    no_play_f = flags["no_play"]
    stream_f = flags["stream"]
    show_player = flags["show_player"]

    chunk_seconds = defs.get("chunk_seconds", 0) or 0
    parallel = defs.get("parallel", 0) or 0
    optimal = get_optimal_settings(text)
    if chunk_seconds == 0:
        chunk_seconds = optimal["chunk_seconds"]
    if parallel == 0:
        parallel = optimal["parallel"]
    if stream_f and chunk_seconds == 0:
        chunk_seconds = STREAMING_CHUNK_SECONDS
    if parallel == 0:
        parallel = min(4, OPTIMAL_WORKERS)

    async def run_generation() -> None:
        try:
            if chunk_seconds > 0 or len(text.split()) > 200 or stream_f:
                await smart_generate_long_text(
                    text,
                    lang,
                    chunk_seconds=chunk_seconds or 30,
                    parallel=parallel,
                    output_path=output_path,
                    enable_streaming=stream_f,
                    show_gui=show_player,
                )
            else:
                await fast_generate_audio(text, lang, output_path)

            if not no_play_f and not stream_f and os.path.isfile(output_path):
                play_audio(output_path)
        finally:
            try:
                await cleanup_http()
            except Exception:
                pass

    asyncio.run(run_generation())


class TTSSpeakApp:
    def __init__(self, defs: Dict[str, Any]) -> None:
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        self._tk = tk
        self.root = tk.Tk()
        self.root.title("TTS_ka")
        self.root.minsize(420, 320)
        self.defs = defs
        _enable_input_methods(self.root)
        self._ui_font = apply_unicode_ui_fonts(self.root)

        frm = ttk.Frame(self.root, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Language").grid(row=0, column=0, sticky=tk.W)
        self.lang = tk.StringVar(value=defs.get("lang", "en"))
        lang_cb = ttk.Combobox(
            frm,
            textvariable=self.lang,
            values=("ka", "ka-m", "ru", "en"),
            state="readonly",
            width=10,
        )
        lang_cb.grid(row=0, column=1, sticky=tk.W, padx=(4, 0))

        self.stream = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Stream while generating (--stream)", variable=self.stream).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0)
        )

        self.vlc_gui = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text="VLC window for streaming (off = headless / --no-gui)",
            variable=self.vlc_gui,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W)

        self.no_play = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Generate only (no play at end)", variable=self.no_play).grid(
            row=3, column=0, columnspan=2, sticky=tk.W
        )

        ttk.Label(frm, text="Text").grid(row=4, column=0, sticky=(tk.N, tk.W), pady=(8, 0))
        text_kw: Dict[str, Any] = {"height": 10, "wrap": tk.WORD}
        self._text_font_obj = None
        if self._ui_font:
            import tkinter.font as tkfont

            self._text_font_obj = tkfont.Font(
                root=self.root,
                family=self._ui_font[0],
                size=self._ui_font[1],
            )
            text_kw["font"] = self._text_font_obj
        self.text = scrolledtext.ScrolledText(frm, **text_kw)
        self.text.grid(row=5, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(4, 0))
        frm.rowconfigure(5, weight=1)
        frm.columnconfigure(1, weight=1)

        # ttk theme setup can reset named fonts; re-apply after widgets exist.
        self._ui_font = apply_unicode_ui_fonts(self.root)
        if self._ui_font and self._text_font_obj is not None:
            self._text_font_obj.configure(family=self._ui_font[0], size=self._ui_font[1])
            self.text.configure(font=self._text_font_obj)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        self.speak_btn = ttk.Button(btn_row, text="Speak", command=self._on_speak)
        self.speak_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Check deps", command=self._on_check_deps).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Quit", command=self.root.destroy).pack(side=tk.RIGHT)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#333").grid(
            row=7, column=0, columnspan=2, sticky=tk.W, pady=(6, 0)
        )

        self._worker: threading.Thread | None = None

    def mainloop(self) -> None:
        self.root.mainloop()

    def _set_busy(self, busy: bool) -> None:
        state = self._tk.DISABLED if busy else self._tk.NORMAL
        self.speak_btn.configure(state=state)

    def _on_check_deps(self) -> None:
        from .deps import format_dep_report, collect_dep_rows

        report = format_dep_report(collect_dep_rows())
        top = self._tk.Toplevel(self.root)
        top.title("TTS_ka - dependency check")
        top.minsize(480, 360)
        from tkinter import scrolledtext

        txt = scrolledtext.ScrolledText(top, wrap=self._tk.WORD)
        txt.pack(fill=self._tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert("1.0", report)
        txt.configure(state=self._tk.DISABLED)
        ttk.Button(top, text="Close", command=top.destroy).pack(pady=(0, 8))

    def _on_speak(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self.status.set("Already generating...")
            return
        raw = self.text.get("1.0", "end-1c").strip()
        if not raw:
            from tkinter import messagebox

            messagebox.showwarning("TTS_ka", "Enter some text first.")
            return
        out = _gui_output_path()
        lang = self.lang.get().strip()
        stream = bool(self.stream.get())
        vlc_gui = bool(self.vlc_gui.get())
        no_play = bool(self.no_play.get())

        self._set_busy(True)
        self.status.set("Generating...")

        def work() -> None:
            err: str | None = None
            try:
                _run_async_speak(
                    raw,
                    lang,
                    out,
                    stream=stream,
                    vlc_gui=vlc_gui,
                    no_play=no_play,
                    defs=self.defs,
                )
            except SystemExit as se:
                code = se.code
                if code not in (0, None):
                    err = "Streaming stopped: install VLC for GUI streaming, or turn off \"VLC window\"."
            except KeyboardInterrupt:
                err = "Cancelled."
            except BaseException:
                err = traceback.format_exc()

            def done() -> None:
                from tkinter import messagebox

                self._set_busy(False)
                if err:
                    self.status.set("Error - see dialog.")
                    messagebox.showerror("TTS_ka", err[:4000])
                else:
                    self.status.set(f"Done. Output: {out}")

            self.root.after(0, done)

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()


def main() -> None:
    try:
        import tkinter as tk
    except ImportError:
        print(
            "Tkinter is not available. On Debian/Ubuntu install: sudo apt install python3-tk",
            file=sys.stderr,
        )
        sys.exit(1)
    cfg = load_user_config(None)
    apply_env_from_config(cfg)
    defs = argparse_defaults_from_config(cfg)

    def _report_callback_exception(_master: object, exc: object, val: BaseException, tb: object) -> None:
        print("GUI error:", val, file=sys.stderr)

    tk.Tk.report_callback_exception = _report_callback_exception  # type: ignore[method-assign]
    app = TTSSpeakApp(defs)
    app.mainloop()


if __name__ == "__main__":
    main()
