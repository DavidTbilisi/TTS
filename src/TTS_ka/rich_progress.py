"""Rich progress display with statistics, ETA, and animations."""

import sys
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


@dataclass
class ProgressStats:
    """Progress statistics for TTS generation."""
    total_chunks: int
    completed_chunks: int = 0
    total_words: int = 0
    processed_words: int = 0
    start_time: float = 0
    current_chunk_start: float = 0
    chunks_per_second: float = 0
    words_per_second: float = 0
    estimated_total_time: float = 0
    time_remaining: float = 0


class RichProgressDisplay:
    """Rich progress display with animations and statistics."""
    
    def __init__(self, total_chunks: int, total_words: int = 0, language: str = "en"):
        self.stats = ProgressStats(
            total_chunks=total_chunks,
            total_words=total_words,
            start_time=time.perf_counter()
        )
        self.language = language
        self.use_tqdm = HAS_TQDM
        self.pbar: Optional[Any] = None
        self._init_progress_bar()
    
    def _init_progress_bar(self):
        """Initialize the appropriate progress bar."""
        if self.use_tqdm:
            # Rich tqdm progress bar with custom format
            lang_flag = {"ka": "🇬🇪", "ru": "🇷🇺", "en": "🇬🇧"}.get(self.language, "🔊")
            desc = f"{lang_flag} TTS Generation"
            
            self.pbar = tqdm(
                total=self.stats.total_chunks,
                desc=desc,
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}',
                dynamic_ncols=True,
                smoothing=0.1
            )
        else:
            # Fallback to custom progress display
            print(f"🚀 Starting TTS generation: {self.stats.total_chunks} chunks")
    
    def update(self, chunk_words: int = 0):
        """Update progress with current chunk completion."""
        now = time.perf_counter()
        
        # Update stats
        self.stats.completed_chunks += 1
        self.stats.processed_words += chunk_words
        
        elapsed = now - self.stats.start_time
        
        if elapsed > 0:
            self.stats.chunks_per_second = self.stats.completed_chunks / elapsed
            if self.stats.total_words > 0:
                self.stats.words_per_second = self.stats.processed_words / elapsed
        
        # Calculate ETA
        if self.stats.chunks_per_second > 0:
            remaining_chunks = self.stats.total_chunks - self.stats.completed_chunks
            self.stats.time_remaining = remaining_chunks / self.stats.chunks_per_second
            self.stats.estimated_total_time = self.stats.total_chunks / self.stats.chunks_per_second
        
        if self.use_tqdm and self.pbar:
            # Update tqdm with rich statistics
            postfix = self._get_postfix_stats()
            self.pbar.set_postfix_str(postfix)
            self.pbar.update(1)
        else:
            # Custom progress display
            self._print_custom_progress()
    
    def _get_postfix_stats(self) -> str:
        """Generate rich statistics for tqdm postfix."""
        stats_parts = []
        
        if self.stats.chunks_per_second > 0:
            stats_parts.append(f"⚡{self.stats.chunks_per_second:.1f}ch/s")
        
        if self.stats.words_per_second > 0:
            stats_parts.append(f"📝{self.stats.words_per_second:.0f}w/s")
        
        if self.stats.time_remaining > 0:
            if self.stats.time_remaining < 60:
                eta = f"{self.stats.time_remaining:.0f}s"
            else:
                eta = f"{self.stats.time_remaining/60:.1f}m"
            stats_parts.append(f"⏱️{eta}")
        
        return " ".join(stats_parts)
    
    def _print_custom_progress(self):
        """Print custom progress without tqdm."""
        percent = (self.stats.completed_chunks / self.stats.total_chunks) * 100
        
        # Progress bar
        bar_width = 30
        filled = int(bar_width * self.stats.completed_chunks / self.stats.total_chunks)
        bar = "█" * filled + "▒" * (bar_width - filled)
        
        # Statistics
        stats = self._get_postfix_stats()
        
        # Language flag
        lang_flag = {"ka": "🇬🇪", "ru": "🇷🇺", "en": "🇬🇧"}.get(self.language, "🔊")
        
        progress_line = (
            f"\r{lang_flag} [{bar}] {percent:5.1f}% "
            f"({self.stats.completed_chunks}/{self.stats.total_chunks}) {stats}"
        )
        
        print(progress_line, end="", flush=True)
    
    def finish(self, success: bool = True):
        """Complete the progress display."""
        total_time = time.perf_counter() - self.stats.start_time
        
        if self.use_tqdm and self.pbar:
            if success:
                final_stats = f"✅ {total_time:.2f}s total"
                self.pbar.set_postfix_str(final_stats)
            else:
                self.pbar.set_postfix_str("❌ Failed")
            self.pbar.close()
        else:
            if success:
                print(f"\n✅ Completed in {total_time:.2f}s")
            else:
                print(f"\n❌ Generation failed")
        
        # Final statistics summary
        if success and self.stats.total_words > 0:
            avg_wps = self.stats.total_words / total_time if total_time > 0 else 0
            print(f"📊 Performance: {avg_wps:.0f} words/sec, {self.stats.chunks_per_second:.1f} chunks/sec")


def create_progress_display(chunks: list, language: str = "en") -> RichProgressDisplay:
    """Create a progress display for the given chunks and language."""
    total_words = sum(len(chunk.split()) for chunk in chunks)
    return RichProgressDisplay(len(chunks), total_words, language)


# Animation frames for loading states
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
PULSE_FRAMES = ["🔊", "🔉", "🔈", "🔇", "🔈", "🔉"]


def animate_loading(message: str = "Processing", duration: float = 1.0):
    """Show animated loading indicator."""
    start_time = time.perf_counter()
    frame_index = 0
    
    while time.perf_counter() - start_time < duration:
        frame = SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]
        print(f"\r{frame} {message}...", end="", flush=True)
        frame_index += 1
        time.sleep(0.1)
    
    print(f"\r✅ {message} complete!" + " " * 10)