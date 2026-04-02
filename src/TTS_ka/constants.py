"""Shared constants for TTS_ka."""

# Supported languages mapped to their Microsoft Neural voice names
VOICE_MAP = {
    'ka': 'ka-GE-EkaNeural',       # Georgian — premium female voice
    'ru': 'ru-RU-SvetlanaNeural',  # Russian — high-quality female voice
    'en': 'en-GB-SoniaNeural',     # English — British neural voice
    'en-US': 'en-US-SteffanNeural',
}

# HTTP client configuration
HTTP_TIMEOUT_TOTAL = 30.0
HTTP_TIMEOUT_CONNECT = 10.0
HTTP_MAX_KEEPALIVE = 20
HTTP_MAX_CONNECTIONS = 100

# Audio generation
STREAMING_CHUNK_SECONDS = 15    # Default chunk size when streaming is enabled
WPM = 160                       # Estimated words-per-minute for chunk sizing
MAX_PARALLEL_WORKERS = 32       # Upper cap on concurrent generation workers

# Playback
PLAYBACK_JOIN_TIMEOUT = 300     # Seconds to wait for playback thread to finish
