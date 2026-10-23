"""Ultra-fast parallel processing with optimized concurrency."""

import asyncio
import glob
import os
import shutil
import sys
import tempfile
import threading
import time
from typing import Callable, List, Optional
from concurrent.futures import ThreadPoolExecutor

from .fast_audio import (
    discard_empty_output,
    fast_generate_audio,
    fast_merge_audio_files,
    generation_failed,
)
from .not_reading import replace_not_readable
from .rich_progress import cprint as _cprint, create_progress_display
from .streaming_player import StreamingAudioPlayer, stop_active_streaming_player
from .constants import (
    MAX_PARALLEL_WORKERS,
    STREAMING_FIRST_CHUNK_SECONDS,
)

# Optimal worker count
OPTIMAL_WORKERS = MAX_PARALLEL_WORKERS


# Per-run temp dirs holding the chunk part files.
RUN_DIR_PREFIX = "tts-ka-run-"
# Run dirs older than this are leftovers (crash, GUI streaming) and get swept.
STALE_RUN_DIR_SECONDS = 12 * 3600


class GenerationCancelled(Exception):
    """Raised when the user cancels generation (e.g. GUI Stop)."""


class EmptyInputError(ValueError):
    """Nothing speakable is left after sanitizing the input."""


def _make_run_dir() -> str:
    """Create a private temp dir for one run's part files."""
    return tempfile.mkdtemp(prefix=RUN_DIR_PREFIX)


def _sweep_stale_run_dirs(max_age: float = STALE_RUN_DIR_SECONDS) -> None:
    """Remove run dirs left behind by earlier runs.

    Only dirs older than *max_age* go: a recent one may belong to a run that
    is still generating or playing in another process.
    """
    cutoff = time.time() - max_age
    for path in glob.glob(os.path.join(tempfile.gettempdir(), RUN_DIR_PREFIX + "*")):
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


async def _await_with_cancel(awaitable, cancel_event: Optional[threading.Event]):
    """Await *awaitable* (e.g. ``fast_generate_audio(...)``) unless *cancel_event* is set."""
    if cancel_event is None:
        return await awaitable
    task = asyncio.create_task(awaitable)

    async def _cancel_poll() -> None:
        while not cancel_event.is_set():
            await asyncio.sleep(0.12)
        if not task.done():
            task.cancel()

    poller = asyncio.create_task(_cancel_poll())
    try:
        return await task
    except asyncio.CancelledError:
        if cancel_event.is_set():
            raise GenerationCancelled() from None
        raise
    finally:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass


def _interrupt_streaming_cleanup(
    streaming_player: Optional[StreamingAudioPlayer], work_dir: str
) -> None:
    """Finish playback queue, stop media, and remove the run's part files."""
    if streaming_player:
        try:
            streaming_player.finish_generation()
        except Exception:
            pass
        stop_active_streaming_player()
    shutil.rmtree(work_dir, ignore_errors=True)


async def ultra_fast_parallel_generation(
    chunks: List[str],
    language: str,
    parallel: int = OPTIMAL_WORKERS,
    streaming_player: StreamingAudioPlayer = None,
    output_path: str = "data.mp3",
    *,
    voice: Optional[str] = None,
    prosody=None,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    work_dir: Optional[str] = None,
) -> List[str]:
    """Ultra-fast parallel generation with optional cancel, progress, voice, and prosody.

    Parts are written as ``.part_<i>.mp3`` inside *work_dir* (a fresh run dir
    when omitted) and returned in chunk order; they never alias *output_path*,
    which is kept only for signature compatibility. The caller merges them
    and removes *work_dir*.
    """
    owns_dir = work_dir is None
    run_dir = work_dir or _make_run_dir()
    parts = [os.path.join(run_dir, f".part_{i:04d}.mp3") for i in range(len(chunks))]

    def discard_parts() -> None:
        ultra_fast_cleanup_parts(parts, keep_parts=False)
        if owns_dir:
            shutil.rmtree(run_dir, ignore_errors=True)

    # Optimize concurrency based on system
    max_workers = min(parallel, OPTIMAL_WORKERS, len(chunks))
    
    # Use optimized semaphore with higher limits for I/O bound tasks
    sem = asyncio.Semaphore(max_workers)
    worker_errors: List[BaseException] = []

    async def worker(i: int, text: str, output: str):
        """Generate audio for a single chunk, notifying the streaming player on success."""
        async with sem:
            try:
                result = await fast_generate_audio(text, language, output,
                                                    quiet=True, voice=voice,
                                                    prosody=prosody)
                # If streaming is enabled, add chunk to player as soon as it's ready
                if result and streaming_player:
                    streaming_player.add_chunk(output, i)
                return (i, result)
            except Exception as e:
                _cprint(f"  [yellow]⚠[/yellow]  Chunk {i} failed: [dim]{e}[/dim]")
                worker_errors.append(e)
                return (i, False)
    
    # Create all tasks at once for better scheduling
    tasks = [asyncio.create_task(worker(i, chunks[i], parts[i])) for i in range(len(chunks))]

    if cancel_event is not None and cancel_event.is_set():
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        discard_parts()
        raise GenerationCancelled()

    progress = None
    if progress_callback is None:
        progress = create_progress_display(chunks, language)
    else:
        progress_callback(0, len(chunks))

    try:
        done_count = 0
        failed = 0
        for coro in asyncio.as_completed(tasks):
            if cancel_event is not None and cancel_event.is_set():
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if progress:
                    progress.finish(success=False)
                discard_parts()
                raise GenerationCancelled()
            chunk_idx, ok = await coro
            done_count += 1
            if not ok:
                # Fail fast: the run can't succeed, so stop spending requests on
                # it. Chunks that already finished are in the chunk cache, so a
                # re-run resumes instead of starting over.
                failed += 1
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                break
            chunk_words = (
                len(chunks[chunk_idx].split()) if 0 <= chunk_idx < len(chunks) else 0
            )
            if progress:
                progress.update(chunk_words)
            if progress_callback:
                progress_callback(done_count, len(chunks))

        if failed:
            # A missing chunk means missing text, so never merge a partial result.
            discard_parts()
            raise generation_failed(
                f"{failed} of {len(chunks)} chunks failed to synthesize",
                worker_errors[-1] if worker_errors else None,
            )

        if progress:
            progress.finish(success=True)
        elif progress_callback:
            progress_callback(len(chunks), len(chunks))
    except GenerationCancelled:
        if progress:
            progress.finish(success=False)
        raise
    except Exception as e:
        if progress:
            progress.finish(success=False)
        raise e

    return parts


async def _generate_direct(text, language, output_path, voice, prosody, cancel_event) -> None:
    """Single-shot synthesis of *text*; raises ``GenerationFailed`` instead of returning False."""
    ok = await _await_with_cancel(
        fast_generate_audio(text, language, output_path, quiet=True,
                            voice=voice, prosody=prosody),
        cancel_event,
    )
    if not ok:
        discard_empty_output(output_path)
        raise generation_failed("Audio generation failed")


def ultra_fast_cleanup_parts(parts: List[str], keep_parts: bool = False) -> None:
    """Ultra-fast parallel cleanup of temporary files with robust error handling."""
    if keep_parts:
        return
    
    def remove_file(part):
        try:
            if os.path.exists(part):
                os.remove(part)
        except (PermissionError, OSError):
            # File might be locked - try again after a short delay
            try:
                import time
                time.sleep(0.1)
                if os.path.exists(part):
                    os.remove(part)
            except OSError:
                pass  # File will be cleaned up on next run
        except OSError:
            pass
    
    # Use thread pool for parallel file deletion
    if len(parts) > 5:
        with ThreadPoolExecutor(max_workers=min(8, len(parts))) as executor:
            executor.map(remove_file, parts)
    else:
        # For few files, sequential is faster
        for part in parts:
            remove_file(part)


async def smart_generate_long_text(
    text: str,
    language: str,
    chunk_seconds: int = 30,
    parallel: int = OPTIMAL_WORKERS,
    output_path: str = "data.mp3",
    keep_parts: bool = False,
    enable_streaming: bool = False,
    show_gui: bool = True,
    preferred_player: Optional[str] = None,
    *,
    voice: Optional[str] = None,
    prosody=None,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Smart generation with dynamic optimization, optional voice/prosody, cancel, and progress."""
    text = replace_not_readable(text)
    if not text.strip():
        raise EmptyInputError("No readable text after filtering — input empty or only symbols/URLs/code.")

    from .chunking import split_text_into_chunks

    _sweep_stale_run_dirs()

    start = time.perf_counter()
    
    # Dynamic chunk sizing based on text length
    word_count = len(text.split())
    if word_count < 200 and not enable_streaming:
        # Very short text - direct generation is fastest (unless streaming is requested)
        if progress_callback:
            progress_callback(0, 1)
        await _generate_direct(text, language, output_path, voice, prosody, cancel_event)
        if progress_callback:
            progress_callback(1, 1)
        elapsed = time.perf_counter() - start
        _cprint(f"  [bold green]✓[/bold green]  [bold]Completed in {elapsed:.2f}s[/bold]  [dim](direct)[/dim]")
        return

    # Optimize chunk size based on text length and parallel workers
    optimal_chunk_seconds = max(15, min(60, word_count // (parallel * 2)))
    if chunk_seconds == 0:
        chunk_seconds = optimal_chunk_seconds
    
    # When streaming, carve a short lead-in first chunk so audio starts sooner
    # (lower time-to-first-audio); later chunks keep the normal size.
    first_chunk_seconds = STREAMING_FIRST_CHUNK_SECONDS if enable_streaming else 0
    chunks = split_text_into_chunks(
        text, approx_seconds=chunk_seconds, first_chunk_seconds=first_chunk_seconds
    )
    if not chunks:
        raise EmptyInputError("No text chunks to process — input text may be empty or whitespace-only")

    if len(chunks) == 1 and not enable_streaming:
        # Still short enough for direct generation (unless streaming is requested)
        if progress_callback:
            progress_callback(0, 1)
        await _generate_direct(text, language, output_path, voice, prosody, cancel_event)
        if progress_callback:
            progress_callback(1, 1)
        elapsed = time.perf_counter() - start
        _cprint(f"  [bold green]✓[/bold green]  [bold]Completed in {elapsed:.2f}s[/bold]  [dim](direct)[/dim]")
        return

    _cprint(f"  [cyan]⚡[/cyan]  [bold]{len(chunks)} chunks[/bold]  [dim]·  {parallel} workers[/dim]")
    
    # Initialize streaming player if enabled
    streaming_player = None
    if enable_streaming:
        from .streaming_player import PlayerDetector
        detected = PlayerDetector.find(preferred=preferred_player)

        if detected is None:
            print(
                "--stream needs a media player (vlc/mpv/ffplay); none found — "
                f"generating without live playback. Audio will be saved to {output_path}. "
                "Install one (run `tts-ka --doctor` for the command) to enable --stream.",
                file=sys.stderr,
            )
            show_gui = False

        streaming_player = StreamingAudioPlayer(show_gui=show_gui, preferred=preferred_player)
        streaming_player.start()
        if sys.platform.startswith('win'):
            mode = "GUI" if show_gui else "headless"
            _cprint(f"  [green]🔊[/green]  [bold]Streaming enabled[/bold]  [dim](Windows, {mode})[/dim]")
        else:
            _cprint("  [green]🔊[/green]  [bold]Streaming enabled[/bold]  [dim]· audio starts immediately[/dim]")
    
    # Generate chunks in parallel
    work_dir = _make_run_dir()
    released = True
    try:
        parts = await ultra_fast_parallel_generation(
            chunks,
            language,
            parallel,
            streaming_player,
            output_path,
            voice=voice,
            prosody=prosody,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            work_dir=work_dir,
        )

        if streaming_player:
            streaming_player.finish_generation()

        # The player reads the parts, never output_path, so merging while it
        # plays is safe. A merge failure propagates: never ship a partial file.
        fast_merge_audio_files(parts, output_path)

        if streaming_player:
            _cprint("  [dim]⏸  Waiting for playback to finish…[/dim]")
            released = await asyncio.to_thread(streaming_player.wait_until_released)
    except BaseException:
        _interrupt_streaming_cleanup(streaming_player, work_dir)
        raise

    # A player that outlives this call without saying it is done (a GUI window
    # fed a stdin playlist) may still open queued parts, so deleting them now
    # would cut playback short; _sweep_stale_run_dirs removes the dir later.
    if keep_parts:
        _cprint(f"  [dim]Part files kept in {work_dir}[/dim]")
    elif released:
        shutil.rmtree(work_dir, ignore_errors=True)

    elapsed = time.perf_counter() - start
    _cprint(
        f"  [bold green]✓[/bold green]  [bold]Completed in {elapsed:.2f}s[/bold]"
        f"  [dim]({len(chunks)} chunks, {parallel} workers)[/dim]"
    )


def get_optimal_settings(text: str) -> dict:
    """Calculate optimal settings based on text characteristics."""
    word_count = len(text.split())
    
    # Dynamic optimization
    if word_count < 100:
        return {'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}
    elif word_count < 500:
        return {'method': 'smart', 'chunk_seconds': 20, 'parallel': 2}
    elif word_count < 2000:
        return {'method': 'smart', 'chunk_seconds': 30, 'parallel': min(4, OPTIMAL_WORKERS)}
    else:
        return {'method': 'smart', 'chunk_seconds': 45, 'parallel': OPTIMAL_WORKERS}