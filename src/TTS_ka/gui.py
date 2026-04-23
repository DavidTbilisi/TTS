"""Small desktop UI: paste text or file, config JSON, Windows context menu (tkinter)."""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

from .constants import STREAMING_CHUNK_SECONDS
from .fast_audio import cleanup_http, fast_generate_audio, play_audio
from .ultra_fast import (
    OPTIMAL_WORKERS,
    GenerationCancelled,
    _await_with_cancel,
    get_optimal_settings,
    smart_generate_long_text,
)
from .user_config import (
    LANG_CODES,
    apply_env_from_config,
    argparse_defaults_from_config,
    default_config_path,
    load_user_config,
    resolved_playback_flags,
    write_user_config,
)


def _gui_output_path() -> str:
    return str(Path.home() / ".tts_ka_gui_last.mp3")


_DEFAULT_DOCS_URL = "https://github.com/DavidTbilisi/TTS/blob/main/readme.md"
_DEFAULT_HOME_URL = "https://github.com/DavidTbilisi/TTS"


def _project_urls_from_metadata() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        meta = importlib.metadata.metadata("TTS_ka")
        for entry in meta.get_all("Project-URL") or ():
            if "," not in entry:
                continue
            name, url = entry.split(",", 1)
            out[name.strip().lower()] = url.strip()
    except importlib.metadata.PackageNotFoundError:
        pass
    return out


def _docs_url() -> str:
    urls = _project_urls_from_metadata()
    return urls.get("documentation") or _DEFAULT_DOCS_URL


def _homepage_url() -> str:
    urls = _project_urls_from_metadata()
    return urls.get("homepage") or _DEFAULT_HOME_URL


def _pip_install_base_kwargs() -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def run_pip_install(*packages: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run ``python -m pip install`` (no console window on Windows). For tests, patch subprocess.run."""
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        **_pip_install_base_kwargs(),
    )


def run_pip_uninstall(*packages: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run ``python -m pip uninstall -y`` (no console window on Windows)."""
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", *packages]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        **_pip_install_base_kwargs(),
    )


def hotkeys_dict_from_combo_lang_pairs(pairs: list[tuple[str, str]]) -> Dict[str, str]:
    """Build ``hotkeys`` JSON object: non-empty combo -> lang (only ``LANG_CODES``)."""
    out: Dict[str, str] = {}
    for combo, lang in pairs:
        c = (combo or "").strip()
        l = (lang or "").strip()
        if not c or l not in LANG_CODES:
            continue
        out[c] = l
    return out


_UNICODE_FONT_PRIORITY = (
    # Mkhedruli first: some Segoe / Tk pairings show ``?`` for Georgian in ``Text`` widgets.
    "sylfaen",
    "noto sans georgian",
    "bpg glsan",
    "bpg nino medium el",
    "bpg nino medium cond",
    "bpg nino medium",
    "segoe ui variable",
    "segoe ui",
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
    cancel_event: threading.Event | None = None,
    progress_callback: Any | None = None,  # Callable[[int, int], None] from worker thread
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
                    cancel_event=cancel_event,
                    progress_callback=progress_callback,
                )
            else:
                if progress_callback:
                    progress_callback(0, 1)
                if cancel_event is None:
                    await fast_generate_audio(text, lang, output_path)
                else:
                    await _await_with_cancel(fast_generate_audio(text, lang, output_path), cancel_event)
                if progress_callback:
                    progress_callback(1, 1)

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
        self._speak_cancel = threading.Event()
        self._pip_install_busy = False
        self.hk_native_var = tk.BooleanVar(value=False)
        self._hk_row_vars: list[tuple[Any, Any]] = []
        self._hk_rows_inner: Any = None
        self._hk_rows_canvas: Any = None
        self._hotkeys_rows_built = False

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

        tab_hk = ttk.Frame(nb, padding=8)
        nb.add(tab_hk, text="Hotkeys")
        self._build_hotkeys_tab(tab_hk)

        if sys.platform == "win32":
            tab_win = ttk.Frame(nb, padding=8)
            nb.add(tab_win, text="Windows shell")
            self._build_windows_tab(tab_win)

        tab_about = ttk.Frame(nb, padding=8)
        nb.add(tab_about, text="About")
        self._build_about_tab(tab_about)

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

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=10, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
        self.speak_btn = ttk.Button(btn_row, text="Speak", command=self._on_speak)
        self.speak_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_speak_btn = ttk.Button(btn_row, text="Stop", command=self._on_stop_speak, state=tk.DISABLED)
        self.stop_speak_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Check deps", command=self._on_check_deps).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Quit", command=self._on_quit).pack(side=tk.RIGHT)

        self.speak_progress = ttk.Progressbar(frm, mode="determinate", maximum=1, value=0)
        self.speak_progress.grid(row=11, column=0, columnspan=3, sticky=(tk.E, tk.W), pady=(4, 0))

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status, foreground="#333").grid(
            row=12, column=0, columnspan=3, sticky=tk.W, pady=(6, 0)
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

    def _build_hotkeys_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        ttk.Label(frm, text="Global clipboard hotkeys (Windows, pynput)").grid(row=0, column=0, columnspan=4, sticky=tk.W)

        if sys.platform != "win32":
            ttk.Label(
                frm,
                text="Native global hotkeys are only supported on Windows. "
                "On this platform you can still edit the JSON \"hotkeys\" map for use on a Windows machine.",
                wraplength=520,
                justify=tk.LEFT,
            ).grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
            self._hotkeys_rows_built = True
            self._hk_build_rows_ui(frm, start_row=2)
            self._hotkey_load_rows_from_disk()
            bf = ttk.Frame(frm)
            bf.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(12, 0))
            ttk.Button(bf, text="Reload bindings from config", command=self._hotkey_load_rows_from_disk).pack(
                side=tk.LEFT, padx=(0, 8)
            )
            ttk.Button(bf, text="Save hotkeys to config", command=self._on_hotkey_save_to_config).pack(side=tk.LEFT)
            frm.columnconfigure(1, weight=1)
            frm.rowconfigure(2, weight=1)
            return

        self.hk_pynput_status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.hk_pynput_status, wraplength=520, justify=tk.LEFT).grid(
            row=1, column=0, columnspan=4, sticky=tk.W, pady=(6, 0)
        )
        self._hotkey_refresh_pynput_status()

        pipf = ttk.Frame(frm)
        pipf.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
        ttk.Button(pipf, text="Install TTS_ka[hotkeys]", command=self._on_hotkey_pip_install).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(pipf, text="Uninstall pynput", command=self._on_hotkey_pip_uninstall).pack(side=tk.LEFT)

        ttk.Checkbutton(
            frm,
            text="Enable global hotkeys (while this app is open)",
            variable=self.hk_native_var,
            command=self._on_toggle_native_hotkeys,
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(10, 0))

        ttk.Label(
            frm,
            text="Uses the JSON path from the Config tab. Each shortcut runs: python -m TTS_ka clipboard --lang …",
            wraplength=520,
            justify=tk.LEFT,
        ).grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))

        self._hk_build_rows_ui(frm, start_row=5)
        self._hotkey_load_rows_from_disk()
        self._hotkeys_rows_built = True

        bf2 = ttk.Frame(frm)
        bf2.grid(row=6, column=0, columnspan=4, sticky=tk.W, pady=(10, 0))
        ttk.Button(bf2, text="Add row", command=self._hotkey_add_empty_row).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf2, text="Reload from disk", command=self._hotkey_load_rows_from_disk).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf2, text="Clear custom hotkeys", command=self._on_hotkey_clear_custom).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf2, text="Save hotkeys + apply", command=self._on_hotkey_save_to_config).pack(side=tk.LEFT)

        help_txt = (
            "Combo strings follow pynput (e.g. <ctrl>+<alt>+1). Languages: en, ru, ka, ka-m. "
            "In JSON you can set a combo to null to drop a default. Standalone listener: TTS_ka-hotkeys."
        )
        ttk.Label(frm, text=help_txt, wraplength=520, justify=tk.LEFT).grid(
            row=7, column=0, columnspan=4, sticky=tk.W, pady=(10, 0)
        )
        frm.columnconfigure(1, weight=1)

    def _hk_build_rows_ui(self, frm: Any, *, start_row: int) -> None:
        import tkinter as tk
        from tkinter import ttk

        wrap = ttk.Frame(frm)
        wrap.grid(row=start_row, column=0, columnspan=4, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(8, 0))
        frm.rowconfigure(start_row, weight=1)

        canvas = tk.Canvas(wrap, height=200, highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        inner = ttk.Frame(canvas)
        self._hk_rows_inner = inner
        self._hk_rows_canvas = canvas
        win_id = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        def _sync_scroll(_evt: Any = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                canvas.itemconfigure(win_id, width=canvas.winfo_width())
            except tk.TclError:
                pass

        inner.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        def _wheel(e: Any) -> None:
            if sys.platform == "win32":
                canvas.yview_scroll(int(-1 * (e.delta or 0) / 120), "units")
            else:
                if getattr(e, "num", None) == 4:
                    canvas.yview_scroll(-1, "units")
                elif getattr(e, "num", None) == 5:
                    canvas.yview_scroll(1, "units")

        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Enter>", lambda _e: canvas.focus_set())
        canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)

    def _hotkey_refresh_pynput_status(self) -> None:
        if sys.platform != "win32":
            return
        from .native_hotkeys import NativeHotkeyManager

        if NativeHotkeyManager.available():
            self.hk_pynput_status.set("pynput: installed (global hotkeys can run).")
        else:
            self.hk_pynput_status.set("pynput: not installed — use Install TTS_ka[hotkeys] above.")

    def _hotkey_redraw_rows(self) -> None:
        if self._hk_rows_inner is None:
            return
        from tkinter import ttk

        for w in self._hk_rows_inner.winfo_children():
            w.destroy()
        ttk.Label(self._hk_rows_inner, text="#").grid(row=0, column=0, padx=(0, 4), pady=2)
        ttk.Label(self._hk_rows_inner, text="Combo (pynput)").grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(self._hk_rows_inner, text="Lang").grid(row=0, column=2, padx=4, pady=2)
        for idx, row in enumerate(self._hk_row_vars):
            cv, lv = row
            r = idx + 1
            ttk.Label(self._hk_rows_inner, text=str(idx + 1)).grid(row=r, column=0, padx=(0, 4), pady=2, sticky="w")
            ttk.Entry(self._hk_rows_inner, textvariable=cv, width=32).grid(
                row=r, column=1, padx=4, pady=2, sticky="ew"
            )
            ttk.Combobox(
                self._hk_rows_inner,
                textvariable=lv,
                values=("en", "ru", "ka", "ka-m"),
                width=9,
                state="readonly",
            ).grid(row=r, column=2, padx=4, pady=2)
            ttk.Button(self._hk_rows_inner, text="Remove", command=lambda i=idx: self._hotkey_remove_row(i)).grid(
                row=r, column=3, padx=4, pady=2
            )

    def _hotkey_remove_row(self, index: int) -> None:
        if 0 <= index < len(self._hk_row_vars):
            self._hk_row_vars.pop(index)
            self._hotkey_redraw_rows()

    def _hotkey_add_empty_row(self) -> None:
        import tkinter as tk

        self._hk_row_vars.append((tk.StringVar(value=""), tk.StringVar(value="en")))
        self._hotkey_redraw_rows()

    def _hotkey_load_rows_from_disk(self) -> None:
        import tkinter as tk

        from .native_hotkeys import resolved_hotkey_lang_map

        p = self.config_path_var.get().strip()
        raw = load_user_config(p if p else None)
        m = resolved_hotkey_lang_map(raw)
        self._hk_row_vars = [(tk.StringVar(value=k), tk.StringVar(value=v)) for k, v in m.items()]
        self._hotkey_redraw_rows()

    def _hotkey_gather_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for cv, lv in self._hk_row_vars:
            pairs.append((cv.get(), lv.get()))
        return pairs

    def _hotkey_apply_running_listener(self) -> None:
        from .native_hotkeys import NativeHotkeyManager

        if self._hotkey_mgr is None or not self.hk_native_var.get():
            return
        if not NativeHotkeyManager.available():
            return
        p = self.config_path_var.get().strip()
        raw = load_user_config(p if p else None)
        self._hotkey_mgr.restart(config=raw)

    def _on_hotkey_save_to_config(self) -> None:
        from tkinter import messagebox

        p = self.config_path_var.get().strip()
        if not p:
            messagebox.showwarning("TTS_ka hotkeys", "Set the config file path on the Config tab first.")
            return
        prev = load_user_config(p) if p else {}
        hot = hotkeys_dict_from_combo_lang_pairs(self._hotkey_gather_pairs())
        payload = {**prev, "hotkeys": hot}
        try:
            write_user_config(p, payload)
        except OSError as e:
            messagebox.showerror("TTS_ka hotkeys", str(e))
            return
        self.status.set("Saved hotkeys to config.")
        messagebox.showinfo("TTS_ka hotkeys", f"Saved hotkeys to:\n{p}")
        self._hotkey_apply_running_listener()

    def _on_hotkey_clear_custom(self) -> None:
        from tkinter import messagebox

        p = self.config_path_var.get().strip()
        if not p:
            messagebox.showwarning("TTS_ka hotkeys", "Set the config file path on the Config tab first.")
            return
        if not messagebox.askyesno(
            "TTS_ka hotkeys",
            "Remove the \"hotkeys\" key from your config file?\n"
            "Built-in defaults will apply after reload.",
        ):
            return
        prev = load_user_config(p) if p else {}
        payload = {k: v for k, v in prev.items() if k != "hotkeys"}
        try:
            write_user_config(p, payload)
        except OSError as e:
            messagebox.showerror("TTS_ka hotkeys", str(e))
            return
        self._hotkey_load_rows_from_disk()
        self._hotkey_apply_running_listener()
        messagebox.showinfo("TTS_ka hotkeys", "Removed custom hotkeys from config.")

    def _on_hotkey_pip_install(self) -> None:
        self._run_pip_install_async(("TTS_ka[hotkeys]",), "TTS_ka[hotkeys]", on_success=self._hotkey_refresh_pynput_status)

    def _on_hotkey_pip_uninstall(self) -> None:
        from tkinter import messagebox

        if not messagebox.askyesno(
            "TTS_ka hotkeys",
            "Uninstall the pynput package from this environment?\n"
            "Global hotkeys will stop working until you install again.",
        ):
            return
        self._run_pip_uninstall_async(("pynput",), "pynput")

    def _run_pip_install_async(
        self,
        packages: tuple[str, ...],
        label: str,
        *,
        on_success: Any | None = None,
    ) -> None:
        from tkinter import messagebox

        if self._pip_install_busy:
            self.status.set("pip install already running…")
            return
        self._pip_install_busy = True
        self.status.set(f"pip: installing {label}…")

        def work() -> None:
            err: str | None = None
            out = ""
            try:
                r = run_pip_install(*packages)
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                if r.returncode != 0:
                    err = out or f"exit code {r.returncode}"
            except subprocess.TimeoutExpired:
                err = "pip install timed out."
            except OSError as e:
                err = str(e)

            def done() -> None:
                self._pip_install_busy = False
                if err:
                    self.status.set(f"pip: {label} failed.")
                    messagebox.showerror("TTS_ka - pip install", err[:4000])
                else:
                    self.status.set(f"pip: finished {label}.")
                    messagebox.showinfo("TTS_ka - pip install", (out or "Done.")[:4000])
                    if on_success is not None:
                        on_success()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _run_pip_uninstall_async(self, packages: tuple[str, ...], label: str) -> None:
        from tkinter import messagebox

        if self._pip_install_busy:
            self.status.set("pip already running…")
            return
        self._pip_install_busy = True
        self.status.set(f"pip: uninstalling {label}…")

        def work() -> None:
            err: str | None = None
            out = ""
            try:
                r = run_pip_uninstall(*packages)
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                if r.returncode != 0:
                    err = out or f"exit code {r.returncode}"
            except subprocess.TimeoutExpired:
                err = "pip uninstall timed out."
            except OSError as e:
                err = str(e)

            def done() -> None:
                self._pip_install_busy = False
                if err:
                    self.status.set(f"pip: uninstall {label} failed.")
                    messagebox.showerror("TTS_ka - pip uninstall", err[:4000])
                else:
                    self.status.set(f"pip: uninstalled {label}.")
                    messagebox.showinfo("TTS_ka - pip uninstall", (out or "Done.")[:4000])
                    if self._hotkey_mgr is not None:
                        self._hotkey_mgr.stop()
                    self.hk_native_var.set(False)
                    self._hotkey_refresh_pynput_status()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _build_windows_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        ttk.Label(
            frm,
            text="Explorer context menu (clipboard / .txt). Global hotkeys: use the Hotkeys tab.",
            wraplength=500,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky=tk.W)

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=1, column=0, sticky=(tk.E, tk.W), pady=10)

        self.cm_include_txt = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm,
            text='Add "read this .txt file" entries (per-language) to right-click on .txt',
            variable=self.cm_include_txt,
        ).grid(row=2, column=0, sticky=tk.W)

        ttk.Label(
            frm,
            text="Registers Explorer / Desktop background menu (per-user HKCU). "
            "Requires the repo script extras/windows/context_menu/Install-TTS_ka-ContextMenu.ps1 "
            "(not shipped in the PyPI wheel unless you have that tree next to the package).",
            wraplength=480,
            justify=tk.LEFT,
        ).grid(row=3, column=0, sticky=tk.W, pady=(8, 0))

        bf = ttk.Frame(frm)
        bf.grid(row=4, column=0, sticky=tk.W, pady=(12, 0))
        ttk.Button(bf, text="Install context menu", command=self._on_install_context_menu).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(bf, text="Uninstall context menu", command=self._on_uninstall_context_menu).pack(side=tk.LEFT)

        self.cm_status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.cm_status, wraplength=480, justify=tk.LEFT).grid(
            row=5, column=0, sticky=tk.W, pady=(10, 0)
        )

    def _build_about_tab(self, frm: Any) -> None:
        import tkinter as tk
        from tkinter import ttk

        from . import __version__ as pkg_version

        try:
            dist_ver = importlib.metadata.version("TTS_ka")
        except importlib.metadata.PackageNotFoundError:
            dist_ver = pkg_version

        ttk.Label(frm, text="TTS_ka").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(frm, text=f"Version {dist_ver}").grid(row=1, column=0, sticky=tk.W, pady=(2, 0))
        ttk.Label(
            frm,
            text="Ultra-fast TTS for Georgian, Russian, and English (edge-tts).",
            wraplength=520,
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky=tk.W, pady=(10, 0))

        link_f = ttk.Frame(frm)
        link_f.grid(row=3, column=0, sticky=tk.W, pady=(14, 0))
        ttk.Button(link_f, text="Full documentation (readme)", command=self._on_open_docs).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(link_f, text="GitHub project", command=self._on_open_home).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(link_f, text="Issues", command=self._on_open_issues).pack(side=tk.LEFT)

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=4, column=0, sticky=(tk.E, tk.W), pady=16)

        ttk.Label(frm, text="Optional Python packages (pip)").grid(row=5, column=0, sticky=tk.W)
        ttk.Label(
            frm,
            text="Uses the same Python environment as this app. You may need to close and reopen the GUI "
            "after installing. Requires network access.",
            wraplength=520,
            justify=tk.LEFT,
        ).grid(row=6, column=0, sticky=tk.W, pady=(6, 0))

        bf = ttk.Frame(frm)
        bf.grid(row=7, column=0, sticky=tk.W, pady=(10, 0))
        ttk.Button(bf, text="Install soundfile", command=self._on_pip_install_soundfile).pack(side=tk.LEFT, padx=(0, 8))
        if not sys.platform.startswith("win"):
            ttk.Button(bf, text="Install uvloop", command=self._on_pip_install_uvloop).pack(side=tk.LEFT)

        tip = (
            "Install global hotkeys (pynput) from the Hotkeys tab on Windows. "
            "Commands: pip install \"TTS_ka[soundfile]\"  |  pip install uvloop (Unix/macOS)"
        )
        ttk.Label(frm, text=tip, wraplength=520, justify=tk.LEFT).grid(row=8, column=0, sticky=tk.W, pady=(12, 0))

    def _on_open_docs(self) -> None:
        webbrowser.open(_docs_url(), new=2)

    def _on_open_home(self) -> None:
        webbrowser.open(_homepage_url(), new=2)

    def _on_open_issues(self) -> None:
        urls = _project_urls_from_metadata()
        webbrowser.open(urls.get("issues") or f"{_DEFAULT_HOME_URL}/issues", new=2)

    def _on_pip_install_soundfile(self) -> None:
        self._run_pip_install_async(("TTS_ka[soundfile]",), "TTS_ka[soundfile]")

    def _on_pip_install_uvloop(self) -> None:
        self._run_pip_install_async(("uvloop",), "uvloop")

    def _on_quit(self) -> None:
        if self._hotkey_mgr is not None:
            self._hotkey_mgr.stop()
        self.root.destroy()

    def _on_toggle_native_hotkeys(self) -> None:
        from tkinter import messagebox

        from .user_config import load_user_config

        if self._hotkey_mgr is None:
            return
        if self.hk_native_var.get():
            p = self.config_path_var.get().strip()
            raw = load_user_config(p if p else None)
            if not self._hotkey_mgr.start(config=raw):
                messagebox.showwarning(
                    "TTS_ka hotkeys",
                    "Install the optional dependency, then try again:\n\n  pip install 'TTS_ka[hotkeys]'",
                )
                self.hk_native_var.set(False)
        else:
            self._hotkey_mgr.stop()

    def mainloop(self) -> None:
        self.root.mainloop()

    def _apply_speak_progress(self, done: int, total: int) -> None:
        t = max(int(total), 1)
        d = min(max(int(done), 0), t)
        self.speak_progress.configure(maximum=t, value=d)
        self.status.set(f"Generating… chunk {d} / {t}")

    def _on_stop_speak(self) -> None:
        self._speak_cancel.set()
        self.status.set("Stopping after current work units finish…")

    def _set_busy(self, busy: bool) -> None:
        state = self._tk.DISABLED if busy else self._tk.NORMAL
        self.speak_btn.configure(state=state)
        self.stop_speak_btn.configure(state=self._tk.NORMAL if busy else self._tk.DISABLED)
        if not busy:
            self.speak_progress.configure(value=0, maximum=1)

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
        if getattr(self, "_hotkeys_rows_built", False):
            self._hotkey_load_rows_from_disk()
            self._hotkey_apply_running_listener()
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

        self._speak_cancel.clear()
        self._set_busy(True)
        self.status.set("Generating…")
        self._apply_speak_progress(0, 1)

        def progress_cb(done: int, total: int) -> None:
            self.root.after(0, lambda d=done, t=total: self._apply_speak_progress(d, t))

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
                    cancel_event=self._speak_cancel,
                    progress_callback=progress_cb,
                )
            except SystemExit as se:
                code = se.code
                if code not in (0, None):
                    err = "Streaming stopped: install VLC for GUI streaming, or turn off \"VLC window\"."
            except GenerationCancelled:
                err = "Cancelled."
            except KeyboardInterrupt:
                err = "Cancelled."
            except BaseException:
                err = traceback.format_exc()

            def done() -> None:
                from tkinter import messagebox

                self._set_busy(False)
                if err == "Cancelled.":
                    self.status.set("Generation cancelled.")
                    return
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
