"""Progress display and styled stderr output using the rich library."""

import time
from dataclasses import dataclass

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

LANG_FLAG: dict[str, str] = {"ka": "🇬🇪", "ka-m": "🇬🇪", "ru": "🇷🇺", "en": "🇬🇧", "en-US": "🇺🇸"}

# Shared console — always writes to stderr so JSON stdout stays clean.
console = Console(stderr=True)


def cprint(msg: str) -> None:
    """Print a rich-markup message to stderr."""
    console.print(msg)


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


class RichProgressDisplay:
    """Animated rich progress bar for chunked generation."""

    def __init__(self, total_chunks: int, total_words: int = 0, language: str = "en"):
        self.stats = ProgressStats(
            total_chunks=total_chunks,
            total_words=total_words,
            start_time=time.perf_counter(),
        )
        self.language = language
        flag = LANG_FLAG.get(language, "🔊")
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

    def update(self, chunk_words: int = 0) -> None:
        now = time.perf_counter()
        self.stats.completed_chunks += 1
        self.stats.processed_words += chunk_words
        elapsed = now - self.stats.start_time
        if elapsed > 0:
            self.stats.chunks_per_second = self.stats.completed_chunks / elapsed
            if self.stats.total_words > 0:
                self.stats.words_per_second = self.stats.processed_words / elapsed

        rate = f"⚡{self.stats.chunks_per_second:.1f} ch/s"
        if self.stats.words_per_second > 0:
            rate += f"  📝{self.stats.words_per_second:.0f} w/s"
        self._progress.update(self._task_id, advance=1, rate=rate)

    def finish(self, success: bool = True) -> None:
        total_time = time.perf_counter() - self.stats.start_time
        avg_wps = self.stats.total_words / total_time if total_time > 0 else 0

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


def create_progress_display(chunks: list, language: str = "en") -> RichProgressDisplay:
    """Create a progress display for the given chunks and language."""
    total_words = sum(len(c.split()) for c in chunks)
    return RichProgressDisplay(len(chunks), total_words, language)
