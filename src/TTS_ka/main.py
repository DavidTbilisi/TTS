"""Ultra-Fast Text-to-Speech CLI tool."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

from .fast_audio import fast_generate_audio, play_audio, cleanup_http
from .streaming_player import stop_active_streaming_player
from .ultra_fast import smart_generate_long_text, get_optimal_settings, OPTIMAL_WORKERS
from .simple_help import show_simple_help, show_troubleshooting
from .constants import STREAMING_CHUNK_SECONDS
from .user_config import (
    apply_env_from_config,
    argparse_defaults_from_config,
    default_config_path,
    load_user_config,
    resolved_playback_flags,
)


def format_cli_version_info() -> str:
    """Return version line, runtime facts, and PyPI distribution metadata when available."""
    from . import __version__ as pkg_ver

    lines = [
        f"TTS_ka {pkg_ver}",
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        f"Executable: {sys.executable}",
        f"Platform: {sys.platform}",
    ]
    try:
        from importlib.metadata import PackageNotFoundError, metadata, version

        dist_ver = version("TTS_ka")
        lines.append(f"Distribution version: {dist_ver}")
        meta = metadata("TTS_ka")
        name = meta.get("Name")
        if name:
            lines.append(f"Name: {name}")
        summary = meta.get("Summary")
        if summary:
            lines.append(f"Summary: {summary}")
        author = meta.get("Author")
        if author:
            lines.append(f"Author: {author}")
        author_email = meta.get("Author-email")
        if author_email:
            lines.append(f"Author-email: {author_email}")
        license_name = meta.get("License")
        if license_name:
            lines.append(f"License: {license_name}")
        home = meta.get("Home-page")
        if home:
            lines.append(f"Home-page: {home}")
        rp = meta.get("Requires-Python")
        if rp:
            lines.append(f"Requires-Python: {rp}")
        req = meta.get_all("Requires-Dist")
        if req:
            preview = ", ".join(req[:8])
            if len(req) > 8:
                preview += f", … (+{len(req) - 8} more)"
            lines.append(f"Requires-Dist: {preview}")
    except PackageNotFoundError:
        lines.append("Distribution: not installed as a package (metadata unavailable)")
    except Exception as exc:  # pragma: no cover - defensive
        lines.append(f"Distribution metadata: unavailable ({exc})")

    return "\n".join(lines)


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


def resolve_positional_text_source(text: str) -> str:
    """Map clipboard shorthands to ``clipboard`` unless they name a real file.

    Recognizes ``cb``, ``clip``, and ``paste`` (case-insensitive). If such a
    string is an existing file path, it is left unchanged.
    """
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered not in {"cb", "clip", "paste"}:
        return text
    candidate = os.path.expanduser(stripped)
    if os.path.isfile(candidate):
        return stripped
    return "clipboard"


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
    cfg_parser = argparse.ArgumentParser(add_help=False)
    cfg_parser.add_argument("--config", metavar="PATH", default=None)
    cfg_ns, argv_rest = cfg_parser.parse_known_args()

    cfg = load_user_config(cfg_ns.config)
    apply_env_from_config(cfg)
    defs = argparse_defaults_from_config(cfg)

    dc = str(default_config_path()).replace("\\", "/")
    epilog = f"""
EXAMPLES:
  %(prog)s "Hello world" -l en                     # Quick English (-l = --lang)
  %(prog)s "გამარჯობა" --lang ka                   # Georgian with auto-optimization
  %(prog)s file.txt -l ru                          # Russian from file
  %(prog)s cb                                      # Clipboard: cb / clip / paste
  %(prog)s "text" --lang ka -o out/clip.mp3       # Custom output path
  %(prog)s --version                               # Version and metadata
  %(prog)s --check-deps                            # ffmpeg, players, Python deps

LANGUAGES: 🇬🇪 ka / ka-m (Georgian female/male) | 🇷🇺 ru | 🇬🇧 en
CONFIG: %(prog)s --config PATH.json  |  env TTS_KA_CONFIG  |  {dc}
For comprehensive help with examples: %(prog)s --help-full
"""

    parser = argparse.ArgumentParser(
        description="🚀 Ultra-Fast TTS - Georgian, Russian, English generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        dest="show_version",
        help="Print version, Python, platform, and package metadata, then exit.",
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Print ffmpeg, streaming player, and Python dependency status; exit 1 if critical deps missing.",
    )

    parser.add_argument(
        "text",
        nargs="?",
        help='Text to convert (file path, "clipboard", cb/clip/paste, or direct text)',
    )
    parser.add_argument(
        "-l",
        "--lang",
        default=defs["lang"],
        choices=["ka", "ka-m", "ru", "en"],
        help="Language: ka=Georgian female, ka-m=Georgian male, ru=Russian, en=English",
    )
    parser.add_argument(
        "-c",
        "--chunk-seconds",
        type=int,
        default=defs["chunk_seconds"],
        help="Chunk size in seconds (0=auto-detect, 20-60 recommended)",
    )
    parser.add_argument(
        "-j",
        "--parallel",
        type=int,
        default=defs["parallel"],
        help=f"Parallel workers (0=auto, 2-8 recommended, max={OPTIMAL_WORKERS})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=defs["output"],
        metavar="PATH",
        help="Output MP3 file path (default: data.mp3)",
    )
    parser.add_argument(
        "-n",
        "--no-play",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Skip automatic audio playback",
    )
    parser.add_argument(
        "--turbo",
        action="store_true",
        help="No-op: auto-optimization is already the default (kept for scripts and older docs).",
    )
    parser.add_argument(
        "--no-turbo",
        "--legacy",
        action="store_true",
        default=argparse.SUPPRESS,
        dest="no_turbo",
        help="Disable auto-optimization (legacy mode); --legacy is an alias",
    )
    parser.add_argument(
        "-s",
        "--stream",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Enable streaming playback (audio starts playing while still generating)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        default=argparse.SUPPRESS,
        dest="no_gui",
        help="Streaming: headless VLC (dummy). Default: one GUI window, playlist grows with chunks (Windows).",
    )
    parser.add_argument(
        "-H",
        "--help-full",
        action="store_true",
        help="Show comprehensive help with examples and workflows",
    )

    args = parser.parse_args(argv_rest)

    flags = resolved_playback_flags(args, defs)
    no_play = flags["no_play"]
    stream = flags["stream"]
    no_turbo = flags["no_turbo"]
    show_player = flags["show_player"]

    if args.show_version:
        print(format_cli_version_info())
        return

    if args.check_deps:
        from .deps import run_dependency_check

        sys.exit(run_dependency_check())

    if args.help_full:
        show_simple_help()
        show_troubleshooting()
        return

    if not args.text:
        show_simple_help()
        print("Error: No text provided")
        print("Try: python -m TTS_ka 'your text' -l en")
        return

    text = get_input_text(resolve_positional_text_source(args.text))
    if not text.strip():
        print("Error: No text provided")
        return
    output_path = os.path.abspath(args.output)

    chunk_seconds = args.chunk_seconds
    parallel = args.parallel

    if not no_turbo:
        optimal = get_optimal_settings(text)
        if chunk_seconds == 0:
            chunk_seconds = optimal["chunk_seconds"]
        if parallel == 0:
            parallel = optimal["parallel"]

        if stream and chunk_seconds == 0:
            chunk_seconds = STREAMING_CHUNK_SECONDS
            optimal["method"] = "smart"
            print(f"🔊 Streaming enabled - forcing chunked generation ({STREAMING_CHUNK_SECONDS}s chunks)")

        lang_names = {"ka": "Georgian", "ka-m": "Georgian (male)", "ru": "Russian", "en": "English"}
        lang_name = lang_names.get(args.lang, "Unknown")
        print(f"OPTIMIZED MODE - {lang_name}")
        print(f"Strategy: {optimal['method']} generation, {parallel} workers")
        print(f"Processing: {len(text.split())} words, {len(text)} characters")

    if parallel == 0:
        parallel = min(4, OPTIMAL_WORKERS)

    async def run_generation() -> None:
        try:
            if chunk_seconds > 0 or len(text.split()) > 200 or stream:
                await smart_generate_long_text(
                    text,
                    args.lang,
                    chunk_seconds=chunk_seconds or 30,
                    parallel=parallel,
                    output_path=output_path,
                    enable_streaming=stream,
                    show_gui=show_player,
                )
            else:
                start = time.perf_counter()
                await fast_generate_audio(text, args.lang, output_path)
                elapsed = time.perf_counter() - start
                print(f"⚡ Completed in {elapsed:.2f}s (direct)")

            if not no_play and not stream:
                play_audio(output_path)
        finally:
            try:
                await cleanup_http()
            except Exception:
                pass

    try:
        asyncio.run(run_generation())
    except KeyboardInterrupt:
        stop_active_streaming_player()
        print("\n⚡ Generation cancelled")


if __name__ == "__main__":
    main()
