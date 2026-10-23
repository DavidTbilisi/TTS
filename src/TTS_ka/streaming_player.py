"""Streaming audio playback — play audio while it is still being generated.

Design
------
``PlayerDetector`` encapsulates all platform-specific player-discovery
logic, keeping ``StreamingAudioPlayer`` focused on queue management and
thread coordination. On Windows with VLC, playback prefers a **single**
VLC process controlled over TCP **oldrc** (``add`` / ``enqueue``); set
``TTS_KA_VLC_RC=0`` to force legacy one-window-per-chunk mode.

``StreamingAudioPlayer`` is the primary public interface:

1. Call ``start()`` before generation begins.
2. Call ``add_chunk(path, chunk_index=…)`` as each part finishes (index keeps
   playback order when generation finishes out-of-order), or
   ``skip_index(i)`` for a chunk that will never come (empty or failed), so
   later chunks are not held back waiting for it.
3. Call ``finish_generation()`` when all chunks are queued.
4. Call ``wait_until_released()`` before deleting the chunk files (or
   ``wait_for_completion()`` to just join the playback thread).

On POSIX, headless mpv is driven over JSON IPC (:mod:`mpv_ipc`): chunks are
appended to an idle mpv as they arrive, which bridges synthesis gaps and
enables ``pause`` / ``resume`` / ``skip_current``. GUI mpv, other players and
Windows keep their previous mechanisms; those control methods then return
``False``.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import sys
import socket
import subprocess
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Set

from .constants import PLAYBACK_JOIN_TIMEOUT
from .mpv_ipc import MpvIpc, MpvIpcError, ipc_supported, kill_process_group

# Range for change_speed (mpv keeps pitch through its scaletempo filter).
MIN_SPEED = 0.5
MAX_SPEED = 2.5

# VLC legacy RC over TCP (stdin RC is unreliable on Windows — see VideoLAN issues).
_RC_CONNECT_ATTEMPTS = 50
_RC_CONNECT_DELAY_SEC = 0.08
_RC_CMD_READ_TIMEOUT = 0.35
_RC_IS_PLAYING_READ_TIMEOUT = 1.25


def _vlc_use_rc() -> bool:
    v = os.environ.get("TTS_KA_VLC_RC", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _pick_local_rc_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _filepath_to_mrl(path: str) -> str:
    return Path(os.path.abspath(path)).as_uri()


def _connect_vlc_rc(port: int) -> Optional[socket.socket]:
    for _ in range(_RC_CONNECT_ATTEMPTS):
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.25)
        except OSError:
            time.sleep(_RC_CONNECT_DELAY_SEC)
    return None


def _terminate_process_quietly(proc: Optional[subprocess.Popen]) -> None:
    """Terminate *proc* (its whole process group when it leads one), killing it if it
    ignores SIGTERM for 2 s."""
    if proc is None:
        return
    try:
        kill_process_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            kill_process_group(proc)
            proc.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        pass


# Every started ``StreamingAudioPlayer`` that is still playing — stopped on Ctrl+C.
_active_streaming_players: Set["StreamingAudioPlayer"] = set()
_active_lock = threading.Lock()


def register_active_streaming_player(player: Optional["StreamingAudioPlayer"]) -> None:
    if player is None:
        return
    with _active_lock:
        _active_streaming_players.add(player)


def unregister_active_streaming_player(player: "StreamingAudioPlayer") -> None:
    with _active_lock:
        _active_streaming_players.discard(player)


def stop_all_streaming_players() -> None:
    """Terminate playback for every active streaming player (e.g. Ctrl+C, MCP ``stop``)."""
    with _active_lock:
        players = list(_active_streaming_players)
    for p in players:
        p.stop()


# Older name, kept for callers that predate multiple concurrent players.
stop_active_streaming_player = stop_all_streaming_players


# ── Player detection ──────────────────────────────────────────────────────────

class PlayerDetector:
    """Finds a suitable streaming audio player on the current platform.

    Preference order: mpv → vlc → ffplay → mplayer.
    On Windows, common installation paths are checked for both mpv and vlc
    when they are not on ``PATH``.
    """

    _CANDIDATES: List[str] = ["mpv", "vlc", "ffplay", "mplayer"]
    _WIN_VLC_PATHS: List[str] = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    _WIN_MPV_PATHS: List[str] = [
        r"C:\Program Files\MPV Player\mpv.exe",
        r"C:\Program Files (x86)\MPV Player\mpv.exe",
    ]

    @classmethod
    def find(cls, preferred: Optional[str] = None) -> Optional[str]:
        """Return the executable path/name of the first available player.

        When *preferred* is set, that player is tried first; if available it
        wins. If not, fall through to the default candidate list so streaming
        still works.
        """
        candidates: List[str] = list(cls._CANDIDATES)
        if preferred:
            candidates = [preferred] + [c for c in candidates if c != preferred]
        for player in candidates:
            path = cls._locate(player)
            if path:
                return path
        return None

    @classmethod
    def _locate(cls, player: str) -> Optional[str]:
        if shutil.which(player):
            return player
        if sys.platform.startswith("win"):
            fallbacks = {"vlc": cls._WIN_VLC_PATHS, "mpv": cls._WIN_MPV_PATHS}
            for path in fallbacks.get(player, []):
                if os.path.exists(path):
                    return path
        return None


# ── Streaming player ──────────────────────────────────────────────────────────

class StreamingAudioPlayer:
    """Plays audio chunks as they become available during generation."""

    def __init__(self, show_gui: bool = True, preferred: Optional[str] = None) -> None:
        self.chunk_queue: Queue = Queue()
        self.playback_thread: Optional[threading.Thread] = None
        self.is_playing = False
        self.finished_generating = False
        self.process: Optional[subprocess.Popen] = None
        self.show_gui = show_gui
        self.preferred = preferred
        self._pending: Dict[int, str] = {}
        self._skipped: Set[int] = set()
        self._next_play_index: int = 0
        self._order_lock = threading.Lock()
        self._ipc: Optional[MpvIpc] = None
        self._stopped = False
        # Set once the player no longer needs any chunk file (e.g. mpv IPC saw
        # every chunk end), even if a GUI window is left open afterwards.
        self._released = False
        self._speed = 1.0
        # First reason a chunk could not be played (mpv IPC only), for callers
        # that report success, e.g. MCP ``speak``.
        self.playback_error: Optional[str] = None

    # ── Public interface ──────────────────────────────────────────────────────

    @staticmethod
    def _infer_chunk_index(chunk_path: str) -> Optional[int]:
        """Parse ``.part_<n>.mp3`` / ``.part_<n>_<ts>.mp3`` basename; else ``None``."""
        base = os.path.basename(chunk_path)
        m = re.match(r"\.part_(\d+)(?:_\d+)?\.mp3$", base, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def add_chunk(self, chunk_path: str, chunk_index: Optional[int] = None) -> None:
        """Enqueue a generated chunk for playback in **document order**.

        Parallel generation finishes chunks out of order; pass the chunk's
        zero-based index so playback stays sequential. If *chunk_index* is omitted
        and the basename matches ``.part_<n>.mp3``, *n* is used. Otherwise the
        path is queued immediately (legacy callers / tests).
        """
        if self._stopped:
            return
        idx = chunk_index
        if idx is None and chunk_path:
            idx = self._infer_chunk_index(chunk_path)
        if not chunk_path or not os.path.exists(chunk_path) or os.path.getsize(chunk_path) <= 0:
            # Nothing to play, but later chunks must not wait for this one.
            if idx is not None:
                self.skip_index(idx)
            return
        if idx is None:
            self.chunk_queue.put(chunk_path)
            return
        with self._order_lock:
            self._pending[idx] = chunk_path
            self._advance_locked()

    def skip_index(self, chunk_index: int) -> None:
        """Mark chunk *chunk_index* as never coming (empty or failed synthesis).

        Without this, every later chunk would be held back until
        ``finish_generation()``, i.e. a single failed sentence would silence
        the rest of a live stream.
        """
        with self._order_lock:
            if chunk_index >= self._next_play_index:
                self._skipped.add(chunk_index)
            self._advance_locked()

    def _advance_locked(self) -> None:
        """Release every chunk that is next in order; caller holds ``_order_lock``."""
        while True:
            i = self._next_play_index
            if i in self._pending:
                self.chunk_queue.put(self._pending.pop(i))
            elif i in self._skipped:
                self._skipped.discard(i)
            else:
                return
            self._next_play_index += 1

    def finish_generation(self) -> None:
        """Signal that no more chunks will be added."""
        if self.finished_generating:
            return
        self.finished_generating = True
        with self._order_lock:
            self._advance_locked()
            self._skipped.clear()
            for k in sorted(self._pending.keys()):
                self.chunk_queue.put(self._pending.pop(k))
            self._pending.clear()
        self.chunk_queue.put(None)  # sentinel

    def start(self) -> None:
        """Start the background playback thread."""
        if self.is_playing:
            return
        self.is_playing = True
        self.playback_thread = threading.Thread(
            target=self._playback_worker, daemon=True
        )
        self.playback_thread.start()
        register_active_streaming_player(self)

    def wait_for_completion(self) -> None:
        """Block until the playback thread exits or the timeout elapses."""
        if not self.playback_thread:
            return
        deadline = time.monotonic() + float(PLAYBACK_JOIN_TIMEOUT)
        while self.playback_thread.is_alive() and time.monotonic() < deadline:
            self.playback_thread.join(timeout=0.25)

    def wait_until_released(self, timeout: Optional[float] = None) -> bool:
        """Block until the player no longer needs the chunk files, so they can be deleted.

        Waits for the playback thread, then for a player process that was
        launched and left running (VLC / mplayer / ffplay fallbacks). Returns
        False on *timeout*, or straight away when a GUI player outlives
        playback without telling us it is done (it may still open queued files).
        """
        deadline = None if timeout is None else time.monotonic() + timeout

        def remaining() -> Optional[float]:
            return None if deadline is None else max(0.0, deadline - time.monotonic())

        thread = self.playback_thread
        while thread is not None and thread.is_alive():
            left = remaining()
            if left == 0.0:
                return False
            thread.join(timeout=0.25 if left is None else min(0.25, left))
        if self._released:
            return True
        proc = self.process
        if proc is None or proc.poll() is not None:
            return True
        if self.show_gui:
            return False
        try:
            proc.wait(timeout=remaining())
            return True
        except subprocess.TimeoutExpired:
            return False

    def stop(self) -> None:
        """Stop playback now: drop queued chunks and terminate the player."""
        self.is_playing = False
        self._stopped = True
        with self._order_lock:
            self._pending.clear()
            self._skipped.clear()
        try:
            while True:
                self.chunk_queue.get_nowait()
        except Empty:
            pass
        self.chunk_queue.put(None)  # unblock the worker
        ipc = self._ipc
        if ipc is not None:
            ipc.close()
        else:
            _terminate_process_quietly(self.process)

    def pause(self) -> bool:
        """Pause playback; False when the active player can't be controlled."""
        return self._ipc_call("pause")

    def resume(self) -> bool:
        """Resume paused playback; False when the active player can't be controlled."""
        return self._ipc_call("resume")

    def skip_current(self) -> bool:
        """Skip to the next queued chunk; False when the active player can't be controlled."""
        return self._ipc_call("skip")

    def change_speed(self, delta: float) -> Optional[float]:
        """Nudge playback speed by *delta*, clamped to MIN_SPEED..MAX_SPEED.

        Returns the new speed, or None when the active player can't be controlled.
        """
        speed = round(min(max(self._speed + delta, MIN_SPEED), MAX_SPEED), 2)
        if not self._ipc_call("set_speed", speed):
            return None
        self._speed = speed
        return speed

    @property
    def controllable(self) -> bool:
        """True when pause / resume / skip_current are supported right now."""
        return self._ipc is not None and not self._stopped

    def _ipc_call(self, method: str, *args: Any) -> bool:
        ipc = self._ipc
        if ipc is None or self._stopped:
            return False
        try:
            getattr(ipc, method)(*args)
            return True
        except MpvIpcError:
            return False

    # ── Internal worker ───────────────────────────────────────────────────────

    def _playback_worker(self) -> None:
        try:
            if sys.platform.startswith("win"):
                self._playback_worker_windows()
            else:
                self._playback_worker_unix()
        except Exception as e:
            print(f"⚠️  Playback error: {e}")
        finally:
            unregister_active_streaming_player(self)

    # ── mpv stdin-playlist (Windows + Unix) ───────────────────────────────────

    def _play_mpv_stdin_playlist(
        self, player: str, first_chunk: Optional[str] = None
    ) -> None:
        """True streaming via ``mpv --playlist=-``.

        mpv reads one absolute file path per line from stdin and starts
        playing immediately, with gapless transitions between tracks.
        Feed each chunk as it arrives; close stdin when generation is done.

        *first_chunk* is the path already popped from the queue (Windows
        worker pops before dispatching).  Pass ``None`` when the queue
        hasn't been pre-popped (Unix mpv path).
        """
        if self.show_gui:
            cmd = [
                player,
                "--force-window",       # show OSC even for audio: seek bar, pause, skip
                "--keep-open=yes",      # pause at end instead of closing — user can replay
                "--gapless-audio=yes",
                "--playlist=-",
            ]
        else:
            cmd = [
                player,
                "--no-video",
                "--really-quiet",
                "--gapless-audio=yes",
                "--load-scripts=no",    # see MpvIpc.argv
                "--playlist=-",
            ]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # own process group: see kill_process_group
            )
        except OSError as e:
            print(f"⚠️  mpv --playlist=- failed to start: {e}")
            return

        print("[mpv] streaming (gapless) -- chunks fed as they arrive")
        try:
            if first_chunk is not None:
                self.process.stdin.write(
                    (os.path.abspath(first_chunk) + "\n").encode("utf-8", errors="replace")
                )
                self.process.stdin.flush()
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                self.process.stdin.write(
                    (os.path.abspath(chunk) + "\n").encode("utf-8", errors="replace")
                )
                self.process.stdin.flush()
            self.process.stdin.close()
            # GUI mode: --keep-open means mpv never exits on its own.
            # Don't block — let the user close the window whenever they like.
            if not self.show_gui:
                self.process.wait()
        except (OSError, BrokenPipeError) as e:
            print(f"⚠️  mpv streaming error: {e}")
            _terminate_process_quietly(self.process)

    def _vlc_rc_cmd(
        self,
        sock: socket.socket,
        command: str,
        *,
        read_timeout: float = _RC_CMD_READ_TIMEOUT,
    ) -> str:
        sock.sendall((command.rstrip() + "\n").encode("ascii", errors="replace"))
        sock.settimeout(read_timeout)
        buf = b""
        try:
            while True:
                try:
                    chunk = sock.recv(16384)
                    if not chunk:
                        break
                    buf += chunk
                except socket.timeout:
                    break
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass
        return buf.decode("utf-8", errors="replace")

    def _vlc_rc_status_lane(self, sock: socket.socket) -> str:
        out = self._vlc_rc_cmd(sock, "status", read_timeout=_RC_IS_PLAYING_READ_TIMEOUT).lower()
        if "state paused" in out or "( paused )" in out:
            return "paused"
        if "state playing" in out or "( playing )" in out:
            return "playing"
        if "state stopped" in out or "( stop" in out:
            return "stopped"
        return "unknown"

    def _vlc_rc_is_playing(self, sock: socket.socket) -> bool:
        out = self._vlc_rc_cmd(sock, "is_playing", read_timeout=_RC_IS_PLAYING_READ_TIMEOUT)
        for ln in reversed([x.strip() for x in out.splitlines() if x.strip()]):
            if ln in ("0", "1"):
                return ln == "1"
        m = re.search(r"(^|\D)(0|1)(\D|$)", out.strip())
        if m:
            return m.group(2) == "1"
        return True

    def _vlc_rc_wait_until_finished(
        self, sock: socket.socket, proc: subprocess.Popen
    ) -> None:
        """After every chunk is enqueued, wait until playback ends (honour pause)."""
        deadline = time.monotonic() + float(PLAYBACK_JOIN_TIMEOUT)
        stable_stopped = 0
        tick = 0.08
        need_stopped = max(12, int(1.6 / tick))

        while proc.poll() is None and self.is_playing and time.monotonic() < deadline:
            lane = self._vlc_rc_status_lane(sock)
            if lane == "paused":
                stable_stopped = 0
                time.sleep(tick)
                continue
            if lane == "playing":
                stable_stopped = 0
                time.sleep(tick)
                continue
            if lane == "stopped":
                stable_stopped += 1
                if stable_stopped >= need_stopped:
                    return
                time.sleep(tick)
                continue
            if self._vlc_rc_is_playing(sock):
                stable_stopped = 0
            else:
                stable_stopped += 1
                if stable_stopped >= need_stopped:
                    return
            time.sleep(tick)

    def _vlc_windows_try_rc_session(self, player: str, first_chunk: str) -> bool:
        """One VLC window: TCP oldrc ``add`` / ``enqueue`` while chunks arrive."""
        if not _vlc_use_rc():
            return False

        port = _pick_local_rc_port()
        intf = "qt" if self.show_gui else "dummy"
        cmd = [
            player,
            "--intf",
            intf,
            "--extraintf",
            "oldrc",
            "--rc-host",
            f"127.0.0.1:{port}",
            "--rc-quiet",
        ]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.process = None
            return False

        sock = _connect_vlc_rc(port)
        if sock is None:
            print("⚠️  VLC remote control unavailable — falling back to per-chunk windows")
            _terminate_process_quietly(self.process)
            self.process = None
            return False

        try:
            mode = "GUI" if self.show_gui else "headless"
            print(f"[VLC] ({mode}) -- one window, playlist fills as chunks are ready")
            self._vlc_rc_cmd(sock, f"add {_filepath_to_mrl(first_chunk)}")
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                self._vlc_rc_cmd(sock, f"enqueue {_filepath_to_mrl(chunk)}")

            self._vlc_rc_wait_until_finished(sock, self.process)
            try:
                self._vlc_rc_cmd(sock, "quit", read_timeout=0.25)
            except OSError:
                pass
            if self.process.poll() is None:
                self.process.wait(timeout=30)
        except Exception as e:
            print(f"⚠️  VLC RC playback error: {e}")
            _terminate_process_quietly(self.process)
            self.process = None
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass

        return True

    def _vlc_windows_play_one_subprocess(self, player: str, chunk: str, chunk_index: int) -> None:
        if self.show_gui:
            vlc_cmd = [player, "--play-and-exit", chunk]
        else:
            vlc_cmd = [player, "--intf", "dummy", "--play-and-exit", chunk]
        print(f"[play] chunk {chunk_index}...")
        self.process = subprocess.Popen(
            vlc_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.process.wait()

    def _playback_worker_windows(self) -> None:
        """Windows streaming: mpv stdin-playlist > VLC TCP oldrc > per-chunk fallback.

        mpv's ``--playlist=-`` is tried first when mpv is on PATH — it is
        simpler and more reliable than the VLC RC interface.  VLC RC is kept
        as a fallback for machines where only VLC is installed.
        """
        # Prefer mpv: stdin playlist avoids VLC's TCP RC complexity entirely.
        mpv = PlayerDetector.find(preferred="mpv")
        if mpv and "mpv" in mpv.lower():
            first = self.chunk_queue.get()
            if first is None:
                return
            self._play_mpv_stdin_playlist(mpv, first_chunk=first)
            return

        player = PlayerDetector.find()
        use_vlc = bool(player and "vlc" in player.lower())

        first = self.chunk_queue.get()
        if first is None:
            return

        if use_vlc and self._vlc_windows_try_rc_session(player, first):
            return

        chunk_index = 0
        chunk: Optional[str] = first
        while chunk is not None:
            chunk_index += 1
            try:
                if use_vlc:
                    self._vlc_windows_play_one_subprocess(player, chunk, chunk_index)
                else:
                    os.startfile(os.path.abspath(chunk))
                    print(f"[play] chunk {chunk_index}...")
            except Exception as e:
                print(f"⚠️  Could not play chunk {chunk_index}: {e}")
            nxt = self.chunk_queue.get()
            if nxt is None or self._stopped:
                break
            chunk = nxt

    def _playback_worker_unix(self) -> None:
        """Multi-player Unix streaming playback."""
        player = PlayerDetector.find(preferred=self.preferred)

        if not player:
            self._unix_fallback()
            return

        if "vlc" in player:
            self._play_vlc_unix(player)
        elif "mpv" in player:
            # GUI mpv bridges gaps itself via --keep-open and has its own controls.
            use_ipc = not self.show_gui and ipc_supported()
            if not (use_ipc and self._play_mpv_ipc(player)):
                self._play_mpv_stdin_playlist(player)
        elif "ffplay" in player:
            self._play_ffplay(player)
        elif "mplayer" in player:
            self._play_mplayer(player)
        else:
            self._unix_fallback()

    def _play_mpv_ipc(self, player: str) -> bool:
        """Stream through one idle headless mpv driven over JSON IPC.

        mpv is started before the first chunk is ready, so its start-up
        overlaps synthesis. Returns False (nothing consumed from the queue)
        when mpv can't be reached, so the caller can fall back.
        """
        ipc = MpvIpc(player, on_error=self._on_mpv_entry_error)
        try:
            ipc.start()
        except MpvIpcError as exc:
            print(f"⚠️  mpv IPC unavailable ({exc}); using stdin playlist", file=sys.stderr)
            return False
        self._ipc = ipc
        self.process = ipc.process
        if self._stopped:
            ipc.close()
            return True

        print("[mpv] streaming (gapless, IPC) -- chunks fed as they arrive")
        done = False
        try:
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None or self._stopped:
                    break
                ipc.append(chunk)
            if not self._stopped:
                done = ipc.wait_done(should_continue=lambda: self.is_playing)
        except MpvIpcError as exc:
            if not self._stopped:
                if self.playback_error is None:
                    self.playback_error = str(exc)
                print(f"⚠️  mpv streaming error: {exc}", file=sys.stderr)
        finally:
            self._released = done
            ipc.close()
        return True

    def _on_mpv_entry_error(self, event: Dict) -> None:
        reason = event.get("file_error", "error")
        if self.playback_error is None:
            self.playback_error = str(reason)
        print(f"⚠️  mpv could not play chunk (playlist entry "
              f"{event.get('playlist_entry_id')}): {reason}",
              file=sys.stderr)

    def _unix_fallback(self) -> None:
        """Drain queue, play only the first chunk with the system default."""
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if not chunks:
            return
        default = "afplay" if sys.platform == "darwin" else "mpg123"
        path = os.path.abspath(chunks[0])
        try:
            self.process = subprocess.Popen(
                [default, path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                start_new_session=True,
            )
        except (OSError, ValueError):
            pass

    def _play_vlc_unix(self, player: str) -> None:
        """VLC: wait for all chunks, then play them as one playlist (argv order)."""
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if not chunks:
            return
        cmd = [player] if self.show_gui else [player, "--intf", "dummy"]
        cmd += ["--play-and-exit"] + [os.path.abspath(c) for c in chunks]
        label = "VLC GUI" if self.show_gui else "VLC"
        print(f"[{label}] playing {len(chunks)} chunk(s)")
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"⚠️  VLC playback error: {e}")

    def _play_ffplay(self, player: str) -> None:
        """ffplay: one subprocess per chunk (ffplay doesn't support stdin playlists)."""
        chunk_idx = 0
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None or self._stopped:
                break
            chunk_idx += 1
            if chunk_idx == 1:
                print("[ffplay] streaming...")
            try:
                self.process = subprocess.Popen(
                    [player, "-nodisp", "-autoexit", "-loglevel", "quiet", chunk],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.process.wait()
            except OSError as e:
                print(f"⚠️  ffplay error on chunk {chunk_idx}: {e}")

    def _play_mplayer(self, player: str) -> None:
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if chunks:
            try:
                print(f"[mplayer] {len(chunks)} chunks")
                self.process = subprocess.Popen(
                    [player, "-really-quiet", "-noconsolecontrols"] + chunks,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"⚠️  mplayer playback error: {e}")
