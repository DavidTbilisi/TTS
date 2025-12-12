"""Parallel processing utilities for audio generation."""

import asyncio
import os
import sys
from typing import List
from .audio import generate_audio, merge_audio_files

# Optional imports
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


async def generate_chunks_parallel(chunks: List[str], language: str, 
                                 parallel: int = 2, use_cache: bool = True) -> List[str]:
    """Generate audio for multiple text chunks in parallel."""
    parts = []
    
    # Prepare part files
    for i in range(len(chunks)):
        part_name = f".part_{i}.mp3"
        if os.path.exists(part_name):
            os.remove(part_name)
        parts.append(part_name)
    
    # Create semaphore to limit concurrency
    sem = asyncio.Semaphore(max(1, parallel))
    
    async def worker(i: int, text: str, output: str):
        async with sem:
            try:
                await generate_audio(text, language, output, use_cache=use_cache, quiet=True)
            except Exception as e:
                print(f"Error generating part {i}: {e}")
    
    # Create tasks
    tasks = [asyncio.create_task(worker(i, chunks[i], parts[i])) 
             for i in range(len(chunks))]
    
    # Show progress
    if HAS_TQDM:
        pbar = tqdm(total=len(tasks), desc='Generating')
        for coro in asyncio.as_completed(tasks):
            await coro
            pbar.update(1)
        pbar.close()
    else:
        completed = 0
        for coro in asyncio.as_completed(tasks):
            await coro
            completed += 1
            sys.stdout.write(f"\rGenerating: {completed}/{len(tasks)}")
            sys.stdout.flush()
        sys.stdout.write("\n")
    
    return parts


def cleanup_parts(parts: List[str], keep_parts: bool = False) -> None:
    """Remove temporary part files."""
    if not keep_parts:
        for part in parts:
            try:
                if os.path.exists(part):
                    os.remove(part)
            except Exception:
                pass