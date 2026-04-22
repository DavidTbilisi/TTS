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
   playback order when generation finishes out-of-order).
3. Call ``finish_generation()`` when all chunks are queued.
4. Call ``wait_for_completion()`` to block until the player thread exits.
"""

from __future__ import annotations

import os
import re
import sys
import asyncio
import socket
import subprocess
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Dict, List, Optional

from .constants import PLAYBACK_JOIN_TIMEOUT

# VLC legacy RC over TCP (stdin RC is unreliable on Windows — see VideoLAN issues).
_RC_CONNECT_ATTEMPTS = 50
_RC_CONNECT_DELAY_SEC = 0.08
_RC_CMD_READ_TIMEOUT = 0.35
_RC_IS_PLAYING_READ_TIMEOUT = 1.25
_RC_IDLE_STABLE_SEC = 1.6


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
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


# Last started ``StreamingAudioPlayer`` (streaming mode) — stopped on Ctrl+C.
_active_streaming_player: Optional["StreamingAudioPlayer"] = None


def register_active_streaming_player(player: Optional["StreamingAudioPlayer"]) -> None:
    global _active_streaming_player
    _active_streaming_player = player


def unregister_active_streaming_player(player: "StreamingAudioPlayer") -> None:
    global _active_streaming_player
    if _active_streaming_player is player:
        _active_streaming_player = None


def stop_active_streaming_player() -> None:
    """Terminate VLC / playback for the active streaming session (e.g. Ctrl+C)."""
    p = _active_streaming_player
    if p is not None:
        p.stop()


# ── Player detection ──────────────────────────────────────────────────────────

class PlayerDetector:
    """Finds a suitable streaming audio player on the current platform.

    Preference order: vlc → mpv → ffplay → mplayer.
    On Windows, common VLC installation paths are checked when ``vlc`` is not
    on ``PATH``.
    """

    _CANDIDATES: List[str] = ["vlc", "mpv", "ffplay", "mplayer"]
    _WIN_VLC_PATHS: List[str] = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]

    @classmethod
    def find(cls) -> Optional[str]:
        """Return the executable path/name of the first available player."""
        for player in cls._CANDIDATES:
            path = cls._locate(player)
            if path:
                return path
        return None

    @classmethod
    def _locate(cls, player: str) -> Optional[str]:
        if sys.platform.startswith("win"):
            return cls._locate_windows(player)
        return cls._locate_unix(player)

    @classmethod
    def _locate_windows(cls, player: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["where", player], capture_output=True, timeout=1
            )
            if result.returncode == 0:
                return player
        except (OSError, subprocess.TimeoutExpired):
            pass
        if player == "vlc":
            for path in cls._WIN_VLC_PATHS:
                if os.path.exists(path):
                    return path
        return None

    @classmethod
    def _locate_unix(cls, player: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["which", player], capture_output=True, timeout=1
            )
            if result.returncode == 0:
                return player
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None


# ── Streaming player ──────────────────────────────────────────────────────────

class StreamingAudioPlayer:
    """Plays audio chunks as they become available during generation."""

    def __init__(self, show_gui: bool = True) -> None:
        self.chunk_queue: Queue = Queue()
        self.playback_thread: Optional[threading.Thread] = None
        self.is_playing = False
        self.finished_generating = False
        self.process: Optional[subprocess.Popen] = None
        self.show_gui = show_gui
        self._pending: Dict[int, str] = {}
        self._next_play_index: int = 0
        self._order_lock = threading.Lock()

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
        if not chunk_path or not os.path.exists(chunk_path) or os.path.getsize(chunk_path) <= 0:
            return
        idx = chunk_index if chunk_index is not None else self._infer_chunk_index(chunk_path)
        if idx is None:
            self.chunk_queue.put(chunk_path)
            return
        with self._order_lock:
            self._pending[idx] = chunk_path
            while self._next_play_index in self._pending:
                self.chunk_queue.put(self._pending.pop(self._next_play_index))
                self._next_play_index += 1

    def finish_generation(self) -> None:
        """Signal that no more chunks will be added."""
        if self.finished_generating:
            return
        self.finished_generating = True
        with self._order_lock:
            while self._next_play_index in self._pending:
                self.chunk_queue.put(self._pending.pop(self._next_play_index))
                self._next_play_index += 1
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

    def stop(self) -> None:
        """Terminate the current player process."""
        self.is_playing = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except OSError:
                pass

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
            print(f"🔊 VLC ({mode}) — one window, playlist fills as chunks are ready")
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
        print(f"🔊 Playing chunk {chunk_index}...")
        self.process = subprocess.Popen(
            vlc_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.process.wait()

    def _playback_worker_windows(self) -> None:
        """Windows: prefer one VLC + TCP oldrc; else per-chunk VLC or os.startfile."""
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
                    print(f"🔊 Playing chunk {chunk_index}...")
            except Exception as e:
                print(f"⚠️  Could not play chunk {chunk_index}: {e}")
            nxt = self.chunk_queue.get()
            if nxt is None:
                break
            chunk = nxt

    def _playback_worker_unix(self) -> None:
        """Multi-player Unix streaming playback."""
        player = PlayerDetector.find()

        if not player:
            self._unix_fallback()
            return

        if "vlc" in player:
            self._play_vlc_unix(player)
        elif "mpv" in player:
            self._play_mpv(player)
        elif "ffplay" in player:
            self._play_ffplay(player)
        elif "mplayer" in player:
            self._play_mplayer(player)
        else:
            self._unix_fallback()

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
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            pass

    def _play_vlc_unix(self, player: str) -> None:
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if not chunks:
            return
        try:
            first_cmd = (
                [player, "--play-and-exit", chunks[0]]
                if self.show_gui
                else [player, "--intf", "dummy", "--play-and-exit", chunks[0]]
            )
            label = "VLC GUI" if self.show_gui else "VLC"
            print(f"🔊 Starting {label} playback...")
            self.process = subprocess.Popen(
                first_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if len(chunks) > 1:
                playlist = self._create_vlc_playlist(chunks)
                if playlist:
                    time.sleep(1)
                    full_cmd = (
                        [player, "--play-and-exit", playlist]
                        if self.show_gui
                        else [player, "--intf", "dummy", "--play-and-exit", playlist]
                    )
                    print(f"🎵 {label} playlist with {len(chunks)} chunks")
                    self.process = subprocess.Popen(
                        full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
        except Exception as e:
            print(f"⚠️  VLC playback error: {e}")

    def _play_mpv(self, player: str) -> None:
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if chunks:
            try:
                print(f"🔊 Starting mpv with {len(chunks)} chunks")
                self.process = subprocess.Popen(
                    [player, "--no-video", "--really-quiet"] + chunks,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"⚠️  mpv playback error: {e}")

    def _play_ffplay(self, player: str) -> None:
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if chunks:
            try:
                self.process = subprocess.Popen(
                    [player, "-nodisp", "-autoexit", "-loglevel", "quiet"] + chunks,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                print(f"⚠️  Could not start ffplay: {e}")

    def _play_mplayer(self, player: str) -> None:
        chunks: List[str] = []
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunks.append(chunk)
        if chunks:
            try:
                print(f"🔊 Starting mplayer with {len(chunks)} chunks")
                self.process = subprocess.Popen(
                    [player, "-really-quiet", "-noconsolecontrols"] + chunks,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print(f"⚠️  mplayer playback error: {e}")

    def _create_vlc_playlist(self, chunks: List[str]) -> Optional[str]:
        """Write an M3U playlist file for seamless VLC playback."""
        playlist_path = ".streaming_playlist.m3u"
        try:
            with open(playlist_path, "w", encoding="utf-8") as f:
                f.write("#EXTM3U\n")
                for i, chunk in enumerate(chunks):
                    if os.path.exists(chunk):
                        f.write(f"#EXTINF:-1,Chunk {i + 1}\n")
                        f.write(f"{os.path.abspath(chunk)}\n")
            return playlist_path
        except Exception as e:
            print(f"⚠️  Could not create playlist: {e}")
            return None


# ── Legacy helper (kept for backward compatibility) ───────────────────────────

async def play_audio_streaming(
    chunks: List[str],
    merge_first: bool = True,
    show_gui: bool = True,
) -> StreamingAudioPlayer:
    """Play audio chunks with optional streaming.

    Returns a ``StreamingAudioPlayer`` instance.  When *merge_first* is
    ``True`` (or on Windows) the player is returned without starting — the
    caller is responsible for merging and playing separately.
    """
    player = StreamingAudioPlayer(show_gui=show_gui)
    if merge_first or sys.platform.startswith("win"):
        return player

    player.start()
    for i, chunk in enumerate(chunks):
        if os.path.exists(chunk):
            player.add_chunk(chunk, i)
            await asyncio.sleep(0.01)
    player.finish_generation()
    return player
