import argparse
import os
import shutil
import hashlib
import concurrent.futures
from typing import List
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


def _cache_filename(text: str, voice: str) -> str:
    """Return a deterministic cache filename for text+voice."""
    h = hashlib.sha256()
    h.update(voice.encode('utf-8'))
    h.update(b"\x00")
    h.update(text.encode('utf-8'))
    return f".tts_cache_{h.hexdigest()}.mp3"


def _generate_sync(text: str, language: str, out_path: str = 'data.mp3') -> None:
    """Synchronous wrapper to run the async text_to_speech in a thread or sequentially."""
    try:
        import asyncio
        # run quietly when used as a worker
        asyncio.run(text_to_speech(text, language, out_path, quiet=True))
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
        # ensure we will overwrite without prompt
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        combined = AudioSegment.from_mp3(parts[0])
        for p in parts[1:]:
            combined += AudioSegment.from_mp3(p)
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


def generate_long_text(text: str, language: str, chunk_seconds: int = 60, parallel: int = 2, out_path: str = 'data.mp3', keep_parts: bool = False):
    """Split long text, generate parts (parallel), show progress, and merge into out_path."""
    chunks = _split_text_into_chunks(text, approx_seconds=chunk_seconds)
    if len(chunks) == 1:
        # short enough
        _generate_sync(text, language, out_path)
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
    # submit tasks
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        futures = {ex.submit(_generate_sync, chunks[i], language, parts[i]): i for i in range(total)}
        if _HAS_TQDM:
            pbar = tqdm(total=total, desc='Generating')
            for fut in concurrent.futures.as_completed(futures):
                pbar.update(1)
            pbar.close()
        else:
            # simple single-line progress update
            completed = 0
            for fut in concurrent.futures.as_completed(futures):
                completed += 1
                sys.stdout.write(f"\rGenerating: {completed}/{total}")
                sys.stdout.flush()
            # finish line
            sys.stdout.write("\n")

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


async def text_to_speech(text, language, out_path: str = 'data.mp3', quiet: bool = False):
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
    if os.path.exists(cache_file):
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
    parser.add_argument('text', help='Text to convert to speech')
    parser.add_argument('--lang', type=str, default='en', help='Language of the text')
    parser.add_argument('--chunk-seconds', type=int, default=0, help='Split long texts into chunks of approx this many seconds (0=disabled)')
    parser.add_argument('--parallel', type=int, default=1, help='Number of workers for parallel generation')
    parser.add_argument('--no-play', action='store_true', help='Do not auto-play the generated file')
    args = parser.parse_args()

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
    if args.chunk_seconds > 0 or len(words) > 1000:
        # use chunking
        generate_long_text(args.text, args.lang, chunk_seconds=(args.chunk_seconds or 60), parallel=args.parallel, out_path='data.mp3')
        if not args.no_play:
            play_file('data.mp3')
    else:
        import asyncio
        asyncio.run(text_to_speech(args.text, args.lang, 'data.mp3'))

if __name__ == "__main__":
    main()