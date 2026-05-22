"""Progress display using the rich library, with tqdm and plain-text fallbacks."""

import sys
import time
from dataclasses import dataclass
from typing import Optional, Any

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    tqdm = None  # type: ignore[assignment,misc]
    HAS_TQDM = False

LANG_FLAG: dict[str, str] = {"ka": "🇬🇪", "ka-m": "🇬🇪", "ru": "🇷🇺", "en": "🇬🇧"}

# Shared console — always writes to stderr so JSON stdout stays clean.
console: Any = Console(stderr=True) if HAS_RICH else None


@dataclass
class ProgressStats:
    """Runtime statistics tracked during generation."""
    total_chunks: int
    completed_chunks: int = 0
    total_words: int = 0
    processed_words: int = 0
    start_time: float = 0.0
    chunks_per_second: float = 0.0
    words_per_second: float = 0.0
    time_remaining: float = 0.0


class RichProgressDisplay:
    """Progress display with rich animations, tqdm fallback, or plain text."""

    def __init__(self, total_chunks: int, total_words: int = 0, language: str = "en"):
        self.stats = ProgressStats(
            total_chunks=total_chunks,
            total_words=total_words,
            start_time=time.perf_counter(),
        )
        self.language = language
        self._progress: Optional[Any] = None
        self._task_id: Optional[Any] = None
        self._pbar: Optional[Any] = None
        self._init()

    def _init(self) -> None:
        flag = LANG_FLAG.get(self.language, "🔊")
        if HAS_RICH:
            self._progress = Progress(
                SpinnerColumn(style="cyan"),
                TextColumn(f"{flag} [bold cyan]Generating[/bold cyan]"),
                BarColumn(
                    bar_width=None,
                    style="dim cyan",
                    complete_style="bold cyan",
                    finished_style="bold green",
                ),
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                TextColumn("[yellow]{task.fields[rate]}[/yellow]"),
                console=console,
                transient=True,
                expand=True,
            )
            self._progress.start()
            self._task_id = self._progress.add_task(
                "Generating",
                total=self.stats.total_chunks,
                rate="",
            )
        elif HAS_TQDM:
            self._pbar = tqdm(
                total=self.stats.total_chunks,
                desc=f"{flag} TTS",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}",
                dynamic_ncols=True,
                smoothing=0.1,
                file=sys.stderr,
            )
        else:
            print(f"  {flag}  Starting TTS: {self.stats.total_chunks} chunks", file=sys.stderr)

    def update(self, chunk_words: int = 0) -> None:
        now = time.perf_counter()
        self.stats.completed_chunks += 1
        self.stats.processed_words += chunk_words
        elapsed = now - self.stats.start_time
        if elapsed > 0:
            self.stats.chunks_per_second = self.stats.completed_chunks / elapsed
            if self.stats.total_words > 0:
                self.stats.words_per_second = self.stats.processed_words / elapsed
        if self.stats.chunks_per_second > 0:
            remaining = self.stats.total_chunks - self.stats.completed_chunks
            self.stats.time_remaining = remaining / self.stats.chunks_per_second

        if HAS_RICH and self._progress is not None and self._task_id is not None:
            rate = f"⚡{self.stats.chunks_per_second:.1f} ch/s"
            if self.stats.words_per_second > 0:
                rate += f"  📝{self.stats.words_per_second:.0f} w/s"
            self._progress.update(self._task_id, advance=1, rate=rate)
        elif self._pbar is not None:
            parts = [f"⚡{self.stats.chunks_per_second:.1f}ch/s"]
            if self.stats.words_per_second > 0:
                parts.append(f"📝{self.stats.words_per_second:.0f}w/s")
            self._pbar.set_postfix_str(" ".join(parts))
            self._pbar.update(1)
        else:
            self._print_fallback()

    def _print_fallback(self) -> None:
        pct = self.stats.completed_chunks / self.stats.total_chunks * 100
        filled = int(30 * self.stats.completed_chunks / self.stats.total_chunks)
        bar = "█" * filled + "▒" * (30 - filled)
        flag = LANG_FLAG.get(self.language, "🔊")
        print(
            f"\r  {flag} [{bar}] {pct:5.1f}%"
            f" ({self.stats.completed_chunks}/{self.stats.total_chunks})",
            end="",
            flush=True,
            file=sys.stderr,
        )

    def finish(self, success: bool = True) -> None:
        total_time = time.perf_counter() - self.stats.start_time
        avg_wps = self.stats.total_words / total_time if total_time > 0 else 0

        if HAS_RICH and self._progress is not None:
            self._progress.stop()
            if success:
                parts = [f"[bold green]✓[/bold green]  [bold]Completed in {total_time:.2f}s[/bold]"]
                if avg_wps > 0:
                    parts.append(f"[yellow]{avg_wps:.0f} w/s[/yellow]")
                if self.stats.chunks_per_second > 0:
                    parts.append(f"[dim]{self.stats.chunks_per_second:.1f} ch/s[/dim]")
                console.print("  " + "  [dim]·[/dim]  ".join(parts))
            else:
                console.print("  [bold red]✗[/bold red]  Generation failed")
        elif self._pbar is not None:
            self._pbar.set_postfix_str(f"{'✅' if success else '❌'} {total_time:.2f}s")
            self._pbar.close()
            if success and avg_wps > 0:
                print(
                    f"  📊 {avg_wps:.0f} w/s  ·  {self.stats.chunks_per_second:.1f} ch/s",
                    file=sys.stderr,
                )
        else:
            if success:
                print(f"\n  ✅  Completed in {total_time:.2f}s", file=sys.stderr)
            else:
                print(f"\n  ❌  Generation failed", file=sys.stderr)


def create_progress_display(chunks: list, language: str = "en") -> RichProgressDisplay:
    """Create a progress display for the given chunks and language."""
    total_words = sum(len(c.split()) for c in chunks)
    return RichProgressDisplay(len(chunks), total_words, language)
