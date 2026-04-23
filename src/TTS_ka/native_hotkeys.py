"""Windows global hotkeys for clipboard TTS (optional ``pynput`` — no AutoHotkey).

Install::

    pip install "TTS_ka[hotkeys]"

Default bindings (clipboard is read the same way as ``TTS_ka clipboard``):

* ``Ctrl+Alt+1`` — English
* ``Ctrl+Alt+2`` — Russian
* ``Ctrl+Alt+3`` — Georgian (female)
* ``Ctrl+Alt+4`` — Georgian (male)

Run standalone (until you press Enter)::

    TTS_ka-hotkeys
    python -m TTS_ka.native_hotkeys

Or enable from the GUI **Windows shell** tab when ``pynput`` is installed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from typing import Callable, Dict, Optional

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


def default_hotkey_callbacks() -> Dict[str, Callable[[], None]]:
    """Map pynput combo string -> no-arg callback."""

    def make(lang: str) -> Callable[[], None]:
        def _cb() -> None:
            try:
                spawn_clipboard_tts(lang)
            except OSError:
                pass

        return _cb

    return {combo: make(lang) for combo, lang in DEFAULT_HOTKEY_LANG.items()}


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

    def start(self, mapping: Optional[Dict[str, Callable[[], None]]] = None) -> bool:
        """Register global hotkeys. Returns False if ``pynput`` is missing or not Windows."""
        if not self.available():
            return False
        from pynput import keyboard

        with self._lock:
            if self._listener is not None:
                return True
            hot = mapping if mapping is not None else default_hotkey_callbacks()
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


def print_hotkey_help() -> None:
    lines = [
        "TTS_ka native global hotkeys (Windows, clipboard)",
        "Requires: pip install 'TTS_ka[hotkeys]'",
        "",
        "Defaults:",
    ]
    for combo, lang in DEFAULT_HOTKEY_LANG.items():
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
    print_hotkey_help()
    mgr = NativeHotkeyManager()
    if not mgr.start():
        sys.exit(1)
    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop()


if __name__ == "__main__":
    main()
