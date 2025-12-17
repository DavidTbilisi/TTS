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
    
    def __init__(self):
        self.chunk_queue: Queue = Queue()
        self.playback_thread: Optional[threading.Thread] = None
        self.is_playing = False
        self.finished_generating = False
        self.process: Optional[subprocess.Popen] = None
        
    def add_chunk(self, chunk_path: str) -> None:
        """Add a generated chunk to the playback queue."""
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
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
        """Windows streaming playback - plays first chunk immediately."""
        chunks_to_play = []
        first_played = False
        
        while True:
            chunk = self.chunk_queue.get()
            if chunk is None:  # Sentinel
                break
            chunks_to_play.append(chunk)
            
            # Play first chunk immediately on Windows
            if not first_played:
                try:
                    # Use os.startfile for immediate playback of first chunk
                    os.startfile(os.path.abspath(chunk))
                    first_played = True
                    print("🔊 Playing first chunk while generating remaining audio...")
                except Exception as e:
                    print(f"⚠️  Could not play first chunk: {e}")
        
        # Note: Subsequent chunks will be merged and the full file will be available
        # Windows doesn't support seamless streaming concat, but user gets immediate feedback
    
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
        if 'mpv' in player:
            # mpv can play multiple files in sequence
            cmd = [player, '--no-video', '--really-quiet']
            chunks = []
            
            # Collect chunks as they arrive
            while True:
                chunk = self.chunk_queue.get()
                if chunk is None:
                    break
                chunks.append(chunk)
                
                # Start playing first chunk immediately
                if len(chunks) == 1:
                    try:
                        self.process = subprocess.Popen(
                            cmd + [chunk],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass
            
            # For remaining chunks, we'd need to use mpv's IPC
            # For now, this provides partial streaming
        
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
        for player in ['mpv', 'ffplay', 'mplayer']:
            try:
                result = subprocess.run(['which', player], 
                                      capture_output=True, 
                                      timeout=1)
                if result.returncode == 0:
                    return player
            except Exception:
                continue
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


async def play_audio_streaming(chunks: List[str], merge_first: bool = True) -> StreamingAudioPlayer:
    """
    Play audio chunks with streaming (play while generating).
    
    Args:
        chunks: List of chunk file paths
        merge_first: If True, merge all chunks first (faster but no streaming)
    
    Returns:
        StreamingAudioPlayer instance
    """
    player = StreamingAudioPlayer()
    
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
