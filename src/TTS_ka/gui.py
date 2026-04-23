"""Small desktop UI: paste text or file, config JSON, Windows context menu (tkinter)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

from .constants import STREAMING_CHUNK_SECONDS
from .fast_audio import cleanup_http, fast_generate_audio, play_audio
from .ultra_fast import get_optimal_settings, smart_generate_long_text, OPTIMAL_WORKERS
from .user_config import (
    apply_env_from_config,
    argparse_defaults_from_config,
    default_config_path,
    load_user_config,
    resolved_playback_flags,
    write_user_config,
)


def _gui_output_path() -> str:
    return str(Path.home() / ".tts_ka_gui_last.mp3")


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
    def __init__(
        self,
        defs: Dict[str, Any],
        *,
        config_explicit: str | None = None,
        initial_raw: Dict[str, Any] | None = None,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self.root = tk.Tk()
        self.root.title("TTS_ka")
        self.root.minsize(520, 420)
        self.defs = dict(defs)
        _enable_input_methods(self.root)
        self._ui_font = apply_unicode_ui_fonts(self.root)

        cfg_path = (config_explicit or "").strip() or str(default_config_path())
        self.config_path_var = tk.StringVar(value=cfg_path)
        self._initial_raw: Dict[str, Any] = dict(initial_raw) if initial_raw is not None else load_user_config(
            config_explicit if (config_explicit or "").strip() else None
        )

        from .native_hotkeys import NativeHotkeyManager

        self._hotkey_mgr = NativeHotkeyManager() if sys.platform == "win32" else None

        outer = ttk.Frame(self.root, padding=4)
        outer.pack(fill=tk.BOTH, expand=True)
        nb = ttk.Notebook(outer)
        nb.pack(fill=tk.BOTH, expand=True)

        tab_speak = ttk.Frame(nb, padding=8)
        tab_cfg = ttk.Frame(nb, padding=8)
        nb.add(tab_speak, text="Speak")
        nb.add(tab_cfg, text="Config")

        self._build_speak_tab(tab_speak)
        self._build_config_tab(tab_cfg)

        if sys.platform == "win32":
            tab_win = ttk.Frame(nb, padding=8)
            nb.add(tab_win, text="Windows shell")
            self._build_windows_tab(tab_win)

        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)

        self._worker: threading.Thread | None = None

    def _build_speak_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk, scrolledtext

        ttk.Label(frm, text="Language").grid(row=0, column=0, sticky=tk.W)
        self.lang = tk.StringVar(value=self.defs.get("lang", "en"))
        ttk.Combobox(
            frm,
            textvariable=self.lang,
            values=("ka", "ka-m", "ru", "en"),
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky=tk.W, padx=(4, 0))

        self.stream = tk.BooleanVar(value=bool(self.defs.get("stream")))
        ttk.Checkbutton(frm, text="Stream while generating (--stream)", variable=self.stream).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0)
        )

        self.vlc_gui = tk.BooleanVar(value=not bool(self.defs.get("no_gui")))
        ttk.Checkbutton(
            frm,
            text="VLC window for streaming (off = headless / --no-gui)",
            variable=self.vlc_gui,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W)

        self.no_play = tk.BooleanVar(value=bool(self.defs.get("no_play")))
        ttk.Checkbutton(frm, text="Generate only (no play at end)", variable=self.no_play).grid(
            row=3, column=0, columnspan=2, sticky=tk.W
        )

        ttk.Label(frm, text="Text source").grid(row=4, column=0, sticky=tk.W, pady=(10, 0))
        self.source_mode = tk.StringVar(value="text")
        rf = ttk.Frame(frm)
        rf.grid(row=5, column=0, columnspan=2, sticky=tk.W)
        ttk.Radiobutton(rf, text="Type or paste in box", variable=self.source_mode, value="text").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Radiobutton(rf, text="Read UTF-8 file", variable=self.source_mode, value="file").pack(side=tk.LEFT)

        ttk.Label(frm, text="Document path").grid(row=6, column=0, sticky=tk.W, pady=(6, 0))
        self.document_path_var = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=self.document_path_var, width=52).grid(
            row=6, column=1, sticky=(tk.E, tk.W), padx=(4, 4), pady=(6, 0)
        )
        ttk.Button(frm, text="Browse...", command=self._on_browse_document).grid(
            row=6, column=2, sticky=tk.W, pady=(6, 0)
        )
        ttk.Button(frm, text="Load file into editor", command=self._on_load_file_into_editor).grid(
            row=7, column=1, sticky=tk.W, pady=(4, 0)
        )

        ttk.Label(frm, text="Text").grid(row=8, column=0, sticky=(tk.N, tk.W), pady=(8, 0))
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
        self.text.grid(row=9, column=0, columnspan=3, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(4, 0))
        frm.rowconfigure(9, weight=1)
        frm.columnconfigure(1, weight=1)

        self._ui_font = apply_unicode_ui_fonts(self.root)
        if self._ui_font and self._text_font_obj is not None:
            self._text_font_obj.configure(family=self._ui_font[0], size=self._ui_font[1])
            self.text.configure(font=self._text_font_obj)

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=10, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        self.speak_btn = ttk.Button(btn_row, text="Speak", command=self._on_speak)
        self.speak_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Check deps", command=self._on_check_deps).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Quit", command=self._on_quit).pack(side=tk.RIGHT)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#333").grid(
            row=11, column=0, columnspan=3, sticky=tk.W, pady=(6, 0)
        )

    def _build_config_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        ttk.Label(frm, text="Config file (JSON)").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frm, textvariable=self.config_path_var, width=50).grid(
            row=0, column=1, sticky=(tk.E, tk.W), padx=4
        )
        ttk.Button(frm, text="Browse...", command=self._on_browse_config).grid(row=0, column=2, sticky=tk.W)

        bf = ttk.Frame(frm)
        bf.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))
        ttk.Button(bf, text="Reload from disk", command=self._on_reload_config).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="Save", command=self._on_save_config).pack(side=tk.LEFT)

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=3, sticky=(tk.E, tk.W), pady=12)

        ttk.Label(frm, text="Default output (-o)").grid(row=3, column=0, sticky=tk.W)
        self.cfg_output_var = tk.StringVar(value=str(self.defs.get("output", "data.mp3")))
        ttk.Entry(frm, textvariable=self.cfg_output_var, width=50).grid(
            row=3, column=1, columnspan=2, sticky=(tk.E, tk.W), pady=2
        )

        ttk.Label(frm, text="Chunk seconds (0=auto)").grid(row=4, column=0, sticky=tk.W)
        self.cfg_chunk_var = tk.StringVar(value=str(int(self.defs.get("chunk_seconds", 0))))
        ttk.Entry(frm, textvariable=self.cfg_chunk_var, width=10).grid(row=4, column=1, sticky=tk.W, pady=2)

        ttk.Label(frm, text="Parallel workers (0=auto)").grid(row=5, column=0, sticky=tk.W)
        self.cfg_parallel_var = tk.StringVar(value=str(int(self.defs.get("parallel", 0))))
        ttk.Entry(frm, textvariable=self.cfg_parallel_var, width=10).grid(row=5, column=1, sticky=tk.W, pady=2)

        self.cfg_no_turbo = tk.BooleanVar(value=bool(self.defs.get("no_turbo")))
        ttk.Checkbutton(frm, text="Legacy mode (--no-turbo)", variable=self.cfg_no_turbo).grid(
            row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0)
        )

        self.cfg_skip_http = tk.BooleanVar(value=False)
        self.cfg_verbose = tk.BooleanVar(value=False)
        self.cfg_vlc_rc = tk.BooleanVar(value=True)
        raw = self._initial_raw
        if raw:
            self.cfg_skip_http.set(bool(raw.get("skip_http")))
            self.cfg_verbose.set(bool(raw.get("verbose")))
            v = raw.get("vlc_rc", True)
            self.cfg_vlc_rc.set(v is not False)

        ttk.Checkbutton(frm, text="skip_http (TTS_KA_SKIP_HTTP)", variable=self.cfg_skip_http).grid(
            row=7, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Checkbutton(frm, text="verbose (TTS_KA_VERBOSE)", variable=self.cfg_verbose).grid(
            row=8, column=0, columnspan=2, sticky=tk.W
        )
        ttk.Checkbutton(
            frm,
            text="VLC RC playlist mode on Windows (vlc_rc; uncheck sets TTS_KA_VLC_RC=0)",
            variable=self.cfg_vlc_rc,
        ).grid(row=9, column=0, columnspan=2, sticky=tk.W)

        help_txt = (
            "Saved keys match ~/.tts_config.json: lang (Speak tab), output, chunk_seconds, "
            "parallel, no_play, stream, no_gui, no_turbo, skip_http, verbose, vlc_rc."
        )
        ttk.Label(frm, text=help_txt, wraplength=480, justify=tk.LEFT).grid(
            row=10, column=0, columnspan=3, sticky=tk.W, pady=(12, 0)
        )
        frm.columnconfigure(1, weight=1)

    def _build_windows_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        from .native_hotkeys import DEFAULT_HOTKEY_LANG

        ttk.Label(frm, text="Global hotkeys (native, optional)").grid(row=0, column=0, sticky=tk.W)
        self.hk_native_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frm,
            text="Enable Ctrl+Alt+1..4 -> speak clipboard (en / ru / ka / ka-m)",
            variable=self.hk_native_var,
            command=self._on_toggle_native_hotkeys,
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))

        hk_lines = "\n".join(f"  {c}  ->  --lang {lang}" for c, lang in DEFAULT_HOTKEY_LANG.items())
        ttk.Label(
            frm,
            text=(
                "Uses the optional pip extra: pip install 'TTS_ka[hotkeys]' (pynput).\n"
                "Runs a separate ``python -m TTS_ka clipboard`` process per key press.\n"
                "Standalone: TTS_ka-hotkeys\n\n"
                f"{hk_lines}"
            ),
            wraplength=500,
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky=tk.W, pady=(6, 0))

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=3, column=0, sticky=(tk.E, tk.W), pady=14)

        self.cm_include_txt = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text='Add "read this .txt file" entries (per-language) to right-click on .txt',
            variable=self.cm_include_txt,
        ).grid(row=4, column=0, sticky=tk.W)

        ttk.Label(
            frm,
            text="Registers Explorer / Desktop background menu (per-user HKCU). "
            "Requires the repo script extras/windows/context_menu/Install-TTS_ka-ContextMenu.ps1 "
            "(not shipped in the PyPI wheel unless you have that tree next to the package).",
            wraplength=480,
            justify=tk.LEFT,
        ).grid(row=5, column=0, sticky=tk.W, pady=(8, 0))

        bf = ttk.Frame(frm)
        bf.grid(row=6, column=0, sticky=tk.W, pady=(12, 0))
        ttk.Button(bf, text="Install context menu", command=self._on_install_context_menu).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(bf, text="Uninstall context menu", command=self._on_uninstall_context_menu).pack(side=tk.LEFT)

        self.cm_status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.cm_status, wraplength=480, justify=tk.LEFT).grid(
            row=7, column=0, sticky=tk.W, pady=(10, 0)
        )

    def _on_quit(self) -> None:
        if self._hotkey_mgr is not None:
            self._hotkey_mgr.stop()
        self.root.destroy()

    def _on_toggle_native_hotkeys(self) -> None:
        from tkinter import messagebox

        if self._hotkey_mgr is None:
            return
        if self.hk_native_var.get():
            if not self._hotkey_mgr.start():
                messagebox.showwarning(
                    "TTS_ka hotkeys",
                    "Install the optional dependency, then try again:\n\n  pip install 'TTS_ka[hotkeys]'",
                )
                self.hk_native_var.set(False)
        else:
            self._hotkey_mgr.stop()

    def mainloop(self) -> None:
        self.root.mainloop()

    def _set_busy(self, busy: bool) -> None:
        state = self._tk.DISABLED if busy else self._tk.NORMAL
        self.speak_btn.configure(state=state)

    def _on_browse_document(self) -> None:
        from tkinter import filedialog

        p = filedialog.askopenfilename(
            parent=self.root,
            title="Open document",
            filetypes=[
                ("Text and markup", "*.txt *.md *.markdown"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if p:
            self.document_path_var.set(p)

    def _on_browse_config(self) -> None:
        from tkinter import filedialog

        p = filedialog.askopenfilename(
            parent=self.root,
            title="Config JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if p:
            self.config_path_var.set(p)

    def _on_load_file_into_editor(self) -> None:
        from tkinter import messagebox

        p = self.document_path_var.get().strip()
        if not p:
            messagebox.showwarning("TTS_ka", "Choose a document path first.")
            return
        if not os.path.isfile(p):
            messagebox.showwarning("TTS_ka", f"File not found:\n{p}")
            return
        try:
            data = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            messagebox.showerror("TTS_ka", str(e))
            return
        self.text.delete("1.0", self._tk.END)
        self.text.insert("1.0", data)
        self.source_mode.set("text")
        self.status.set(f"Loaded {len(data)} characters from file.")

    def _on_reload_config(self) -> None:
        from tkinter import messagebox

        p = self.config_path_var.get().strip()
        raw = load_user_config(p) if p else {}
        self.defs = argparse_defaults_from_config(raw)
        apply_env_from_config(raw)
        self.lang.set(self.defs["lang"])
        self.stream.set(bool(self.defs["stream"]))
        self.no_play.set(bool(self.defs["no_play"]))
        self.vlc_gui.set(not bool(self.defs.get("no_gui")))
        self.cfg_output_var.set(str(self.defs.get("output", "data.mp3")))
        self.cfg_chunk_var.set(str(int(self.defs.get("chunk_seconds", 0))))
        self.cfg_parallel_var.set(str(int(self.defs.get("parallel", 0))))
        self.cfg_no_turbo.set(bool(self.defs.get("no_turbo")))
        self.cfg_skip_http.set(bool(raw.get("skip_http")))
        self.cfg_verbose.set(bool(raw.get("verbose")))
        self.cfg_vlc_rc.set(raw.get("vlc_rc", True) is not False)
        messagebox.showinfo("TTS_ka", "Reloaded settings from config file.")

    def _gather_config_payload(self) -> Dict[str, Any]:
        def _i(var: Any) -> int:
            try:
                return max(0, int(str(var.get()).strip() or "0"))
            except (TypeError, ValueError):
                return 0

        lang = self.lang.get().strip()
        if lang not in ("ka", "ka-m", "ru", "en"):
            lang = "en"
        return {
            "lang": lang,
            "output": (self.cfg_output_var.get().strip() or "data.mp3"),
            "chunk_seconds": _i(self.cfg_chunk_var),
            "parallel": _i(self.cfg_parallel_var),
            "no_play": bool(self.no_play.get()),
            "stream": bool(self.stream.get()),
            "no_gui": not bool(self.vlc_gui.get()),
            "no_turbo": bool(self.cfg_no_turbo.get()),
            "skip_http": bool(self.cfg_skip_http.get()),
            "verbose": bool(self.cfg_verbose.get()),
            "vlc_rc": bool(self.cfg_vlc_rc.get()),
        }

    def _on_save_config(self) -> None:
        from tkinter import messagebox

        p = self.config_path_var.get().strip()
        if not p:
            messagebox.showwarning("TTS_ka", "Set a config file path.")
            return
        prev = load_user_config(p) if p else {}
        payload = {**prev, **self._gather_config_payload()}
        try:
            write_user_config(p, payload)
        except OSError as e:
            messagebox.showerror("TTS_ka", str(e))
            return
        apply_env_from_config(payload)
        self.defs = argparse_defaults_from_config(payload)
        messagebox.showinfo("TTS_ka", f"Saved:\n{p}")

    def _on_check_deps(self) -> None:
        from tkinter import scrolledtext, ttk

        from .deps import collect_dep_rows, format_dep_report

        report = format_dep_report(collect_dep_rows())
        top = self._tk.Toplevel(self.root)
        top.title("TTS_ka - dependency check")
        top.minsize(480, 360)
        txt = scrolledtext.ScrolledText(top, wrap=self._tk.WORD)
        txt.pack(fill=self._tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert("1.0", report)
        txt.configure(state=self._tk.DISABLED)
        ttk.Button(top, text="Close", command=top.destroy).pack(pady=(0, 8))

    def _resolve_speak_text(self) -> str | None:
        from tkinter import messagebox

        if self.source_mode.get() == "file":
            p = self.document_path_var.get().strip()
            if not p:
                messagebox.showwarning("TTS_ka", "Choose a document path, or switch to typing in the box.")
                return None
            if not os.path.isfile(p):
                messagebox.showwarning("TTS_ka", f"File not found:\n{p}")
                return None
            try:
                return Path(p).read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                messagebox.showerror("TTS_ka", str(e))
                return None
        raw = self.text.get("1.0", "end-1c").strip()
        if not raw:
            messagebox.showwarning("TTS_ka", "Enter some text first.")
            return None
        return raw

    def _on_speak(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self.status.set("Already generating...")
            return
        raw = self._resolve_speak_text()
        if raw is None:
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

    def _run_ps_context_menu(self, *, uninstall: bool) -> None:
        from tkinter import messagebox

        def work() -> None:
            err: str | None = None
            out = ""
            try:
                from .windows_shell import find_context_menu_installer, run_context_menu_installer

                if find_context_menu_installer() is None:
                    err = (
                        "Install-TTS_ka-ContextMenu.ps1 was not found.\n"
                        "Clone the GitHub repo or copy extras/windows/context_menu/ next to your source tree, "
                        "or run the script manually from PowerShell."
                    )
                else:
                    r = run_context_menu_installer(
                        uninstall=uninstall,
                        include_txt_files=bool(self.cm_include_txt.get()) and not uninstall,
                    )
                    out = (r.stdout or "").strip() + "\n" + (r.stderr or "").strip()
                    out = out.strip()
                    if r.returncode != 0:
                        err = out or f"Exit code {r.returncode}"
            except subprocess.TimeoutExpired:
                err = "Timed out waiting for PowerShell."
            except FileNotFoundError as e:
                err = str(e)
            except OSError as e:
                err = str(e)

            def done() -> None:
                if err:
                    self.cm_status.set(err[:800])
                    messagebox.showerror("TTS_ka context menu", err[:4000])
                else:
                    self.cm_status.set(out[:800] or "OK.")
                    messagebox.showinfo("TTS_ka context menu", out[:4000] or "Done.")

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _on_install_context_menu(self) -> None:
        self._run_ps_context_menu(uninstall=False)

    def _on_uninstall_context_menu(self) -> None:
        self._run_ps_context_menu(uninstall=True)


def main() -> None:
    try:
        import tkinter as tk
    except ImportError:
        print(
            "Tkinter is not available. On Debian/Ubuntu install: sudo apt install python3-tk",
            file=sys.stderr,
        )
        sys.exit(1)
    explicit = os.environ.get("TTS_KA_CONFIG", "").strip() or None
    cfg = load_user_config(explicit)
    apply_env_from_config(cfg)
    defs = argparse_defaults_from_config(cfg)

    def _report_callback_exception(_master: object, exc: object, val: BaseException, tb: object) -> None:
        print("GUI error:", val, file=sys.stderr)

    tk.Tk.report_callback_exception = _report_callback_exception  # type: ignore[method-assign]
    app = TTSSpeakApp(defs, config_explicit=explicit, initial_raw=cfg)
    app.mainloop()


if __name__ == "__main__":
    main()
