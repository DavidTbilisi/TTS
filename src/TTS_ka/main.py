import argparse
import os
import shutil
import hashlib
import concurrent.futures
from typing import List
AudioSegment = None
tqdm = None
try:
    from pydub import AudioSegment
    _HAS_PYDUB = True
except Exception:
    _HAS_PYDUB = False
try:
    from tqdm import tqdm
    _HAS_TQDM = True
except Exception:
    _HAS_TQDM = False
import sys
import pyperclip
from edge_tts import Communicate
import time


def _cache_filename(text: str, voice: str) -> str:
    """Return a deterministic cache filename for text+voice."""
    h = hashlib.sha256()
    h.update(voice.encode('utf-8'))
    h.update(b"\x00")
    h.update(text.encode('utf-8'))
    return f".tts_cache_{h.hexdigest()}.mp3"


def _generate_sync(text: str, language: str, out_path: str = 'data.mp3', use_cache: bool = True) -> None:
    """Synchronous wrapper to run the async text_to_speech in a thread or sequentially."""
    try:
        import asyncio
        # run quietly when used as a worker
        asyncio.run(text_to_speech(text, language, out_path, quiet=True, use_cache=use_cache))
    except Exception as e:
        print(f"Error generating '{text[:30]}...': {e}")


def _split_text_into_chunks(text: str, approx_seconds: int = 60) -> List[str]:
    """Naive text splitter that tries to create chunks roughly approx_seconds long.
    This uses words-per-minute heuristics (avg 160 wpm -> ~2.66 wps).
    """
    wpm = 160
    words_per_second = wpm / 60.0
    words_per_chunk = max(20, int(words_per_second * approx_seconds))
    words = text.split()
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunks.append(' '.join(words[i:i+words_per_chunk]))
    return chunks


def _merge_mp3_files(parts: List[str], out_path: str) -> None:
    """Merge mp3 files in parts into out_path. Prefer pydub, fallback to ffmpeg concat."""
    if not parts:
        raise ValueError("no parts to merge")

    if _HAS_PYDUB:
        # import locally so static analyzers don't complain when pydub is absent
        from pydub import AudioSegment as _AudioSegment
        # ensure we will overwrite without prompt
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        combined = _AudioSegment.from_mp3(parts[0])
        for p in parts[1:]:
            combined += _AudioSegment.from_mp3(p)
        combined.export(out_path, format='mp3')
    else:
        # create a temporary concat file for ffmpeg
        listfile = '.ff_concat.txt'
        with open(listfile, 'w', encoding='utf-8') as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        # run ffmpeg
        # -y to overwrite without asking
        rc = os.system(f"ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i {listfile} -c copy {out_path}")
        try:
            os.remove(listfile)
        except Exception:
            pass
        if rc != 0:
            raise RuntimeError('ffmpeg concat failed')


def generate_long_text(text: str, language: str, chunk_seconds: int = 60, parallel: int = 2, out_path: str = 'data.mp3', keep_parts: bool = False, use_cache: bool = True):
    """Split long text, generate parts (parallel), show progress, and merge into out_path."""
    start = time.perf_counter()
    chunks = _split_text_into_chunks(text, approx_seconds=chunk_seconds)
    if len(chunks) == 1:
        # short enough
        _generate_sync(text, language, out_path, use_cache=use_cache)
        elapsed = time.perf_counter() - start
        print(f"Completed generation in {elapsed:.2f} seconds.")
        return

    parts = []
    for i, _ in enumerate(chunks):
        part_name = f".part_{i}.mp3"
        # remove existing part to avoid interactive prompts from underlying tools
        try:
            if os.path.exists(part_name):
                os.remove(part_name)
        except Exception:
            pass
        parts.append(part_name)

    total = len(chunks)

    # Run all chunk generation coroutines inside a single asyncio event loop.
    # Use a semaphore to bound concurrent requests to `parallel`.
    async def _run_parts_async():
        import asyncio as _asyncio

        sem = _asyncio.Semaphore(max(1, parallel))

        async def _worker(i: int, txt: str, outp: str):
            async with sem:
                try:
                    await text_to_speech(txt, language, outp, quiet=True, use_cache=use_cache)
                except Exception as e:
                    # surface part-level errors but keep going
                    print(f"Error generating part {i}: {e}")

        tasks = [_asyncio.create_task(_worker(i, chunks[i], parts[i])) for i in range(total)]

        if _HAS_TQDM:
            from tqdm import tqdm as _tqdm
            pbar = _tqdm(total=total, desc='Generating')
            for coro in _asyncio.as_completed(tasks):
                await coro
                pbar.update(1)
            pbar.close()
        else:
            completed = 0
            for coro in _asyncio.as_completed(tasks):
                await coro
                completed += 1
                sys.stdout.write(f"\rGenerating: {completed}/{total}")
                sys.stdout.flush()
            sys.stdout.write("\n")

    import asyncio
    asyncio.run(_run_parts_async())

    # merge
    # remove existing output to avoid prompts
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except Exception:
        pass
    _merge_mp3_files(parts, out_path)
    if not keep_parts:
        for p in parts:
            try:
                os.remove(p)
            except Exception:
                pass
    elapsed = time.perf_counter() - start
    print(f"Completed generation in {elapsed:.2f} seconds.")


async def text_to_speech(text, language, out_path: str = 'data.mp3', quiet: bool = False, use_cache: bool = True):
    """
    Converts the given text to speech in the specified language.
    
    Parameters:
    - text (str): The text to convert to speech.
    - language (str): The language code for the speech ('en' for English, 'ka' for Georgian, 'ru' for Russian).
    
    Returns:
    None
    """
    voice = {
        'ka': 'ka-GE-EkaNeural',
        'en': 'en-GB-SoniaNeural',
        'ru': 'ru-RU-SvetlanaNeural',
        'en-US': 'en-US-SteffanNeural'
    }.get(language, 'en-GB-SoniaNeural')



  
    # try cache
    cache_file = _cache_filename(text, voice)
    if use_cache and os.path.exists(cache_file):
        # copy to data.mp3 quickly (overwrite)
        try:
            if os.path.abspath(cache_file) != os.path.abspath(out_path):
                shutil.copyfile(cache_file, out_path)
            return_code = 0
        except Exception:
            return_code = 1
    else:
        communicate = Communicate(text, voice)
        try:
            await communicate.save(out_path)
            # save copy to cache (best-effort)
            if use_cache:
                try:
                    if os.path.abspath(cache_file) != os.path.abspath(out_path):
                        shutil.copyfile(out_path, cache_file)
                except Exception:
                    # ignore cache save failures
                    pass
            return_code = 0
        except Exception:
            return_code = 1
    
    

    if return_code != 0:
        if not quiet:
            print("Error generating audio file.")
    else:
        if not quiet:
            print(f"Audio file generated at {os.path.abspath(out_path)}")
            # non-blocking playback per-platform
            if sys.platform.startswith('win'):
                # use os.startfile on Windows (non-blocking)
                try:
                    os.startfile(os.path.abspath(out_path))
                except Exception:
                    # fallback to start via cmd
                    os.system(f"start {os.path.abspath(out_path)}")
            elif sys.platform == 'darwin':
                os.system(f"open '{os.path.abspath(out_path)}' &")
            else:
                # try xdg-open, fallback to mpg123 if available
                if os.system(f"xdg-open '{os.path.abspath(out_path)}' &") != 0:
                    # try mpg123
                    os.system(f"mpg123 '{os.path.abspath(out_path)}' &")
    # end of async function


def play_file(out_path: str) -> None:
    """Play file non-blocking using platform-specific commands."""
    try:
        if sys.platform.startswith('win'):
            os.startfile(os.path.abspath(out_path))
        elif sys.platform == 'darwin':
            os.system(f"open '{os.path.abspath(out_path)}' &")
        else:
            if os.system(f"xdg-open '{os.path.abspath(out_path)}' &") != 0:
                os.system(f"mpg123 '{os.path.abspath(out_path)}' &")
    except Exception:
        # best-effort playback
        pass

def main():
    parser = argparse.ArgumentParser(description='Text to Speech CLI')
    parser.add_argument('text', nargs='?', help='Text to convert to speech (optional when using --clear-cache)')
    parser.add_argument('--lang', type=str, default='en', help='Language of the text')
    parser.add_argument('--chunk-seconds', type=int, default=0, help='Split long texts into chunks of approx this many seconds (0=disabled)')
    parser.add_argument('--parallel', type=int, default=1, help='Number of workers for parallel generation')
    parser.add_argument('--no-play', action='store_true', help='Do not auto-play the generated file')
    parser.add_argument('--no-cache', action='store_true', help='Do not use or save cache during this run')
    parser.add_argument('--clear-cache', action='store_true', help='Clear cache files before running')
    parser.add_argument('--cache-age-days', type=int, default=0, help='If >0 and used without text, delete cache files older than this many days and exit')
    parser.add_argument('--dry', action='store_true', help='With --clear-cache or --cache-age-days, only report how much would be removed')
    parser.add_argument('--clear-all-artifacts', action='store_true', help='When clearing cache, also remove part files and output')
    args = parser.parse_args()

    # If user only asked to clear cache (no text given), do it and exit
    if args.clear_cache and not args.text:
        import glob
        removed = []
        total_bytes = 0
        for f in glob.glob('.tts_cache_*.mp3'):
            try:
                sz = os.path.getsize(f)
                total_bytes += sz
                if not args.dry:
                    os.remove(f)
                    removed.append(f)
            except Exception:
                pass
        if args.clear_all_artifacts:
            for f in glob.glob('.part_*.mp3') + glob.glob('data*.mp3'):
                try:
                    sz = os.path.getsize(f)
                    total_bytes += sz
                    if not args.dry:
                        os.remove(f)
                        removed.append(f)
                except Exception:
                    pass
        mb = total_bytes / (1024*1024)
        if args.dry:
            print(f"Cache + artifacts would free {mb:.2f} MB ({total_bytes} bytes) and {len(glob.glob('.tts_cache_*.mp3'))} cache files match.")
        else:
            print(f"Cleared {len(removed)} files, freed {mb:.2f} MB ({total_bytes} bytes).")
            for r in removed:
                print(' -', r)
        return

    # NOTE: automatic startup deletion removed. Use --cache-age-days to delete old caches on demand.
    if args.cache_age_days > 0 and not args.text:
        import glob, time as _time
        cutoff = _time.time() - (args.cache_age_days * 24 * 60 * 60)
        removed = []
        total_bytes = 0
        for f in glob.glob('.tts_cache_*.mp3'):
            try:
                if os.path.getmtime(f) < cutoff:
                    sz = os.path.getsize(f)
                    total_bytes += sz
                    if not args.dry:
                        os.remove(f)
                        removed.append(f)
            except Exception:
                pass
        mb = total_bytes / (1024*1024)
        if args.dry:
            print(f"Cache older than {args.cache_age_days} days would free {mb:.2f} MB ({total_bytes} bytes) and {len([1 for _ in glob.glob('.tts_cache_*.mp3') if os.path.getmtime(_)<cutoff])} matching files.")
        else:
            print(f"Cleared {len(removed)} files, freed {mb:.2f} MB ({total_bytes} bytes).")
            for r in removed:
                print(' -', r)
        return

    if args.text == "clipboard":
        args.text = pyperclip.paste().replace('\r\n', '\n')
        if not args.text.strip():
            print("No text was copied from the clipboard.")
            return
    # if args.text is a path to a file, read it
    if os.path.exists(args.text) and os.path.isfile(args.text):
        with open(args.text, 'r', encoding='utf-8') as f:
            args.text = f.read()
        
    # Decide whether to chunk
    words = args.text.split()
    # cache control
    if args.clear_cache:
        import glob
        for f in glob.glob('.tts_cache_*.mp3'):
            try:
                os.remove(f)
            except Exception:
                pass
    use_cache = not args.no_cache
    if args.chunk_seconds > 0 or len(words) > 1000:
        # use chunking
        generate_long_text(args.text, args.lang, chunk_seconds=(args.chunk_seconds or 60), parallel=args.parallel, out_path='data.mp3', use_cache=use_cache)
        if not args.no_play:
            play_file('data.mp3')
    else:
        import asyncio
        start = time.perf_counter()
        asyncio.run(text_to_speech(args.text, args.lang, 'data.mp3', use_cache=use_cache))
        elapsed = time.perf_counter() - start
        print(f"Completed generation in {elapsed:.2f} seconds.")
        if not args.no_play:
            play_file('data.mp3')

if __name__ == "__main__":
    main()