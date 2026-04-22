# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev install
pip install -e ".[dev]"

# Run tests (coverage enforced in pytest / pyproject config)
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

Tests use `pytest-asyncio` in auto mode — install the `[test]` or `[dev]` extra so async tests are not skipped.

## Architecture

### High-level flow

```
Input (text | clipboard | file)
  → sanitize (not_reading.py)       # strips code blocks, URLs, large numbers
  → route: direct or chunked        # auto-selected by ultra_fast.get_optimal_settings()
      ↓ chunked path
      split_text_into_chunks()      # WPM-based splitting
      ultra_fast_parallel_generation()  # async, semaphore-controlled
          fast_generate_audio()     # Bing HTTP (optional) → edge-tts per chunk
          → StreamingAudioPlayer    # plays each chunk as it arrives (optional)
      fast_merge_audio_files()      # merges parts → output MP3
```

Short texts (< ~200 words, non-streaming) skip chunking and call `fast_generate_audio` once.

Environment variables (see `fast_audio.py`, `readme.md`):

- `TTS_KA_SKIP_HTTP=1` — skip unofficial Bing HTTP TTS; use edge-tts only.
- `TTS_KA_VERBOSE=1` — log when falling back from HTTP to edge-tts.

### Module map

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI parsing, input sourcing, routing; `-V` / `--version` → `format_cli_version_info()` (runtime + `importlib.metadata` when installed) |
| `ultra_fast.py` | Parallel async generation, auto-optimization |
| `fast_audio.py` | Per-chunk TTS (HTTP + edge-tts), merge, playback helpers |
| `streaming_player.py` | Queue-based background playback thread |
| `chunking.py` | WPM-based text splitting |
| `not_reading.py` | Text sanitization before generation |
| `constants.py` | `VOICE_MAP` (`ka`, `ka-m`, `ru`, `en`, `en-US`), `SSML_LANG_MAP`, HTTP/stream limits |

### Non-obvious design decisions

- **Global async HTTP client** (`fast_audio.get_http_client()`): a module-level `httpx.AsyncClient` is reused across all chunks for connection pooling. Call `cleanup_http()` on shutdown.
- **Streaming**: `StreamingAudioPlayer` plays chunks as they finish; Windows prefers VLC when available, else per-chunk `os.startfile`.
- **Layered fallbacks**: optional Bing HTTP POST → `edge-tts`; merge: `soundfile` → PyDub → FFmpeg.
- **uvloop on Unix**: used in `ultra_fast.py` when available for faster event-loop I/O.
- **Georgian voices**: `--lang ka` (Eka), `--lang ka-m` (Giorgi); SSML `xml:lang` uses `ka-GE` for those codes on the HTTP path.
