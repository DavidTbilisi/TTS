"""Unified CLI for TTS_ka: provides `synth`, `ultra`, and `list-voices` subcommands.

Also supports a compact "simple mode" invocation (no subcommand) with rich output:
  -l/--lang
  -o/--out
  -s/--speed
Positional text is required in simple mode.
"""

import argparse
import asyncio
import os
import sys
from typing import Any, Optional

try:
    import pyperclip

    HAS_CLIPBOARD = True
except Exception:
    HAS_CLIPBOARD = False

from rich.console import Console

from .audio import generate_audio, merge_audio_files, play_audio
from .chunker import needs_chunking, split_into_chunks
from .not_reading import sanitize_text
from .parallel import cleanup_chunks, generate_chunks_parallel
from .simple_help import show_simple_help, show_troubleshooting
from .ultra_fast import OPTIMAL_WORKERS, get_optimal_settings, smart_generate_long_text

console = Console()


def get_text_input(text_input: str) -> str:
    """Get text from various sources.

    Args:
        text_input: Text, file path, or 'clipboard'

    Returns:
        Text content
    """
    # Clipboard
    if text_input == "clipboard":
        if not HAS_CLIPBOARD:
            console.print(
                "[red]Error:[/] pyperclip not installed. Install with: pip install pyperclip"
            )
            return ""

        text = str(pyperclip.paste())
        if not text or not text.strip():
            console.print("[red]Error:[/] Clipboard is empty")
            return ""
        # Normalize CRLF to LF and remove trailing newlines for predictable counts
        return text.replace("\r\n", "\n").rstrip("\n")

    # File
    if os.path.isfile(text_input):
        try:
            with open(text_input, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            # On read errors, return the original path (tests expect this fallback)
            console.print(f"Error reading file: {e}")
            return text_input

    # Direct text
    return text_input


async def process_text_synth(
    text: str, language: str, output_file: str, no_play: bool = False, workers: int = 4
) -> bool:
    """Process text to speech (synth command).

    Args:
        text: Text to convert
        language: Language code (ka, ru, en)
        output_file: Output file path
        no_play: Don't play audio after generation
        workers: Number of parallel workers for long text

    Returns:
        True if successful
    """
    # Ensure text is sanitized before any chunking/generation
    text = sanitize_text(text)

    # Short text - direct generation
    if not needs_chunking(text):
        success = await generate_audio(text, language, output_file)
        if success and not no_play:
            play_audio(output_file)
        return success

    # Long text - chunked parallel generation
    console.print(f"Long text detected ({len(text.split())} words) - using parallel generation")
    chunks = split_into_chunks(text)

    # Setup paths
    output_dir = os.path.dirname(output_file) or "."
    chunk_dir = os.path.join(output_dir, ".tts_chunks")

    try:
        # Generate chunks in parallel
        chunk_files = await generate_chunks_parallel(chunks, language, chunk_dir, workers)

        # Merge chunks
        try:
            merge_audio_files(chunk_files, output_file)
        except Exception:
            return False

        # Cleanup
        cleanup_chunks(chunk_files)
        try:
            os.rmdir(chunk_dir)
        except Exception:
            pass

        # Play
        if not no_play:
            play_audio(output_file)

        return True

    except Exception as e:
        console.print(f"[red]Error processing long text:[/] {e}")
        return False


def synth_command(args: Any) -> None:
    """Process synth subcommand."""
    text = get_text_input(args.text)
    if not text:
        sys.exit(1)

    # Sanitize text (mandatory for all generation paths)
    text = sanitize_text(text)

    # Output default
    output_file = args.output or os.path.join(".venv", "data.mp3")
    if not args.output:
        os.makedirs(".venv", exist_ok=True)

    console.print(f"Language: {args.lang}")
    console.print(f"Output: {output_file}")
    console.print()

    success = asyncio.run(
        process_text_synth(text, args.lang, output_file, args.no_play, args.workers)
    )
    sys.exit(0 if success else 1)


def ultra_command(args: Any) -> None:
    """Process ultra subcommand."""
    # Mirrors previous main.py behavior (ultra-fast path)
    if args.help_full:
        show_simple_help()
        show_troubleshooting()
        return

    if not args.text:
        show_simple_help()
        console.print("[red]ERROR:[/] No text provided")
        console.print("Try: python -m TTS_ka 'your text' --lang en")
        return

    text = get_text_input(args.text)
    if not text:
        return

    # Sanitize text (mandatory)
    text = sanitize_text(text)

    output_path = args.output or "data.mp3"

    # Auto-optimize
    if not args.no_turbo:
        optimal = get_optimal_settings(text)
        if args.chunk_seconds == 0:
            args.chunk_seconds = optimal.get("chunk_seconds", 0)
        if args.parallel == 0:
            args.parallel = optimal.get("parallel", min(4, OPTIMAL_WORKERS))

        if args.stream and args.chunk_seconds == 0:
            args.chunk_seconds = 15
            optimal["method"] = "smart"
            console.print(f"🔊 Streaming enabled - forcing chunked generation (15s chunks)")

        lang_names = {"ka": "Georgian", "ru": "Russian", "en": "English"}
        lang_name = lang_names.get(args.lang, "Unknown")
        console.print(f"OPTIMIZED MODE - {lang_name}")
        console.print(f"Strategy: {optimal.get('method')} generation, {args.parallel} workers")
        console.print(f"Processing: {len(text.split())} words, {len(text)} characters")

    if args.parallel == 0:
        args.parallel = min(4, OPTIMAL_WORKERS)

    async def run_generation():
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
                start = asyncio.get_event_loop().time()
                await generate_audio(text, args.lang, output_path)
                elapsed = asyncio.get_event_loop().time() - start
                console.print(f"⚡ Completed in {elapsed:.2f}s (direct)")

            if not args.no_play and not args.stream:
                play_audio(output_path)

        finally:
            # Attempt cleanup if available
            try:
                from .fast_audio import cleanup_http

                asyncio.run(cleanup_http())
            except Exception:
                pass

    try:
        asyncio.run(run_generation())
    except KeyboardInterrupt:
        console.print("\n⚡ Generation cancelled")


def list_voices_command(args: Any) -> None:
    """Process list-voices subcommand."""
    # Simple static list from audio VOICE_MAP may be available
    try:
        from .audio import VOICE_MAP

        for k, v in VOICE_MAP.items():
            console.print(f"{k}: {v}")
    except Exception:
        console.print("No voice information available")


def build_parser() -> argparse.ArgumentParser:
    """Build the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="tts-ka", description="TTS_ka unified CLI")
    sub = parser.add_subparsers(dest="command")

    # synth subcommand (lightweight)
    p_synth = sub.add_parser("synth", help="Synthesize text (simple mode)")
    p_synth.add_argument("text", help='Text to convert (direct text, file path, or "clipboard")')
    p_synth.add_argument("--lang", default="en", choices=["ka", "ru", "en"])
    p_synth.add_argument("--output", default=None)
    p_synth.add_argument("--no-play", action="store_true")
    p_synth.add_argument("--workers", type=int, default=4)
    p_synth.set_defaults(func=synth_command)

    # ultra subcommand (ultra-fast, advanced)
    p_ultra = sub.add_parser("ultra", help="Ultra-fast TTS with optimization")
    p_ultra.add_argument("text", nargs="?", help="Text to convert (file, clipboard, or text)")
    p_ultra.add_argument("--lang", default="en", choices=["ka", "ru", "en"])
    p_ultra.add_argument("--chunk-seconds", type=int, default=0)
    p_ultra.add_argument("--parallel", type=int, default=0)
    p_ultra.add_argument("--no-play", action="store_true")
    p_ultra.add_argument("--no-turbo", action="store_true")
    p_ultra.add_argument("--stream", action="store_true")
    p_ultra.add_argument("--no-gui", dest="show_player", action="store_false", default=True)
    p_ultra.add_argument("--help-full", action="store_true")
    p_ultra.add_argument("--output", default=None)
    p_ultra.set_defaults(func=ultra_command)

    # list-voices
    p_list = sub.add_parser("list-voices", help="List available voices")
    p_list.set_defaults(func=list_voices_command)

    return parser


def build_simple_parser() -> argparse.ArgumentParser:
    """Build a very small parser for the compact one-shot mode.

    This preserves backward compatibility: if a subcommand is provided the
    original parser is used. If no subcommand is provided the simple parser
    accepts the following flags:
      -l/--lang
      -o/--out
      -s/--speed
    and a positional text argument.
    """
    parser = argparse.ArgumentParser(
        prog="tts-ka", add_help=True, description="Simple TTS invocation"
    )
    parser.add_argument("text", help="Text to convert (or file path or 'clipboard')")
    parser.add_argument(
        "-l", "--lang", default="en", choices=["ka", "ru", "en"], help="Language code"
    )
    parser.add_argument("-o", "--out", dest="output", default=None, help="Output file path")
    parser.add_argument(
        "-s",
        "--speed",
        dest="speed",
        type=float,
        default=1.0,
        help="Initial audio speed (playback rate)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    """Main CLI entry point with subcommand routing."""
    # Decide invocation mode: subcommand-based (existing) or simple one-shot
    if argv is None:
        argv = sys.argv[1:]

    # If there are no args, show full help
    if not argv:
        parser = build_parser()
        parser.print_help()
        return

    first = argv[0]
    subcommands = {"synth", "ultra", "list-voices"}

    # Use existing subcommand behavior when explicit
    if first in subcommands:
        parser = build_parser()
        args = parser.parse_args(argv)

        if not args.command:
            parser.print_help()
            return

        try:
            args.func(args)
        except SystemExit:
            raise
        except Exception as e:
            console.print(f"[red]Error:[/] {e}")
            sys.exit(1)

        return

    # Otherwise treat invocation as simple one-shot
    simple_parser = build_simple_parser()
    try:
        args = simple_parser.parse_args(argv)
    except SystemExit:
        # argparse already printed message
        return

    # Map simple args to the existing ultra handler for convenience
    sargs = argparse.Namespace(
        text=args.text,
        lang=args.lang,
        output=args.output,
        speed=args.speed,  # currently unused by core generation; kept for API compatibility
        chunk_seconds=0,
        parallel=0,
        no_turbo=True,
        stream=False,
        show_player=True,
        no_play=False,
        help_full=False,
    )

    # Call the ultra_command path which will handle short/long decisions
    try:
        ultra_command(sargs)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
