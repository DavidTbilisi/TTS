"""Shared constants for TTS_ka."""

# Supported languages mapped to their Microsoft Neural voice names
VOICE_MAP = {
    'ka': 'ka-GE-EkaNeural',       # Georgian — female neural
    'ka-m': 'ka-GE-GiorgiNeural',  # Georgian — male neural
    'ru': 'ru-RU-SvetlanaNeural',  # Russian — high-quality female voice
    'en': 'en-GB-SoniaNeural',     # English — British neural voice
    'en-US': 'en-US-SteffanNeural',
}

# Audio generation
STREAMING_CHUNK_SECONDS = 15    # Default chunk size when streaming is enabled
STREAMING_FIRST_CHUNK_SECONDS = 6  # Smaller first chunk when streaming → lower time-to-first-audio
WPM = 160                       # Estimated words-per-minute for chunk sizing
MAX_PARALLEL_WORKERS = 32       # Upper cap on concurrent generation workers

# Playback
PLAYBACK_JOIN_TIMEOUT = 300     # Seconds to wait for playback thread to finish
