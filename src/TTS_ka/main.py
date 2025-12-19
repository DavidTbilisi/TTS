"""Compatibility wrapper exposing `main` that delegates to the unified CLI (ultra mode).

Also re-exports helper functions used by tests for backwards compatibility.
"""

import sys
from argparse import ArgumentParser
from typing import Optional

from .cli import main as cli_main
from .fast_audio import fast_generate_audio as _fast_generate_audio
from .fast_audio import generate_audio_ultra_fast as _generate_audio_ultra_fast
from .ultra_fast import determine_strategy as _determine_strategy
from .ultra_fast import generate_tts_turbo as _generate_tts_turbo
from .ultra_fast import smart_generate_long_text as _smart_generate_long_text


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split()) if text else 0


def validate_language(lang: str) -> bool:
    """Validate if language code is supported."""
    return lang in ("ka", "ru", "en")


# Re-exported helpers for tests (stable compatibility surface)
generate_tts_turbo = _generate_tts_turbo
determine_strategy = _determine_strategy
generate_audio_ultra_fast = _generate_audio_ultra_fast
fast_generate_audio = _fast_generate_audio
smart_generate_long_text = _smart_generate_long_text


def create_parser() -> ArgumentParser:
    """Create a simple ArgumentParser compatible with older CLI tests.

    This parser intentionally uses the name `text_input` for the positional
    argument because many tests expect that parameter name in the parser
    signature and parsing behavior.
    """
    parser = ArgumentParser(prog="tts-ka", description="Ultra-Fast TTS")
    parser.add_argument(
        "text_input", help='Text to convert (direct text, file path, or "clipboard")'
    )
    parser.add_argument("--lang", default="en", choices=["ka", "ru", "en"])
    parser.add_argument("--turbo", action="store_true", default=False)
    parser.add_argument("--no-play", action="store_true", default=False)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--chunk-seconds", type=int, default=0)
    parser.add_argument("--help-full", action="store_true", default=False)
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    """Forward to the unified CLI implementation.

    If no subcommand is provided, prepend `ultra` to preserve historic
    behavior where `main()` expected a text argument directly.
    """
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 0 or argv[0] not in ("synth", "ultra", "list-voices"):
        argv = ["ultra"] + list(argv)

    return cli_main(argv)


if __name__ == "__main__":
    main()
