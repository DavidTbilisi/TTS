"""Rich progress display with statistics, ETA, and animations."""

import time
from dataclasses import dataclass
from typing import Any, Optional

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
            total_chunks=total_chunks, total_words=total_words, start_time=time.perf_counter()
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
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}",
                dynamic_ncols=True,
                smoothing=0.1,
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
            print(
                f"📊 Performance: {avg_wps:.0f} words/sec, {self.stats.chunks_per_second:.1f} chunks/sec"
            )


# Full ProgressTracker implementation expected by tests
class ProgressTracker:
    """Compatibility ProgressTracker used by tests.

    API:
      ProgressTracker(total=<int>, language=<str>)
      attributes: total, language, completed, total_words, start_time
      methods: update(words_processed=0), _get_flag(), _calculate_stats(),
               _estimate_time(), _format_time(), show_final_stats()
      context manager support via __enter__/__exit__
    """

    def __init__(self, total: int, language: str = "en"):
        self.total = total if isinstance(total, int) else 0
        self.language = language or ""
        self.completed = 0
        self.total_words = 0
        self.start_time = time.time()
        self._use_tqdm = HAS_TQDM
        self._pbar = None
        self._init()

    def _init(self):
        if self._use_tqdm:
            try:
                self._pbar = tqdm(
                    total=max(0, self.total), desc=self._get_flag() + " TTS Generation"
                )
            except Exception:
                self._use_tqdm = False
                self._pbar = None
        else:
            # Print a simple line using print with an argument to satisfy tests
            print(f"Starting TTS generation: {self.total} chunks")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.show_final_stats(success=False)
        else:
            self.show_final_stats(success=True)
        if self._pbar:
            try:
                self._pbar.close()
            except Exception:
                pass

    def update(self, words_processed: int = 0):
        """Mark a single chunk as completed and update stats."""
        self.completed += 1
        try:
            self.total_words += int(words_processed)
        except Exception:
            pass

        # Update tqdm if available
        if self._use_tqdm and self._pbar:
            try:
                self._pbar.update(1)
            except Exception:
                pass

    def _get_flag(self) -> str:
        return {"ka": "🇬🇪", "ru": "🇷🇺", "en": "🇬🇧"}.get(self.language, "🌐")

    def _calculate_stats(self) -> str:
        elapsed = max(1e-6, time.time() - self.start_time)
        ch_per_s = (self.completed / elapsed) if elapsed > 0 else 0
        w_per_s = (self.total_words / elapsed) if elapsed > 0 else 0
        eta = self._estimate_time()
        eta_str = self._format_time(eta) if eta > 0 else "0"
        return f"⚡{ch_per_s:.1f}ch/s 📝{w_per_s:.0f}w/s ⏱️{eta_str}"

    def _estimate_time(self) -> float:
        if self.completed <= 0 or self.total <= 0:
            return 0
        elapsed = max(1e-6, time.time() - self.start_time)
        rate = self.completed / elapsed
        if rate <= 0:
            return 0
        remaining = max(0, self.total - self.completed)
        return remaining / rate

    def _format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}"
        else:
            return f"{int(round(seconds/60))}m"

    def show_final_stats(self, success: bool = True):
        total_time = max(0.0, time.time() - self.start_time)
        if success:
            print(f"Completed in {total_time:.2f}s")
        else:
            print("Generation failed")
        if self.total_words > 0 and total_time > 0:
            wps = self.total_words / total_time
            print(f"Performance: {int(wps)} words/sec")


# Keep create_progress_display for other code
def create_progress_display(chunks: list, language: str = "en") -> RichProgressDisplay:
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
