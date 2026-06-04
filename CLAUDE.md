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

# Release: bump version, commit, tag vX.Y.Z, push (then publish GitHub Release → PyPI)
python scripts/release.py patch   # or minor | major
python scripts/release.py patch --dry-run

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
| `live_stream.py` | `--live` mode: read stdin incrementally, speak each sentence as it lands (for piping LLM output) |
| `mcp_server.py` | MCP server (`TTS_ka-mcp`): exposes `speak` / `stream_open` / `stream_append` / `stream_close` / `stop` / `list_voices` over stdio for AI clients |
| `chunking.py` | WPM-based text splitting |
| `not_reading.py` | Text sanitization before generation |
| `constants.py` | `VOICE_MAP` (`ka`, `ka-m`, `ru`, `en`, `en-US`), `SSML_LANG_MAP`, HTTP/stream limits |
| `study_session.py` | Pure-logic timing model for study mode: binary-search word lookup over `List[WordEvent]`, chunk boundaries, WPM. No UI/audio deps. |
| `study_player.py` | Tk + pygame synchronized RSVP+audio reader (study mode); excluded from coverage like `gui.py`. Launched from `main.py --study`. Requires the `[study]` extra. |
| `quiz.py` | `QuizProvider` Protocol + `RuleBasedProvider` (zero-dep; `_generate_for_chunk` is intentionally a TODO slot) + `LLMQuizProvider` stub for future swap. |
| `session_log.py` | Append-only JSONL training log at `~/.tts_ka_study.jsonl` (override via `TTS_KA_STUDY_LOG`). `SessionRecord` dataclass with `wpm` property. |
| `extras/autohotkey/` | Windows: `TTS_ka_hotkeys.ahk` (hotkeys + Apps key / Ctrl+Alt+RButton language menu), `Install-TTS_ka-Hotkeys.ps1` (Startup) |
| `extras/windows/context_menu/` | `Install-TTS_ka-ContextMenu.ps1` — nested “Read with TTS_ka” on Explorer/Desktop background (clipboard) |

### Non-obvious design decisions

- **Global async HTTP client** (`fast_audio.get_http_client()`): a module-level `httpx.AsyncClient` is reused across all chunks for connection pooling. Call `cleanup_http()` on shutdown.
- **Streaming**: `StreamingAudioPlayer` plays chunks as they finish; Windows prefers VLC when available, else per-chunk `os.startfile`.
- **Layered fallbacks**: optional Bing HTTP POST → `edge-tts`; merge: `soundfile` → PyDub → FFmpeg.
- **uvloop on Unix**: used in `ultra_fast.py` when available for faster event-loop I/O.
- **Georgian voices**: `--lang ka` (Eka), `--lang ka-m` (Giorgi); SSML `xml:lang` uses `ka-GE` for those codes on the HTTP path.
- **`--live` AI-streaming mode**: `tts-ka --live -l en` reads stdin line-by-line, accumulates in `SentenceBuffer`, flushes on `[.!?]+\s`, paragraph break, or idle (default 800 ms via `--live-idle-ms`). Code fences (` ``` `) are held open until closed so `not_reading.replace_not_readable` can collapse them; per-sentence MP3s feed into `StreamingAudioPlayer` with `chunk_index` ordering. Use case: `claude --print | tts-ka --live`.
- **MCP server (`TTS_ka-mcp`)**: stdio JSON-RPC server (`pip install -e ".[mcp]"`). Tools: `speak`, `stream_open`, `stream_append`, `stream_close`, `session_status`, `list_sessions`, `stop`, `list_voices`. `_LiveSession` tracks two counters: `_idx` (output-file numbering, ticks inside `_speak`) and `_queued` (status-visible, ticks when `feed` extracts a sentence — so an agent can see backed-up synths via `synths_pending = _queued - done_tasks`). `build_server(sessions=dict)` factory lets tests inject a session dict for inspection. Configure in Claude Code: `{"mcpServers": {"tts-ka": {"command": "TTS_ka-mcp"}}}`.
- **MCP stdout duality** (`_run_with_preserved_stdout`): naively swapping `sys.stdout = sys.stderr` to silence library prints ALSO kills MCP framing because `mcp.server.stdio` reads `sys.stdout.buffer` at handshake time. The fix is fd-level: `os.dup(1)` saves the original stdout fd, `os.dup2(2, 1)` redirects Python-level stdout (and any subprocess inheriting fd 1) to stderr, and the saved fd is wrapped and handed to `stdio_server(stdout=...)`. Without this, the E2E test hangs on `session.initialize()` because the server's reply lands on stderr.
- **Study mode (`--study`)**: synchronized RSVP word-flash + audio playback over the same text. Reuses `fast_audio.generate_audio_with_subs` for the per-word `WordEvent` timing list; `study_session.StudySession` is the pure-logic model (binary-search lookup via `bisect_right` on a pre-extracted `_starts` array, O(log n) inside the 30 Hz sync loop). The Tk player polls `pygame.mixer.music.get_pos()` every 33 ms and updates a centred big-word label plus faded peripheral context. Quiz generation lives behind a `QuizProvider` Protocol so a future LLM backend can swap in without touching the player; the default `RuleBasedProvider._generate_for_chunk` is a TODO(human) slot — wrap of the slot raises `NotImplementedError`, intentionally, so the player surfaces it instead of silently returning empty results. Session log is plain JSONL at `~/.tts_ka_study.jsonl`.
