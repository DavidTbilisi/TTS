"""Streaming audio playback — play audio while it is still being generated.

Design
------
``PlayerDetector`` encapsulates all platform-specific player-discovery
logic, keeping ``StreamingAudioPlayer`` focused on queue management and
thread coordination.

``StreamingAudioPlayer`` is the primary public interface:

1. Call ``start()`` before generation begins.
2. Call ``add_chunk(path)`` as each part finishes generating.
3. Call ``finish_generation()`` when all chunks are queued.
4. Call ``wait_for_completion()`` to block until the player thread exits.
"""

from __future__ import annotations

import os
import sys
import asyncio
import subprocess
import threading
import time
from queue import Queue
from typing import List, Optional

from .constants import PLAYBACK_JOIN_TIMEOUT


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

    # ── Public interface ──────────────────────────────────────────────────────

    def add_chunk(self, chunk_path: str) -> None:
        """Enqueue a successfully generated chunk for playback."""
        if chunk_path and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            self.chunk_queue.put(chunk_path)

    def finish_generation(self) -> None:
        """Signal that no more chunks will be added."""
        self.finished_generating = True
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

    def wait_for_completion(self) -> None:
        """Block until the playback thread exits or the timeout elapses."""
        if self.playback_thread:
            self.playback_thread.join(timeout=PLAYBACK_JOIN_TIMEOUT)

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

    def _playback_worker_windows(self) -> None:
        """Sequential per-chunk playback on Windows."""
        player = PlayerDetector.find()
        use_vlc = player and "vlc" in player.lower()
        chunk_index = 0

        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:
                break
            chunk_index += 1
            try:
                if use_vlc:
                    vlc_cmd = (
                        [player, "--play-and-exit", chunk]
                        if self.show_gui and chunk_index == 1
                        else [player, "--intf", "dummy", "--play-and-exit", chunk]
                    )
                    print(f"🔊 Playing chunk {chunk_index}...")
                    self.process = subprocess.Popen(
                        vlc_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    self.process.wait()
                else:
                    os.startfile(os.path.abspath(chunk))
                    print(f"🔊 Playing chunk {chunk_index}...")
            except Exception as e:
                print(f"⚠️  Could not play chunk {chunk_index}: {e}")

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
    for chunk in chunks:
        if os.path.exists(chunk):
            player.add_chunk(chunk)
            await asyncio.sleep(0.01)
    player.finish_generation()
    return player
