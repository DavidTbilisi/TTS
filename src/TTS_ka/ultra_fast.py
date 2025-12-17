"""Ultra-fast parallel processing with optimized concurrency."""

import asyncio
import os
import sys
from typing import List
from concurrent.futures import ThreadPoolExecutor
import multiprocessing as mp

try:
    import uvloop
    HAS_UVLOOP = True
except ImportError:
    HAS_UVLOOP = False

from .fast_audio import fast_generate_audio, fast_merge_audio_files
from .rich_progress import create_progress_display, animate_loading
from .streaming_player import StreamingAudioPlayer

# Optimal worker count
OPTIMAL_WORKERS = min(32, (os.cpu_count() or 1) * 4)


async def ultra_fast_parallel_generation(chunks: List[str], language: str, 
                                       parallel: int = OPTIMAL_WORKERS,
                                       streaming_player: StreamingAudioPlayer = None,
                                       output_path: str = 'data.mp3') -> List[str]:
    """Ultra-fast parallel generation with optimized concurrency and optional streaming playback."""
    
    # Use uvloop for maximum performance on Unix systems
    if HAS_UVLOOP and sys.platform != 'win32':
        try:
            loop = uvloop.new_event_loop()
            asyncio.set_event_loop(loop)
        except Exception:
            pass
    
    parts = []
    
    # Pre-allocate part files - if streaming, first chunk becomes output file
    for i in range(len(chunks)):
        if i == 0 and streaming_player:
            # First chunk becomes the final output file for immediate playback
            part_name = output_path
        else:
            part_name = f".part_{i}.mp3"
            # Safe file removal - handle locked files gracefully
            if os.path.exists(part_name):
                try:
                    os.remove(part_name)
                except (PermissionError, OSError) as e:
                    # File might be locked by media player - try alternative name
                    import time
                    timestamp = int(time.time() * 1000)
                    part_name = f".part_{i}_{timestamp}.mp3"
        parts.append(part_name)
    
    # Optimize concurrency based on system
    max_workers = min(parallel, OPTIMAL_WORKERS, len(chunks))
    
    # Use optimized semaphore with higher limits for I/O bound tasks
    sem = asyncio.Semaphore(max_workers)
    
    async def worker(i: int, text: str, output: str):
        async with sem:
            try:
                result = await fast_generate_audio(text, language, output, quiet=True)
                # If streaming is enabled, add chunk to player as soon as it's ready
                if result and streaming_player:
                    streaming_player.add_chunk(output)
                return result
            except Exception as e:
                print(f"⚠️  Error generating part {i}: {e}")
                return False
    
    # Create all tasks at once for better scheduling
    tasks = [asyncio.create_task(worker(i, chunks[i], parts[i])) 
             for i in range(len(chunks))]
    
    # Rich progress display with statistics
    progress = create_progress_display(chunks, language)
    
    try:
        # Process tasks as they complete with rich progress updates
        completed_tasks = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed_tasks.append(result)
            
            # Update progress with chunk word count
            chunk_idx = len(completed_tasks) - 1
            chunk_words = len(chunks[chunk_idx].split()) if chunk_idx < len(chunks) else 0
            progress.update(chunk_words)
        
        progress.finish(success=True)
    except Exception as e:
        progress.finish(success=False)
        raise e
    
    return parts


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
            except Exception:
                # If still can't remove, silently continue (file will be cleaned up later)
                pass
        except Exception:
            pass
    
    # Use thread pool for parallel file deletion
    if len(parts) > 5:
        with ThreadPoolExecutor(max_workers=min(8, len(parts))) as executor:
            executor.map(remove_file, parts)
    else:
        # For few files, sequential is faster
        for part in parts:
            remove_file(part)


async def smart_generate_long_text(text: str, language: str, chunk_seconds: int = 30, 
                                  parallel: int = OPTIMAL_WORKERS, output_path: str = 'data.mp3',
                                  keep_parts: bool = False, enable_streaming: bool = False) -> None:
    """Smart generation with dynamic optimization based on text length and optional streaming playback."""
    
    from .chunking import split_text_into_chunks
    import time
    import glob
    
    # Clean up any leftover part files from previous runs/crashes
    for old_part in glob.glob('.part_*.mp3'):
        try:
            os.remove(old_part)
        except Exception:
            pass
    
    start = time.perf_counter()
    
    # Dynamic chunk sizing based on text length
    word_count = len(text.split())
    if word_count < 200 and not enable_streaming:
        # Very short text - direct generation is fastest (unless streaming is requested)
        await fast_generate_audio(text, language, output_path)
        elapsed = time.perf_counter() - start
        print(f"⚡ Completed in {elapsed:.2f}s (direct)")
        return
    
    # Debug logging for streaming
    if enable_streaming:
        print(f"📊 Streaming mode: {word_count} words, proceeding with chunked generation")
    
    # Optimize chunk size based on text length and parallel workers
    optimal_chunk_seconds = max(15, min(60, word_count // (parallel * 2)))
    if chunk_seconds == 0:
        chunk_seconds = optimal_chunk_seconds
    
    chunks = split_text_into_chunks(text, approx_seconds=chunk_seconds)
    
    if len(chunks) == 1 and not enable_streaming:
        # Still short enough for direct generation (unless streaming is requested)
        await fast_generate_audio(text, language, output_path)
        elapsed = time.perf_counter() - start
        print(f"⚡ Completed in {elapsed:.2f}s (direct)")
        return
    
    print(f"⚡ Using {len(chunks)} chunks with {parallel} workers")
    
    # Initialize streaming player if enabled
    streaming_player = None
    if enable_streaming:
        streaming_player = StreamingAudioPlayer()
        streaming_player.start()
        if sys.platform.startswith('win'):
            print("🔊 Streaming enabled - first chunk will play immediately (Windows mode)")
        else:
            print("🔊 Streaming playback enabled - audio will start playing immediately")
    
    # Generate chunks in parallel
    parts = await ultra_fast_parallel_generation(chunks, language, parallel, streaming_player, output_path)
    
    try:
        # Signal streaming completion
        if streaming_player:
            streaming_player.finish_generation()
        
        # For streaming: ensure final complete audio is in output_path
        if streaming_player:
            if len(parts) > 1:
                remaining_parts = [p for p in parts[1:] if os.path.exists(p)]
                if remaining_parts:
                    # Wait for media player to release the file
                    time.sleep(0.3)
                    
                    # Create backup of first chunk
                    backup_path = output_path + ".backup"
                    try:
                        import shutil
                        shutil.copy2(output_path, backup_path)
                        
                        # Merge all parts directly to output_path
                        all_parts = [backup_path] + remaining_parts
                        fast_merge_audio_files(all_parts, output_path)
                        
                        # Clean up backup
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                            
                    except Exception as e:
                        print(f"⚠️  Merge warning: {e}")
                        # Restore backup if merge failed
                        if os.path.exists(backup_path):
                            try:
                                shutil.move(backup_path, output_path)
                            except Exception:
                                pass
            # For single chunk streaming, file is already complete in output_path
        else:
            # Normal merge for non-streaming
            fast_merge_audio_files(parts, output_path)
        
        # Fast cleanup (but keep output_path)
        cleanup_parts = [p for p in parts if p != output_path]
        ultra_fast_cleanup_parts(cleanup_parts, keep_parts)
        
        # Wait for streaming playback to complete if enabled
        if streaming_player:
            print("⏸️  Waiting for playback to complete...")
            streaming_player.wait_for_completion()
            # Small delay to ensure files are released by media player
            time.sleep(0.2)
        
        elapsed = time.perf_counter() - start
        print(f"⚡ Completed in {elapsed:.2f}s ({len(chunks)} chunks, {parallel} workers)")
    except KeyboardInterrupt:
        # Cleanup on interruption
        ultra_fast_cleanup_parts(parts, keep_parts=False)
        raise
    except Exception as e:
        # Cleanup on error
        ultra_fast_cleanup_parts(parts, keep_parts=False)
        raise


def get_optimal_settings(text: str) -> dict:
    """Calculate optimal settings based on text characteristics."""
    word_count = len(text.split())
    char_count = len(text)
    
    # Dynamic optimization
    if word_count < 100:
        return {'method': 'direct', 'chunk_seconds': 0, 'parallel': 1}
    elif word_count < 500:
        return {'method': 'smart', 'chunk_seconds': 20, 'parallel': 2}
    elif word_count < 2000:
        return {'method': 'smart', 'chunk_seconds': 30, 'parallel': min(4, OPTIMAL_WORKERS)}
    else:
        return {'method': 'smart', 'chunk_seconds': 45, 'parallel': OPTIMAL_WORKERS}