"""mpv JSON-IPC driver: gapless, controllable streaming playback (POSIX).

Why not ``mpv --playlist=-``: a headless mpv fed a stdin playlist exits as
soon as it plays out what it has, so a chunk that is still synthesizing when
the previous one ends is never heard. Here mpv runs with ``--idle=yes`` and is
driven over its ``--input-ipc-server`` Unix socket instead:

* ``loadfile <path> append-play`` queues a chunk and starts playback if mpv
  went idle in a gap, so gaps between chunks are bridged.
* ``end-file`` events and the ``idle-active`` property give a real "finished
  playing everything" signal (``wait_done``).
* ``pause`` / ``resume`` / ``skip`` / ``stop`` map to mpv commands.

Only headless playback uses this. A GUI mpv keeps the stdin playlist with
``--keep-open``, which bridges gaps on its own, offers its own controls, and
is the invocation user wrappers around ``mpv`` already recognise.

The socket lives in a private dir under ``tempfile.gettempdir()``: a flatpak
mpv can create sockets in ``/tmp`` but not in ``XDG_RUNTIME_DIR``.

Windows is not supported (mpv's named pipe needs overlapped I/O to read and
write concurrently); the caller keeps using the stdin playlist there. Set
``TTS_KA_MPV_IPC=0`` to disable IPC everywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable, Dict, List, Optional, Set

CONNECT_TIMEOUT = 10.0  # flatpak cold starts can take a few seconds
REPLY_TIMEOUT = 2.0
_IDLE_PROPERTY_ID = 1


class MpvIpcError(RuntimeError):
    """mpv could not be started, reached, or did not accept a command."""


def ipc_supported() -> bool:
    """True when this platform can drive mpv over a Unix socket and it isn't disabled."""
    flag = os.environ.get("TTS_KA_MPV_IPC", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return os.name == "posix" and hasattr(socket, "AF_UNIX")


class MpvIpc:
    """One mpv process plus its IPC connection.

    *on_error* is called with the path-less ``end-file`` event when mpv fails
    to play an entry (e.g. a corrupt chunk); playback continues with the next.
    """

    def __init__(self, player: str, *,
                 on_error: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.player = player
        self.process: Optional[subprocess.Popen] = None
        self._on_error = on_error
        self._dir: Optional[str] = None
        self._sock: Optional[socket.socket] = None
        self._write_lock = threading.Lock()
        self._next_id = 1
        self._replies: Dict[int, "Queue[Optional[Dict[str, Any]]]"] = {}
        self._state = threading.Condition()
        self._appended: Set[int] = set()   # playlist_entry_ids we queued
        self._ended: Set[int] = set()      # playlist_entry_ids that finished
        self._appended_anon = 0            # mpv < 0.33 reports no entry ids
        self._ended_anon = 0
        self._idle = False
        self._stopped = False
        self._disconnected = False
        self._closed = False

    def argv(self, sock_path: str) -> List[str]:
        return [
            self.player,
            "--idle=yes",
            # Launched without a tty mpv would pick pseudo-gui mode and open a window.
            "--player-operation-mode=cplayer",
            "--no-video",
            "--audio-display=no",
            "--no-terminal",
            "--gapless-audio=yes",
            f"--input-ipc-server={sock_path}",
        ]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, connect_timeout: float = CONNECT_TIMEOUT) -> None:
        """Spawn mpv and connect to its socket; raise ``MpvIpcError`` on failure."""
        self._dir = tempfile.mkdtemp(prefix="ttska-mpv-")
        sock_path = os.path.join(self._dir, "ipc.sock")
        try:
            self.process = subprocess.Popen(
                self.argv(sock_path),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._cleanup_dir()
            raise MpvIpcError(f"could not start {self.player}: {exc}") from exc

        deadline = time.monotonic() + connect_timeout
        while True:
            if self.process.poll() is not None:
                self._cleanup_dir()
                raise MpvIpcError(f"{self.player} exited before opening its IPC socket")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(sock_path)
                break
            except OSError:
                sock.close()
            if time.monotonic() >= deadline:
                self.close(quit=False)
                raise MpvIpcError(f"{self.player} did not open its IPC socket "
                                  f"within {connect_timeout:.0f}s")
            time.sleep(0.05)

        self._sock = sock
        threading.Thread(target=self._read_loop, daemon=True).start()
        self.command("observe_property", _IDLE_PROPERTY_ID, "idle-active")

    def close(self, quit: bool = True) -> None:
        """Quit mpv (killing it if it lingers) and remove the socket dir. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if quit and self._sock is not None:
            try:
                self.command("quit", timeout=0.5)
            except MpvIpcError:
                pass
        proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._cleanup_dir()

    def _cleanup_dir(self) -> None:
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None

    # ── Commands ──────────────────────────────────────────────────────────────

    def command(self, *args: Any, timeout: float = REPLY_TIMEOUT) -> Any:
        """Send one IPC command and return its ``data``; raise ``MpvIpcError`` on failure."""
        with self._write_lock:
            sock = self._sock
            if sock is None:
                raise MpvIpcError("mpv IPC is not connected")
            rid = self._next_id
            self._next_id += 1
            reply_q: "Queue[Optional[Dict[str, Any]]]" = Queue(maxsize=1)
            self._replies[rid] = reply_q
            line = json.dumps({"command": list(args), "request_id": rid}) + "\n"
            try:
                sock.sendall(line.encode("utf-8"))
            except OSError as exc:
                self._replies.pop(rid, None)
                raise MpvIpcError(f"mpv IPC write failed: {exc}") from exc
        try:
            reply = reply_q.get(timeout=timeout)
        except Empty:
            raise MpvIpcError(f"mpv did not answer {args[0]!r}") from None
        finally:
            self._replies.pop(rid, None)
        if reply is None:
            raise MpvIpcError("mpv IPC connection closed")
        if reply.get("error") != "success":
            raise MpvIpcError(f"mpv {args[0]!r} failed: {reply.get('error')}")
        return reply.get("data")

    def append(self, path: str) -> None:
        """Queue *path* after whatever is playing; starts playback if mpv is idle."""
        data = self.command("loadfile", os.path.abspath(path), "append-play")
        entry_id = data.get("playlist_entry_id") if isinstance(data, dict) else None
        with self._state:
            if entry_id is None:
                self._appended_anon += 1
            else:
                self._appended.add(entry_id)

    def pause(self) -> None:
        self.command("set_property", "pause", True)

    def resume(self) -> None:
        self.command("set_property", "pause", False)

    def set_speed(self, speed: float) -> None:
        """Set the playback speed multiplier; it carries over to later chunks."""
        self.command("set_property", "speed", speed)

    def skip(self) -> None:
        """Jump to the next queued chunk (or go idle if this was the last)."""
        self.command("playlist-next", "force")

    def stop(self) -> None:
        """Stop playback and clear the playlist; ``wait_done`` returns at once."""
        with self._state:
            self._stopped = True
            self._state.notify_all()
        self.command("stop")

    def wait_done(self, timeout: Optional[float] = None,
                  should_continue: Callable[[], bool] = lambda: True) -> bool:
        """Block until every appended chunk has played and mpv is idle.

        Returns True when playback is over (also when mpv exited or ``stop``
        was called), False on *timeout* or once *should_continue* turns false.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._state:
            while True:
                if self._stopped or self._disconnected:
                    return True
                if self._idle and self._all_ended_locked():
                    return True
                if not should_continue():
                    return False
                wait = 0.25
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    wait = min(wait, remaining)
                self._state.wait(wait)

    def _all_ended_locked(self) -> bool:
        return self._appended <= self._ended and self._appended_anon <= self._ended_anon

    # ── Reader thread ─────────────────────────────────────────────────────────

    def _read_loop(self) -> None:
        sock = self._sock
        try:
            assert sock is not None
            for raw in sock.makefile("rb"):
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if "event" in msg:
                    self._handle_event(msg)
                elif "request_id" in msg:
                    reply_q = self._replies.get(msg["request_id"])
                    if reply_q is not None:
                        reply_q.put(msg)
        except (OSError, ValueError, AssertionError):
            pass
        finally:
            with self._state:
                self._disconnected = True
                self._state.notify_all()
            for reply_q in list(self._replies.values()):
                try:
                    reply_q.put_nowait(None)
                except Exception:
                    pass

    def _handle_event(self, msg: Dict[str, Any]) -> None:
        event = msg.get("event")
        failed = False
        with self._state:
            if event == "end-file":
                entry_id = msg.get("playlist_entry_id")
                if entry_id is None:
                    self._ended_anon += 1
                else:
                    self._ended.add(entry_id)
                failed = msg.get("reason") == "error"
            elif event == "property-change" and msg.get("id") == _IDLE_PROPERTY_ID:
                self._idle = bool(msg.get("data"))
            self._state.notify_all()
        if failed and self._on_error is not None:
            self._on_error(msg)
