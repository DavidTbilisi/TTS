"""Ultra-Fast Text-to-Speech CLI tool."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Optional

from .fast_audio import (
    fast_generate_audio,
    play_audio,
    cleanup_http,
    generate_audio_with_subs,
)
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
from . import voices as _voices
from . import prosody as _prosody
from .readers import read_file as _read_file, MissingExtraError
from . import metadata as _metadata
from . import subtitles as _subtitles
from . import completion as _completion


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


def _make_emitter(enabled: bool, stream) -> Callable[[Dict[str, Any]], None]:
    """Return a function that writes one JSON event per line to *stream*."""
    if not enabled:
        return lambda _event: None

    def emit(event: Dict[str, Any]) -> None:
        stream.write(json.dumps(event, ensure_ascii=False))
        stream.write("\n")
        stream.flush()
    return emit


async def _run_preview(text: str, voice_id: str, output_path: str) -> None:
    """Generate a short sample with *voice_id* into *output_path*."""
    try:
        await fast_generate_audio(text, "en", output_path, voice=voice_id)
    finally:
        try:
            await cleanup_http()
        except Exception:
            pass


def _resolve_output_path(raw: Optional[str], force: bool = False,
                          fallback: str = "data.mp3") -> str:
    """Normalize an output path.

    - When *raw* is None, return *fallback* unchanged (silent overwrite, used
      for both the legacy ``data.mp3`` default and config-derived paths).
    - Otherwise infer a ``.mp3`` extension if missing, create any missing parent
      directories, and refuse to overwrite an existing file unless *force* is set.

    Raises SystemExit(2) with a stderr message on overwrite conflict.
    """
    if raw is None:
        parent = os.path.dirname(fallback)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return fallback
    path = raw
    if not os.path.splitext(path)[1]:
        path = path + ".mp3"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path) and not force:
        print(
            f"Error: '{path}' already exists. Pass --force to overwrite.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return path


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
        try:
            return _read_file(text_input)
        except MissingExtraError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(2)

    return text_input


def _maybe_serve(argv: list) -> bool:
    """If argv invokes `TTS_ka serve ...`, handle it and return True."""
    if not argv or argv[0] != "serve":
        return False
    serve_parser = argparse.ArgumentParser(prog="TTS_ka serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=7777)
    serve_parser.add_argument("--token", default=None,
                              help="API token; overrides TTS_API_TOKEN env var.")
    sargs = serve_parser.parse_args(argv[1:])
    from . import server
    try:
        server.run_server(host=sargs.host, port=sargs.port, token=sargs.token)
    except server.MissingExtraError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    return True


def main() -> None:
    if _maybe_serve(sys.argv[1:]):
        return

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
  %(prog)s serve --port 7777                       # Run REST server
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
        "--player",
        default=None,
        help="Preferred streaming player name (e.g. vlc, mpv, ffplay, mplayer). "
             "Falls back to auto-detection if not found.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="ID3 title (TIT2) to embed in the output MP3.",
    )
    parser.add_argument(
        "--author",
        default=None,
        help="ID3 artist/author (TPE1) to embed in the output MP3.",
    )
    parser.add_argument(
        "--album",
        default=None,
        help="ID3 album (TALB) to embed in the output MP3.",
    )
    parser.add_argument(
        "--cover",
        default=None,
        help="Path to a JPEG/PNG to embed as the cover image (APIC).",
    )
    parser.add_argument(
        "--chapters",
        default=None,
        help="Path to a JSON file with [{title, start_ms, end_ms}, ...] chapter entries.",
    )
    parser.add_argument(
        "--srt",
        action="store_true",
        help="Write an SRT subtitle file next to the output MP3.",
    )
    parser.add_argument(
        "--vtt",
        action="store_true",
        help="Write a WebVTT subtitle file next to the output MP3.",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="Specific voice ID (e.g. en-US-JennyNeural). "
             "If given, --lang is inferred from the voice locale.",
    )
    parser.add_argument(
        "--rate",
        default=defs.get("rate"),
        help="Speech rate as a signed percentage (e.g. +30%%, -20%%). "
             "Config key: rate.",
    )
    parser.add_argument(
        "--pitch",
        default=defs.get("pitch"),
        help="Pitch shift in Hz or %% (e.g. +5Hz, -2Hz, +10%%). Config key: pitch.",
    )
    parser.add_argument(
        "--volume",
        default=defs.get("volume"),
        help="Volume as a signed percentage (e.g. +10%%, -25%%). Config key: volume.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available voices and exit. Combine with --lang to filter.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON events on stdout; suppress decorative output.",
    )
    parser.add_argument(
        "--preview-voice",
        default=None,
        metavar="VOICE_ID",
        help="Generate and play a short sample with the given voice, then exit.",
    )
    parser.add_argument(
        "-H",
        "--help-full",
        action="store_true",
        help="Show comprehensive help with examples and workflows",
    )
    parser.add_argument(
        "--print-completion",
        choices=["bash", "zsh", "fish"],
        default=None,
        help="Print a shell completion script and exit.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Read stdin incrementally and speak each sentence as it lands. "
             "For piping AI/LLM output (e.g. `claude … | tts-ka --live -l en`).",
    )
    parser.add_argument(
        "--live-idle-ms",
        type=int,
        default=800,
        help="In --live mode, flush a partial sentence after this many ms of stdin silence (default 800).",
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

    if args.print_completion:
        sys.stdout.write(_completion.render(args.print_completion))
        return

    if args.list_voices:
        voices = (_voices.voices_for_lang(args.lang)
                  if args.lang in {"ka", "ru", "en"}
                  else _voices.all_voices())
        if "--lang" not in sys.argv[1:] and not any(a.startswith("--lang=") for a in sys.argv[1:]):
            voices = _voices.all_voices()
        print(_voices.format_table(voices))
        return

    if args.preview_voice:
        voice = _voices.get_voice(args.preview_voice)
        if voice is None:
            print(
                f"Error: unknown voice {args.preview_voice!r}. "
                f"Use --list-voices to see available voices.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        phrase = _voices.PREVIEW_PHRASE.get(voice.lang, _voices.PREVIEW_PHRASE["en"])
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            preview_path = tmp.name
        try:
            asyncio.run(_run_preview(phrase, voice.id, preview_path))
            play_audio(preview_path)
        finally:
            try:
                os.remove(preview_path)
            except OSError:
                pass
        return

    # Reconcile --voice and --lang: voice locale wins, with explicit conflict error.
    if args.voice:
        inferred_lang = _voices.lang_for_voice(args.voice)
        if inferred_lang is None:
            print(
                f"Error: unknown voice {args.voice!r}. "
                f"Use --list-voices to see available voices.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        explicit_lang = (
            "--lang" in sys.argv[1:]
            or any(a.startswith("--lang=") for a in sys.argv[1:])
        )
        if explicit_lang and args.lang != inferred_lang:
            print(
                f"Error: --voice {args.voice!r} is {inferred_lang!r}, "
                f"but --lang {args.lang!r} was given.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        args.lang = inferred_lang

    # JSON mode: redirect decorative stdout to stderr, save real stdout for events.
    json_stream = sys.stdout
    if args.json:
        sys.stdout = sys.stderr
    emit = _make_emitter(args.json, json_stream)

    # --live: incremental stdin → per-sentence speak. Branches before the
    # blocking sys.stdin.read() below so we read line-by-line instead.
    if args.live:
        prosody_opts = _prosody.build_opts(args.rate, args.pitch, args.volume)
        from .live_stream import live_loop as _live_loop
        try:
            asyncio.run(_live_loop(
                lang=args.lang,
                voice=args.voice,
                prosody=prosody_opts,
                idle_flush_ms=args.live_idle_ms,
                show_player_gui=show_player,
            ))
        except KeyboardInterrupt:
            stop_active_streaming_player()
            emit({"event": "error", "message": "cancelled"})
        return

    # Stdin handling: if no text arg and stdin is piped, or text == "-", read stdin.
    if args.text == "-" or (not args.text and not sys.stdin.isatty()):
        try:
            args.text = sys.stdin.read()
        except (OSError, ValueError):
            args.text = ""

    if not args.text or not args.text.strip():
        if not args.json:
            show_simple_help()
            print("Error: No text provided")
            print("Try: python -m TTS_ka 'your text' --lang en")
        else:
            emit({"event": "error", "message": "no text provided"})
        return

    text = (args.text if args.text and "\n" in args.text and not os.path.exists(args.text)
            else get_input_text(resolve_positional_text_source(args.text)))
    if not text or not text.strip():
        if args.json:
            emit({"event": "error", "message": "empty input"})
        else:
            print("Error: No text provided")
        return

    # Overwrite protection applies only to explicit CLI --output / -o, not config defaults.
    output_explicit = any(
        a == "-o" or a == "--output" or a.startswith("--output=") or a.startswith("-o=")
        for a in sys.argv[1:]
    )
    output_path = _resolve_output_path(
        args.output if output_explicit else None,
        force=args.force,
        fallback=os.path.abspath(args.output) if args.output else "data.mp3",
    )

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
            print(f"[stream] Streaming enabled - forcing chunked generation ({STREAMING_CHUNK_SECONDS}s chunks)")

        lang_names = {"ka": "Georgian", "ka-m": "Georgian (male)", "ru": "Russian", "en": "English"}
        lang_name = lang_names.get(args.lang, "Unknown")
        print(f"OPTIMIZED MODE - {lang_name}")
        print(f"Strategy: {optimal['method']} generation, {parallel} workers")
        print(f"Processing: {len(text.split())} words, {len(text)} characters")

    if parallel == 0:
        parallel = min(4, OPTIMAL_WORKERS)

    prosody_opts = _prosody.build_opts(args.rate, args.pitch, args.volume)
    emit({"event": "start", "words": len(text.split()), "lang": args.lang})

    async def run_generation() -> None:
        run_start = time.perf_counter()
        want_subs = args.srt or args.vtt
        try:
            if want_subs:
                # Subtitle export needs WordBoundary events; route through edge-tts.
                start = time.perf_counter()
                events = await generate_audio_with_subs(
                    text, args.lang, output_path,
                    voice=args.voice, prosody=prosody_opts,
                )
                elapsed = time.perf_counter() - start
                print(f"⚡ Completed in {elapsed:.2f}s (subtitled)")
                base, _ = os.path.splitext(output_path)
                if args.srt:
                    _subtitles.write_subs(events, base + ".srt", "srt")
                if args.vtt:
                    _subtitles.write_subs(events, base + ".vtt", "vtt")
            elif chunk_seconds > 0 or len(text.split()) > 200 or stream:
                await smart_generate_long_text(
                    text,
                    args.lang,
                    chunk_seconds=chunk_seconds or 30,
                    parallel=parallel,
                    output_path=output_path,
                    enable_streaming=stream,
                    show_gui=show_player,
                    preferred_player=args.player,
                    voice=args.voice,
                    prosody=prosody_opts,
                )
            else:
                start = time.perf_counter()
                await fast_generate_audio(text, args.lang, output_path,
                                           voice=args.voice, prosody=prosody_opts)
                elapsed = time.perf_counter() - start
                print(f"⚡ Completed in {elapsed:.2f}s (direct)")

            # Apply ID3 tags + chapters if any were requested
            chapters = None
            if args.chapters:
                try:
                    chapters = _metadata.load_chapters(args.chapters)
                except (OSError, ValueError) as exc:
                    print(f"Error: --chapters {args.chapters!r}: {exc}",
                          file=sys.stderr)
                    raise SystemExit(2)
            meta_spec = _metadata.MetadataSpec(
                title=args.title,
                author=args.author,
                album=args.album,
                cover_path=args.cover,
                chapters=chapters,
            )
            if not meta_spec.is_empty():
                try:
                    _metadata.apply(output_path, meta_spec)
                except _metadata.MissingExtraError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    raise SystemExit(2)

            if not no_play and not stream:
                play_audio(output_path)
            emit({
                "event": "done",
                "output": output_path,
                "seconds": round(time.perf_counter() - run_start, 3),
            })
        except Exception as exc:
            emit({"event": "error", "message": str(exc)})
            raise
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
        emit({"event": "error", "message": "cancelled"})


if __name__ == "__main__":
    main()
