"""TTS_ka: Ultra-fast multilingual text-to-speech.

Minimal public API exposing the core generation functions.
"""

from .audio import merge_audio_files as merge_audio
from .audio import play_audio
from .chunking import should_chunk_text
from .fast_audio import fast_generate_audio as generate_audio
from .main import main
from .not_reading import sanitize_text

__version__ = "1.1.0"

__all__ = [
    "main",
    "generate_audio",
    "play_audio",
    "merge_audio",
    "should_chunk_text",
    "sanitize_text",
    "__version__",
]
