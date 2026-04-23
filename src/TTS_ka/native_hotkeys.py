"""Windows global hotkeys for clipboard TTS (optional ``pynput`` — no AutoHotkey).

Install::

    pip install "TTS_ka[hotkeys]"

Default bindings (clipboard is read the same way as ``TTS_ka clipboard``):

* ``Ctrl+Alt+1`` — English
* ``Ctrl+Alt+2`` — Russian
* ``Ctrl+Alt+3`` — Georgian (female)
* ``Ctrl+Alt+4`` — Georgian (male)

Override or extend via JSON config (same file as other TTS_ka settings), key ``hotkeys``:
map of pynput combo string to language code; use ``null`` to remove a default binding.
See ``extras/tts_config.example.json``.

Run standalone (until you press Enter)::

    TTS_ka-hotkeys
    python -m TTS_ka.native_hotkeys

Or enable from the GUI **Hotkeys** tab when ``pynput`` is installed.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, Mapping, Optional

from .user_config import load_user_config, merge_hotkey_bindings

# combo string -> --lang value (must match CLI)
DEFAULT_HOTKEY_LANG: Dict[str, str] = {
    "<ctrl>+<alt>+1": "en",
    "<ctrl>+<alt>+2": "ru",
    "<ctrl>+<alt>+3": "ka",
    "<ctrl>+<alt>+4": "ka-m",
}


def pynput_available() -> bool:
    return importlib.util.find_spec("pynput") is not None


def clipboard_tts_argv(lang: str) -> list[str]:
    """Argv to run ``python -m TTS_ka clipboard --lang …`` (detached)."""
    return [sys.executable, "-m", "TTS_ka", "clipboard", "--lang", lang]


def spawn_clipboard_tts(lang: str) -> None:
    """Start TTS_ka on the clipboard in a new process (non-blocking)."""
    argv = clipboard_tts_argv(lang)
    kw: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(argv, **kw)


def _callbacks_from_lang_map(lang_by_combo: Mapping[str, str]) -> Dict[str, Callable[[], None]]:
    """Map pynput combo string -> no-arg callback."""

    def make(lang: str) -> Callable[[], None]:
        def _cb() -> None:
            try:
                spawn_clipboard_tts(lang)
            except OSError:
                pass

        return _cb

    return {combo: make(lang) for combo, lang in lang_by_combo.items()}


def resolved_hotkey_lang_map(cfg: Mapping[str, Any] | None) -> Dict[str, str]:
    """Defaults merged with ``cfg['hotkeys']`` when *cfg* is not ``None``."""
    if cfg is None:
        return dict(DEFAULT_HOTKEY_LANG)
    return merge_hotkey_bindings(cfg, DEFAULT_HOTKEY_LANG)


def hotkey_callbacks_for_config(cfg: Mapping[str, Any] | None) -> Dict[str, Callable[[], None]]:
    """Build pynput callbacks from merged config (``hotkeys`` + defaults)."""
    return _callbacks_from_lang_map(resolved_hotkey_lang_map(cfg))


def default_hotkey_callbacks(cfg: Mapping[str, Any] | None = None) -> Dict[str, Callable[[], None]]:
    """Backward-compatible name: same as :func:`hotkey_callbacks_for_config`."""
    return hotkey_callbacks_for_config(cfg)


class NativeHotkeyManager:
    """Start/stop a ``pynput.keyboard.GlobalHotKeys`` listener (single-use per start)."""

    def __init__(self) -> None:
        self._listener: Optional[object] = None
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return pynput_available() and sys.platform == "win32"

    def is_running(self) -> bool:
        with self._lock:
            return self._listener is not None

    def start(
        self,
        mapping: Optional[Dict[str, Callable[[], None]]] = None,
        *,
        config: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Register global hotkeys.

        Pass ``mapping`` for full control, or ``config`` (loaded JSON) to use ``hotkeys`` + defaults,
        or omit both to load config from ``TTS_KA_CONFIG`` / default ``~/.tts_config.json`` chain.
        """
        if not self.available():
            return False
        from pynput import keyboard

        with self._lock:
            if self._listener is not None:
                return True
            if mapping is not None:
                hot = mapping
            elif config is not None:
                hot = hotkey_callbacks_for_config(dict(config))
            else:
                ex = os.environ.get("TTS_KA_CONFIG", "").strip() or None
                hot = hotkey_callbacks_for_config(load_user_config(ex))
            self._listener = keyboard.GlobalHotKeys(hot)
            self._listener.start()
        return True

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
            try:
                listener.join(timeout=3)
            except Exception:
                pass

    def restart(
        self,
        mapping: Optional[Dict[str, Callable[[], None]]] = None,
        *,
        config: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Stop the listener if running, then :meth:`start` with the same arguments."""
        self.stop()
        return self.start(mapping=mapping, config=config)


def print_hotkey_help(cfg: Mapping[str, Any] | None = None) -> None:
    lines = [
        "TTS_ka native global hotkeys (Windows, clipboard)",
        "Requires: pip install 'TTS_ka[hotkeys]'",
        "",
        "Effective bindings (defaults + ~/.tts_config.json hotkeys):",
    ]
    for combo, lang in resolved_hotkey_lang_map(cfg).items():
        lines.append(f"  {combo:24}  ->  clipboard --lang {lang}")
    lines.extend(
        [
            "",
            "Copy text, press the shortcut; a new ``python -m TTS_ka`` process runs.",
            "Press Enter here to stop the hotkey listener.",
        ]
    )
    print("\n".join(lines))


def main() -> None:
    if sys.platform != "win32":
        print("Native hotkeys are only supported on Windows.", file=sys.stderr)
        sys.exit(1)
    if not NativeHotkeyManager.available():
        print("Install the optional dependency: pip install 'TTS_ka[hotkeys]'", file=sys.stderr)
        sys.exit(1)
    ex = os.environ.get("TTS_KA_CONFIG", "").strip() or None
    cfg = load_user_config(ex)
    print_hotkey_help(cfg)
    mgr = NativeHotkeyManager()
    if not mgr.start(config=cfg):
        sys.exit(1)
    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop()


if __name__ == "__main__":
    main()
