"""Streaming audio playback - play audio while it's still generating."""

import os
import sys
import asyncio
import subprocess
from typing import List, Optional
from queue import Queue
import threading


class StreamingAudioPlayer:
    """Plays audio chunks as they become available during generation."""
    
    def __init__(self, show_gui: bool = True):
        self.chunk_queue: Queue = Queue()
        self.playback_thread: Optional[threading.Thread] = None
        self.is_playing = False
        self.finished_generating = False
        self.process: Optional[subprocess.Popen] = None
        self.show_gui = show_gui
        
    def add_chunk(self, chunk_path: str) -> None:
        """Add a generated chunk to the playback queue."""
        if chunk_path and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            self.chunk_queue.put(chunk_path)
    
    def finish_generation(self) -> None:
        """Signal that all chunks have been generated."""
        self.finished_generating = True
        self.chunk_queue.put(None)  # Sentinel value
    
    def _playback_worker(self) -> None:
        """Background thread that plays chunks as they arrive."""
        try:
            if sys.platform.startswith('win'):
                self._playback_worker_windows()
            else:
                self._playback_worker_unix()
        except Exception as e:
            print(f"⚠️  Playback error: {e}")
    
    def _playback_worker_windows(self) -> None:
        """Windows streaming playback - plays first chunk immediately, then waits for merge completion."""
        chunks_to_play = []
        first_played = False
        output_file = None
        
        # Check if VLC is available on Windows
        vlc_player = self._find_streaming_player()
        use_vlc = vlc_player and 'vlc' in vlc_player.lower()
        
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:  # Sentinel
                break
            chunks_to_play.append(chunk)
            
            # Play first chunk immediately on Windows
            if not first_played:
                try:
                    if use_vlc:
                        # Use VLC for better control
                        if self.show_gui:
                            vlc_cmd = [vlc_player, '--play-and-exit', chunk]
                            print("🔊 Playing with VLC GUI while generating remaining chunks...")
                        else:
                            vlc_cmd = [vlc_player, '--intf', 'dummy', '--play-and-exit', chunk]
                            print("🔊 Playing with VLC while generating remaining chunks...")
                        self.process = subprocess.Popen(
                            vlc_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    else:
                        # Fallback to Windows default player
                        os.startfile(os.path.abspath(chunk))
                        print("🔊 Playing audio while generating remaining chunks...")
                    
                    first_played = True
                    output_file = chunk
                except Exception as e:
                    print(f"⚠️  Could not play first chunk: {e}")
        
        # If we have VLC and multiple chunks, create playlist for seamless experience
        if use_vlc and len(chunks_to_play) > 1 and self.finished_generating:
            try:
                playlist = self._create_vlc_playlist(chunks_to_play)
                if playlist:
                    import time
                    time.sleep(0.5)  # Brief pause
                    if self.show_gui:
                        full_cmd = [vlc_player, '--play-and-exit', playlist]
                        print(f"🎵 VLC GUI with {len(chunks_to_play)} chunks")
                    else:
                        full_cmd = [vlc_player, '--intf', 'dummy', '--play-and-exit', playlist]
                        print(f"🎵 VLC playlist with {len(chunks_to_play)} chunks")
                    subprocess.Popen(
                        full_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
            except Exception as e:
                print(f"⚠️  VLC playlist error: {e}")
        
        # For streaming: The first chunk becomes the full output file after merging
        if output_file and self.finished_generating:
            print("✅ Audio generation completed - full audio should be playing")
    
    def _playback_worker_unix(self) -> None:
        """Unix streaming playback using mpv or ffplay."""
        # Try to find a suitable player
        player = self._find_streaming_player()
        
        if not player:
            # Fallback to non-streaming playback
            chunks = []
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
            
            # Play first chunk immediately
            if chunks:
                try:
                    os.system(f"{self._get_default_player()} '{chunks[0]}' &")
                except Exception:
                    pass
            return
        
        # Build streaming command
        if 'vlc' in player:
            # VLC with playlist for seamless chunk streaming
            chunks = []
            
            # Collect all chunks first
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
            
            if chunks:
                # Play first chunk immediately for instant feedback
                try:
                    if self.show_gui:
                        first_cmd = [player, '--play-and-exit', chunks[0]]
                        print("🔊 Starting VLC GUI playback...")
                    else:
                        first_cmd = [player, '--intf', 'dummy', '--play-and-exit', chunks[0]]
                        print("🔊 Starting VLC playback...")
                    self.process = subprocess.Popen(
                        first_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    
                    # If multiple chunks, create playlist for full audio
                    if len(chunks) > 1:
                        playlist = self._create_vlc_playlist(chunks)
                        if playlist:
                            # Wait briefly, then start full playlist
                            import time
                            time.sleep(1)
                            if self.show_gui:
                                full_cmd = [player, '--play-and-exit', playlist]
                                print(f"🎵 VLC GUI playlist with {len(chunks)} chunks")
                            else:
                                full_cmd = [player, '--intf', 'dummy', '--play-and-exit', playlist]
                                print(f"🎵 VLC playlist with {len(chunks)} chunks")
                            subprocess.Popen(
                                full_cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                except Exception as e:
                    print(f"⚠️  VLC playback error: {e}")
        
        elif 'mpv' in player:
            # mpv can play multiple files in sequence
            cmd = [player, '--no-video', '--really-quiet']
            chunks = []
            
            # Collect chunks as they arrive
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
            
            if chunks:
                # mpv can handle multiple files directly for seamless playback
                try:
                    print(f"🔊 Starting mpv with {len(chunks)} chunks")
                    self.process = subprocess.Popen(
                        cmd + chunks,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    print(f"⚠️  mpv playback error: {e}")
        
        elif 'ffplay' in player:
            # Similar approach for ffplay
            chunks = []
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
                
                if len(chunks) == 1:
                    try:
                        self.process = subprocess.Popen(
                            [player, '-nodisp', '-autoexit', '-loglevel', 'quiet', chunk],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass
    
    def _find_streaming_player(self) -> Optional[str]:
        """Find a suitable streaming audio player."""
        players = ['vlc', 'mpv', 'ffplay', 'mplayer']
        
        for player in players:
            try:
                if sys.platform.startswith('win'):
                    # Windows: check both PATH and common install locations
                    if player == 'vlc':
                        common_paths = [
                            "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",
                            "C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe"
                        ]
                    else:
                        common_paths = [f"C:\\Program Files\\{player}\\{player}.exe"]
                    
                    # Check PATH first
                    result = subprocess.run(['where', player], 
                                          capture_output=True, 
                                          timeout=1)
                    if result.returncode == 0:
                        return player
                    
                    # Check common install paths
                    for path in common_paths:
                        if os.path.exists(path):
                            return path
                else:
                    # Unix: use which
                    result = subprocess.run(['which', player], 
                                          capture_output=True, 
                                          timeout=1)
                    if result.returncode == 0:
                        return player
            except Exception:
                continue
        return None
    
    def _create_vlc_playlist(self, chunks: List[str]) -> Optional[str]:
        """Create M3U playlist file for VLC seamless playback."""
        playlist_path = '.streaming_playlist.m3u'
        try:
            with open(playlist_path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for i, chunk in enumerate(chunks):
                    if os.path.exists(chunk):
                        f.write(f'#EXTINF:-1,Chunk {i+1}\n')
                        f.write(f'{os.path.abspath(chunk)}\n')
            return playlist_path
        except Exception as e:
            print(f'⚠️  Could not create playlist: {e}')
            return None
    
    def _get_default_player(self) -> str:
        """Get default player command."""
        if sys.platform == 'darwin':
            return 'afplay'
        return 'mpg123'
    
    def start(self) -> None:
        """Start the streaming playback thread."""
        if self.is_playing:
            return
        
        self.is_playing = True
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()
    
    def wait_for_completion(self) -> None:
        """Wait for playback to complete."""
        if self.playback_thread:
            self.playback_thread.join(timeout=300)  # 5 minute timeout
    
    def stop(self) -> None:
        """Stop playback."""
        self.is_playing = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass


async def play_audio_streaming(chunks: List[str], merge_first: bool = True, show_gui: bool = True) -> StreamingAudioPlayer:
    """
    Play audio chunks with streaming (play while generating).
    
    Args:
        chunks: List of chunk file paths
        merge_first: If True, merge all chunks first (faster but no streaming)
        show_gui: If True, show VLC GUI instead of headless playback
    
    Returns:
        StreamingAudioPlayer instance
    """
    player = StreamingAudioPlayer(show_gui=show_gui)
    
    if merge_first or sys.platform.startswith('win'):
        # Windows or user preference: merge first then play
        # This is more reliable on Windows
        return player
    
    # Unix: can do true streaming
    player.start()
    
    # Add chunks as they're available
    for chunk in chunks:
        if os.path.exists(chunk):
            player.add_chunk(chunk)
            await asyncio.sleep(0.01)  # Small delay to prevent queue overflow
    
    player.finish_generation()
    return player
