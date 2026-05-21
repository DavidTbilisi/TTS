# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev install (editable + test/lint tools)
pip install -e ".[dev]"

# Run tests (coverage enforced at 80% by pytest.ini)
pytest

# Single test file / single test
pytest tests/test_chunking.py -v
pytest tests/test_chunking.py::test_split_into_chunks -v

# Skip slow/integration tests
pytest -m "not slow"

# Format / lint / type-check
black src/ tests/
flake8 src/ tests/
mypy src/

# Run the CLI (two equivalent entry points)
python -m TTS_ka "Hello" --lang en
TTS_ka "Hello" --lang en          # installed via [project.scripts]
```

Tests use `pytest-asyncio` in auto mode — async test functions need no explicit decorator. Note that **`pytest.ini` and `pyproject.toml` both define pytest config**; `pytest.ini` wins, so its `--cov-fail-under=80` is the effective threshold (pyproject.toml's `70` is stale).

## Architecture

### High-level flow

```
Input (text | clipboard | file)
  → sanitize (not_reading.py)       # strips code blocks, URLs, 7+ digit numbers
  → route: direct or chunked        # auto-selected by ultra_fast.get_optimal_settings()
      ↓ chunked path
      split_text_into_chunks()      # WPM-based splitting (constants.WPM = 160)
      ultra_fast_parallel_generation()  # async, asyncio.Semaphore-controlled
          fast_generate_audio()     # HTTP → Azure; falls back to edge-tts per chunk
          → StreamingAudioPlayer    # plays each chunk as it arrives (optional)
      fast_merge_audio_files()      # merges parts → data.mp3
```

Short texts (< ~200 words) skip chunking entirely and make a single HTTP call (unless `--stream` is set, which forces chunked mode).

### Module map

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI parsing, input sourcing, routing. Owns stdlib clipboard reader (`_read_clipboard`). |
| `ultra_fast.py` | Parallel async generation, auto-optimization (`get_optimal_settings`), `smart_generate_long_text` orchestrator. |
| `fast_audio.py` | Per-chunk HTTP TTS, audio merging, playback. Protocol-based: `AudioGenerator`, `AudioMerger`, `MergerFactory`. |
| `streaming_player.py` | Queue-based background playback thread. `PlayerDetector` finds vlc/mpv/ffplay/mplayer. |
| `chunking.py` | WPM-based text splitting (`split_text_into_chunks`). |
| `not_reading.py` | Text sanitization pipeline (`TextProcessingPipeline` + composable filters). |
| `rich_progress.py` | tqdm-backed progress display with chunks/sec, words/sec, ETA. |
| `simple_help.py` | ASCII-only help/troubleshooting text for Windows consoles. |
| `constants.py` | Voice map, HTTP config, worker limits, WPM, streaming chunk size. |

### Non-obvious design decisions

- **Global async HTTP client** (`fast_audio.get_http_client()`): a module-level `httpx.AsyncClient` is reused across all chunks for connection pooling. Always call `await cleanup_http()` on shutdown (the CLI does this in a `finally`).
- **Streaming starts immediately**: `StreamingAudioPlayer` dequeues and plays chunks as they finish generating — first audio within 2–3 seconds. The **first chunk writes directly to `output_path`** (not a `.part_0.mp3`) so playback can start without copying; remaining chunks merge into it at the end.
- **VLC required for `--stream` (default GUI mode)**: `smart_generate_long_text` checks `PlayerDetector.find()` and raises `SystemExit(1)` if VLC isn't found. Pass `--no-gui` to allow non-VLC players.
- **Layered fallbacks**:
  - Generation: `HttpAudioGenerator` (direct Azure SSML) → `EdgeTTSGenerator` (edge-tts lib).
  - Merging: `SoundFileMerger` (soundfile + numpy) → `PydubMerger` → `FFmpegMerger` (subprocess). `MergerFactory.create()` picks at runtime; `fast_merge_audio_files` tries all in order on exception.
- **Clipboard reading is stdlib-only**: `_read_clipboard()` tries tkinter, then platform fallbacks (`Get-Clipboard` on Windows, `pbpaste` on macOS). `pyperclip` was removed — don't reintroduce it.
- **uvloop on Unix**: installed automatically in `ultra_fast.py`/`fast_audio.py` when available for ~2× event-loop throughput. Skipped on `win32`.
- **Crash-leftover cleanup**: `smart_generate_long_text` deletes stale `.part_*.mp3` files at startup. If you add new temp-file patterns, update that glob.
- **Sanitization filters preserve order**: in `not_reading.py`, code blocks are filtered *before* inline code (otherwise the `` ` `` chars inside a fenced block would match the inline regex). Keep this order when adding new filters.
