# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev install
pip install -e ".[dev]"

# Run tests (coverage enforced at 70%)
pytest

# Single test file
pytest tests/test_chunking.py -v

# Skip slow/integration tests
pytest -m "not slow"

# Format / lint / type-check
black src/ tests/
flake8 src/ tests/
mypy src/
```

Tests use `pytest-asyncio` in auto mode — async test functions work without extra decoration.

## Architecture

### High-level flow

```
Input (text | clipboard | file)
  → sanitize (not_reading.py)       # strips code blocks, URLs, large numbers
  → route: direct or chunked        # auto-selected by ultra_fast.get_optimal_settings()
      ↓ chunked path
      split_text_into_chunks()      # WPM-based splitting
      ultra_fast_parallel_generation()  # async, semaphore-controlled
          fast_generate_audio()     # HTTP → Azure; falls back to edge-tts per chunk
          → StreamingAudioPlayer    # plays each chunk as it arrives
      fast_merge_audio_files()      # merges parts → data.mp3
```

Short texts (< ~200 words) skip chunking entirely and make a single HTTP call.

### Module map

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI parsing, input sourcing, routing |
| `ultra_fast.py` | Parallel async generation, auto-optimization |
| `fast_audio.py` | Per-chunk HTTP TTS, audio merging, playback |
| `streaming_player.py` | Queue-based background playback thread |
| `chunking.py` | WPM-based text splitting |
| `not_reading.py` | Text sanitization before generation |
| `constants.py` | Voice map, HTTP config, worker limits, WPM |
| `audio.py` | Legacy edge-tts wrapper (fallback only) |

### Non-obvious design decisions

- **Global async HTTP client** (`fast_audio.get_http_client()`): a module-level `httpx.AsyncClient` is reused across all chunks for connection pooling. Call `cleanup_http()` on shutdown.
- **Streaming starts immediately**: `StreamingAudioPlayer` dequeues and plays chunks as they finish generating — first audio within 2–3 seconds regardless of total length.
- **Layered fallbacks**: HTTP → `edge-tts` library (per chunk); `soundfile` → PyDub → FFmpeg (merging).
- **uvloop on Unix**: installed automatically in `ultra_fast.py` when available for ~2× event-loop throughput.
