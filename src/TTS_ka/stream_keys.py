"""Single-key playback controls while the CLI streams (``--stream``, ``--live``).

    space / p   pause / resume
    n           next chunk
    + / -       speed up / slow down (mpv ``speed``; pitch is preserved)
    q           quit, same as Ctrl+C

Keys are read from ``/dev/tty`` rather than stdin, so they work when the text
itself is piped in. The terminal goes into cbreak mode (no echo, no line
buffering, Ctrl+C still raises SIGINT) and is restored on exit.

Controls need a player ``StreamingAudioPlayer`` can drive: headless mpv over
JSON IPC (POSIX). Nothing is set up on Windows, without a controlling
terminal (hotkeys, the GUI, cron) or from a background job, where touching
the terminal would stop the process with SIGTTOU.
"""

from __future__ import annotations

import os
import re
import signal
import sys
import threading
from typing import Optional

from .rich_progress import cprint

SPEED_STEP = 0.1
HINT = "  [dim]⌨  space pause · n next · +/- speed · q quit[/dim]"
NOT_CONTROLLABLE = "  [dim]⌨  playback keys need headless mpv (not this player)[/dim]"
# CSI (ESC [ … final byte), SS3 (ESC O x), or ESC plus one byte (Alt+key).
_ESCAPE_SEQ = re.compile(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|O.|.)?", re.DOTALL)


class KeyControls:
    """Read single keys in a thread and drive *player*; use as a context manager."""

    def __init__(self, player, tty_path: str = "/dev/tty") -> None:
        self._player = player
        self._tty_path = tty_path
        self._fd: Optional[int] = None
        self._saved_attrs: Optional[list] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._paused = False
        self._hinted = False
        self._warned = False

    @property
    def active(self) -> bool:
        return self._thread is not None

    def __enter__(self) -> "KeyControls":
        return self.start()

    def start(self) -> "KeyControls":
        """Take over the terminal and start reading keys, when that is possible."""
        if sys.platform.startswith("win"):
            return self
        import termios
        import tty

        try:
            fd = os.open(self._tty_path, os.O_RDONLY | os.O_NOCTTY)
        except OSError:
            return self
        try:
            if os.tcgetpgrp(fd) != os.getpgrp():
                os.close(fd)
                return self
            self._saved_attrs = termios.tcgetattr(fd)
            tty.setcbreak(fd, termios.TCSANOW)
        except (OSError, termios.error):
            os.close(fd)
            return self
        self._fd = fd
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        """Stop reading keys and restore the terminal. Safe to call twice."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._fd is not None:
            import termios

            try:
                if self._saved_attrs is not None:
                    termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)
            except (OSError, termios.error):
                pass
            os.close(self._fd)
            self._fd = None

    def _read_loop(self) -> None:
        import select

        assert self._fd is not None
        while not self._stop.is_set():
            if not self._hinted and self._player.controllable:
                self._hinted = True
                cprint(HINT)
            ready, _, _ = select.select([self._fd], [], [], 0.2)
            if not ready:
                continue
            try:
                data = os.read(self._fd, 32)
            except OSError:
                return
            if not data:
                return
            # Arrow / function keys arrive as escape sequences; drop them, not
            # the plain keys that may share the read.
            data = _ESCAPE_SEQ.sub(b"", data)
            for key in data.decode("utf-8", errors="ignore"):
                message = self.handle(key)
                if message:
                    cprint(message)

    def handle(self, key: str) -> Optional[str]:
        """Apply one key press; return a status line to show, or None."""
        player = self._player
        if key == "q":
            os.kill(os.getpid(), signal.SIGINT)
            return None
        if key not in " pn+=-_":
            return None
        if not player.controllable:
            if self._warned:
                return None
            self._warned = True
            return NOT_CONTROLLABLE
        if key in " p":
            if self._paused:
                if player.resume():
                    self._paused = False
                    return "  ▶  resumed"
            elif player.pause():
                self._paused = True
                return "  ⏸  paused  [dim](space to resume)[/dim]"
            return None
        if key == "n":
            return "  ⏭  next" if player.skip_current() else None
        speed = player.change_speed(SPEED_STEP if key in "+=" else -SPEED_STEP)
        return f"  ⏩  speed {speed:.1f}×" if speed is not None else None
