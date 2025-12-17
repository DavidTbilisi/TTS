"""TTS_ka - Ultra-Fast Text-to-Speech with Streaming Playback."""

from .audio import generate_audio, play_audio, merge_audio_files
from .fast_audio import fast_generate_audio, fast_merge_audio_files
from .ultra_fast import smart_generate_long_text, ultra_fast_parallel_generation
from .streaming_player import StreamingAudioPlayer
from .chunking import split_text_into_chunks, should_chunk_text
from .main import main

__version__ = "1.1.0"
__all__ = [
    'generate_audio',
    'play_audio',
    'merge_audio_files',
    'fast_generate_audio',
    'fast_merge_audio_files',
    'smart_generate_long_text',
    'ultra_fast_parallel_generation',
    'StreamingAudioPlayer',
    'split_text_into_chunks',
    'should_chunk_text',
    'main',
]
