"""Ultra-Fast Text-to-Speech CLI tool."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

from .fast_audio import fast_generate_audio, play_audio, cleanup_http
from .ultra_fast import smart_generate_long_text, get_optimal_settings, OPTIMAL_WORKERS
from .simple_help import show_simple_help, show_troubleshooting
from .constants import STREAMING_CHUNK_SECONDS


def _read_clipboard() -> str:
    """Read clipboard text using stdlib — no third-party dependencies.

    Tries tkinter first (cross-platform), then platform-specific fallbacks.
    Returns an empty string when the clipboard cannot be accessed.
    """
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            return root.clipboard_get()
        finally:
            root.destroy()
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.rstrip("\n")
        except Exception:
            pass

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass

    return ""


def get_input_text(text_input: str) -> str:
    """Process text input — handle clipboard, file paths, or direct text."""
    if text_input == "clipboard":
        text = _read_clipboard().replace("\r\n", "\n")
        if not text.strip():
            print("No text was copied from the clipboard.")
            return ""
        return text

    if os.path.exists(text_input) and os.path.isfile(text_input):
        with open(text_input, "r", encoding="utf-8") as f:
            return f.read()

    return text_input


def main() -> None:
    parser = argparse.ArgumentParser(
        description="🚀 Ultra-Fast TTS - Georgian, Russian, English generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
  %(prog)s "Hello world" --lang en                  # Quick English generation
  %(prog)s "გამარჯობა" --lang ka                    # Georgian with auto-optimization
  %(prog)s file.txt --lang ru                       # Russian from file
  %(prog)s clipboard                                 # From clipboard (fastest workflow)

LANGUAGES: 🇬🇪 ka / ka-m (Georgian female/male) | 🇷🇺 ru | 🇬🇧 en
For comprehensive help with examples: %(prog)s --help-full
        """,
    )

    parser.add_argument(
        "text",
        nargs="?",
        help='Text to convert (file path, "clipboard", or direct text)',
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["ka", "ka-m", "ru", "en"],
        help="Language: ka=Georgian female, ka-m=Georgian male, ru=Russian, en=English",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=0,
        help="Chunk size in seconds (0=auto-detect, 20-60 recommended)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=0,
        help=f"Parallel workers (0=auto, 2-8 recommended, max={OPTIMAL_WORKERS})",
    )
    parser.add_argument("--no-play", action="store_true", help="Skip automatic audio playback")
    parser.add_argument(
        "--no-turbo",
        action="store_true",
        help="Disable auto-optimization (legacy mode)",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Enable streaming playback (audio starts playing while still generating)",
    )
    parser.add_argument(
        "--no-gui",
        dest="show_player",
        action="store_false",
        default=True,
        help="Disable VLC player GUI when streaming (use headless playback)",
    )
    parser.add_argument(
        "--help-full",
        action="store_true",
        help="Show comprehensive help with examples and workflows",
    )

    args = parser.parse_args()

    if args.help_full:
        show_simple_help()
        show_troubleshooting()
        return

    if not args.text:
        show_simple_help()
        print("Error: No text provided")
        print("Try: python -m TTS_ka 'your text' --lang en")
        return

    text = get_input_text(args.text)
    if not text:
        return
    output_path = "data.mp3"

    if not args.no_turbo:
        optimal = get_optimal_settings(text)
        if args.chunk_seconds == 0:
            args.chunk_seconds = optimal["chunk_seconds"]
        if args.parallel == 0:
            args.parallel = optimal["parallel"]

        if args.stream and args.chunk_seconds == 0:
            args.chunk_seconds = STREAMING_CHUNK_SECONDS
            optimal["method"] = "smart"
            print(f"🔊 Streaming enabled - forcing chunked generation ({STREAMING_CHUNK_SECONDS}s chunks)")

        lang_names = {"ka": "Georgian", "ka-m": "Georgian (male)", "ru": "Russian", "en": "English"}
        lang_name = lang_names.get(args.lang, "Unknown")
        print(f"OPTIMIZED MODE - {lang_name}")
        print(f"Strategy: {optimal['method']} generation, {args.parallel} workers")
        print(f"Processing: {len(text.split())} words, {len(text)} characters")

    if args.parallel == 0:
        args.parallel = min(4, OPTIMAL_WORKERS)

    async def run_generation() -> None:
        try:
            if args.chunk_seconds > 0 or len(text.split()) > 200 or args.stream:
                await smart_generate_long_text(
                    text,
                    args.lang,
                    chunk_seconds=args.chunk_seconds or 30,
                    parallel=args.parallel,
                    output_path=output_path,
                    enable_streaming=args.stream,
                    show_gui=args.show_player,
                )
            else:
                start = time.perf_counter()
                await fast_generate_audio(text, args.lang, output_path)
                elapsed = time.perf_counter() - start
                print(f"⚡ Completed in {elapsed:.2f}s (direct)")

            if not args.no_play and not args.stream:
                play_audio(output_path)
        finally:
            try:
                await cleanup_http()
            except Exception:
                pass

    try:
        asyncio.run(run_generation())
    except KeyboardInterrupt:
        print("\n⚡ Generation cancelled")


if __name__ == "__main__":
    main()
