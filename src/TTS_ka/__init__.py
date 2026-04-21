"""TTS_ka - Ultra-Fast Text-to-Speech with Streaming Playback."""

from .fast_audio import fast_generate_audio, fast_merge_audio_files, play_audio
from .ultra_fast import smart_generate_long_text, ultra_fast_parallel_generation
from .streaming_player import StreamingAudioPlayer
from .chunking import split_text_into_chunks, should_chunk_text
from .main import main

__version__ = "1.4.4"
__all__ = [
    'fast_generate_audio',
    'fast_merge_audio_files',
    'play_audio',
    'smart_generate_long_text',
    'ultra_fast_parallel_generation',
    'StreamingAudioPlayer',
    'split_text_into_chunks',
    'should_chunk_text',
    'main',
]
