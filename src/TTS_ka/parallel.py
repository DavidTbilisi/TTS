"""Parallel chunk generation with merging."""

import asyncio
import os
from typing import List

from .fast_audio import fallback_generate_audio


async def generate_chunks_parallel(
    chunks: List[str], language: str, output_dir: str, max_workers: int = 4
) -> List[str]:
    """Generate audio for multiple chunks in parallel.

    Args:
        chunks: List of text chunks
        language: Language code
        output_dir: Directory to store chunk files
        max_workers: Maximum parallel workers

    Returns:
        List of generated chunk file paths
    """
    os.makedirs(output_dir, exist_ok=True)

    # Create semaphore to limit concurrency
    sem = asyncio.Semaphore(max_workers)
    chunk_files = []

    async def generate_chunk(index: int, text: str) -> str:
        async with sem:
            chunk_file = os.path.join(output_dir, f"chunk_{index:04d}.mp3")
            # Use fallback_generate_audio (edge-tts) for chunk generation
            await fallback_generate_audio(text, language, chunk_file)
            return chunk_file

    # Generate all chunks
    print(f"Generating {len(chunks)} chunks with {max_workers} workers...")
    tasks = [generate_chunk(i, chunk) for i, chunk in enumerate(chunks)]
    chunk_files = await asyncio.gather(*tasks)

    return chunk_files


def merge_audio_files(chunk_files: List[str], output_file: str) -> bool:
    """Merge multiple audio files into one.

    Args:
        chunk_files: List of chunk file paths
        output_file: Final output file path

    Returns:
        True if successful
    """
    if not chunk_files:
        return False

    # Single file - just copy
    if len(chunk_files) == 1:
        import shutil

        shutil.copy2(chunk_files[0], output_file)
        return True

    # Try pydub first (optional dependency)
    try:
        from pydub import AudioSegment

        print(f"Merging {len(chunk_files)} chunks...")
        combined = AudioSegment.from_mp3(chunk_files[0])
        for chunk_file in chunk_files[1:]:
            if os.path.exists(chunk_file):
                combined += AudioSegment.from_mp3(chunk_file)

        combined.export(output_file, format="mp3")
        print(f"✓ Merged to: {output_file}")
        return True

    except ImportError:
        # Fallback to ffmpeg concat
        return _merge_with_ffmpeg(chunk_files, output_file)


def _merge_with_ffmpeg(chunk_files: List[str], output_file: str) -> bool:
    """Merge using ffmpeg concat protocol.

    Args:
        chunk_files: List of chunk file paths
        output_file: Final output file path

    Returns:
        True if successful
    """
    import tempfile

    # Create concat list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_file = f.name
        for chunk_file in chunk_files:
            if os.path.exists(chunk_file):
                # Use forward slashes for ffmpeg
                path = os.path.abspath(chunk_file).replace("\\", "/")
                f.write(f"file '{path}'\n")

    try:
        # Run ffmpeg
        cmd = f'ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "{list_file}" -c copy "{output_file}"'
        result = os.system(cmd)

        if result == 0:
            print(f"✓ Merged to: {output_file}")
            return True
        else:
            print(f"✗ ffmpeg merge failed (exit code {result})")
            return False

    finally:
        # Cleanup list file
        try:
            os.remove(list_file)
        except Exception:
            pass


def cleanup_chunks(chunk_files: List[str]) -> None:
    """Remove temporary chunk files.

    Args:
        chunk_files: List of chunk file paths to remove
    """
    for chunk_file in chunk_files:
        try:
            if os.path.exists(chunk_file):
                os.remove(chunk_file)
        except Exception:
            pass
