# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dev install
pip install -e ".[dev]"

# Run tests (coverage gate: fail_under in pyproject.toml [tool.coverage.report])
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
          fast_generate_audio()     # edge-tts per chunk (retries transient 403/429)
          → StreamingAudioPlayer    # plays each chunk as it arrives (optional)
      fast_merge_audio_files()      # merges parts → output MP3
```

Short texts (< ~200 words, non-streaming) skip chunking and call `fast_generate_audio` once.

Environment variables (see `readme.md`):

- `TTS_KA_CONFIG` — alternate JSON config path (default `~/.tts_config.json`, loaded by `user_config.py`).
- `TTS_KA_VLC_RC=0` — Windows: disable the single-VLC TCP remote-control playlist.
- `TTS_API_TOKEN` — bearer token required by `tts-ka serve`.

### Module map

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI parsing, input sourcing, routing; `-V` / `--version` → `format_cli_version_info()` (runtime + `importlib.metadata` when installed) |
| `ultra_fast.py` | Parallel async generation, auto-optimization |
| `fast_audio.py` | Per-chunk TTS (edge-tts), merge back-ends, playback helpers |
| `chunk_cache.py` | Content-addressed cache of synthesized chunks (+ word-timing sidecars): key = sha256(version, format, sanitized text, voice, rate, pitch, volume); atomic writes, LRU prune to `TTS_KA_CACHE_MAX_MB` |
| `streaming_player.py` | `PlayerDetector` + queue-based background playback thread |
| `mpv_ipc.py` | `MpvIpc`: headless mpv over its JSON-IPC Unix socket (`--idle`, `loadfile append-play`, `end-file` / `idle-active` → `wait_done`, pause/resume/skip/stop). POSIX only |
| `stream_keys.py` | `KeyControls`: single-key playback control while the CLI streams (space pause, n next, +/- speed, q = SIGINT). Reads `/dev/tty` in cbreak mode, restores it on close; inactive on Windows, without a terminal, or in a background process group (tcsetattr there would SIGTTOU) |
| `live_stream.py` | `--live` mode: read stdin incrementally, speak each sentence as it lands (for piping LLM output) |
| `mcp_server.py` | MCP server (`tts-ka-mcp`): `speak`, `stream_open` / `stream_append` / `stream_close`, `session_status`, `list_sessions`, `pause` / `resume` / `skip`, `stop`, `list_voices` over stdio |
| `server.py` | `tts-ka serve` FastAPI REST server (`/voices`, `/synthesize`; `[server]` extra) |
| `gui.py` | tkinter GUI (`tts-ka-gui`): Setup / Speak / Config / Hotkeys / Windows shell (Windows only) / About tabs. `[gui]` extra → sv-ttk theme (`apply_gui_theme`, `TTS_KA_GUI_THEME=light\|dark\|system\|classic`); `apply_unicode_ui_fonts` re-targets the SunValley fonts to a Georgian-capable family and leaves `TkFixedFont` monospace |
| `chunking.py` | WPM-based text splitting |
| `not_reading.py` | Text sanitization before generation |
| `readers/` | File → text by extension (txt/md/html/pdf/epub/docx; heavy deps via `[readers]`). `read_file(path, pages=)` / `--pages 20-24,30-`: 1-based PDF page selection (`pdf.parse_page_spec`); out-of-range, malformed or non-PDF raises `PageRangeError` → exit 2. PDFs go through poppler `pdftotext` when installed (pages split on `\f`, count from `pdfinfo`), else `pypdf`: `pypdf` turns soft hyphens into spaces ("dif fer ent"), `pdftotext` keeps U+00AD plus a stray space after the next glyph, which `_repair_soft_hyphens` rejoins (not after a hyphen/dash: `big-O`, `rm -f`) |
| `voices.py` / `prosody.py` | Voice catalog (`--list-voices`, `--voice`); `--rate/--pitch/--volume` parsing |
| `metadata.py` / `subtitles.py` | ID3 tags + chapters (`[metadata]`); SRT/VTT from edge-tts WordBoundary events |
| `user_config.py` | JSON config loading, CLI defaults, `LANG_CODES` |
| `deps.py` | `--doctor` checks; shared `MissingExtraError` for optional extras |
| `rich_progress.py` | rich progress bar + `cprint` (stderr, so `--json` stdout stays clean) |
| `completion.py` / `simple_help.py` | `--print-completion` scripts; `--help-full` text |
| `native_hotkeys.py` / `windows_shell.py` | pynput global hotkeys (`[hotkeys]`); Explorer context-menu installer wrapper |
| `constants.py` | `VOICE_MAP` (`ka`, `ka-m`, `ru`, `en`, `en-US`) — the single source of supported languages — plus stream/worker limits |
| `study_session.py` | Pure-logic timing model for study mode: binary-search word lookup over `List[WordEvent]`, chunk boundaries, WPM. No UI/audio deps. |
| `study_player.py` | Tk + pygame synchronized RSVP+audio reader (study mode); excluded from coverage like `gui.py`. Launched from `main.py --study`. Requires the `[study]` extra. |
| `quiz.py` | `QuizProvider` Protocol + `RuleBasedProvider` (zero-dep; `_generate_for_chunk` is intentionally a TODO slot) + `LLMQuizProvider` stub for future swap. |
| `session_log.py` | Append-only JSONL training log at `~/.tts_ka_study.jsonl` (override via `TTS_KA_STUDY_LOG`). `SessionRecord` dataclass with `wpm` property. |
| `extras/autohotkey/` | Windows: `TTS_ka_hotkeys.ahk` (hotkeys + Apps key / Ctrl+Alt+RButton language menu), `Install-TTS_ka-Hotkeys.ps1` (Startup) |
| `extras/windows/context_menu/` | `Install-TTS_ka-ContextMenu.ps1` — nested “Read with TTS_ka” on Explorer/Desktop background (clipboard) |

### Non-obvious design decisions

- **Streaming**: `StreamingAudioPlayer` plays chunks as they finish. `PlayerDetector` order is mpv → VLC → ffplay → mplayer (`--player` / `preferred=` overrides). Headless mpv on POSIX is driven over JSON IPC (`mpv_ipc.MpvIpc`, `TTS_KA_MPV_IPC=0` disables): a stdin-playlist mpv without `--keep-open` exits at the first synthesis gap, so later chunks were lost. GUI mpv keeps the stdin playlist with `--keep-open` — user `mpv` wrappers (e.g. a shim that strips the window when it sees `--playlist=-`) key on that argv, so don't move GUI mode to IPC. On Windows VLC gets one instance driven over TCP RC, else per-chunk `os.startfile`. Ordering: chunks are released strictly by index, so every index must either `add_chunk` or `skip_index` (empty/failed sentence) — a missing index stalls everything after it until `finish_generation()`. Delete chunk files only after `wait_until_released()`; `stop()` drains the queue, kills the player (terminate → kill) and ignores later `add_chunk`. Speed: `change_speed(delta)` sets mpv's `speed` property over IPC (clamped `MIN_SPEED`..`MAX_SPEED`); like pause/skip it returns falsy when the player isn't IPC-driven. CLI keys (`stream_keys.KeyControls`) are opt-in via `key_controls=` on `smart_generate_long_text` / `live_loop` — only `main` passes it, so the GUI and MCP never grab the terminal; `--live` turns them off when stdin is a tty (it would steal typed text). All started players are tracked in a set; `stop_all_streaming_players()` (alias `stop_active_streaming_player`) stops them on Ctrl+C.
- **Merging**: edge-tts emits headerless 48 kbps CBR MP3, so `.mp3` output from MP3 parts is joined by `ConcatMp3Merger` (byte concat, later parts' ID3 stripped, atomic `os.replace`) — no re-encode, no deps. Other outputs fall back to `soundfile` → PyDub → FFmpeg. Every merger raises `MergeFailed` on a missing/empty/unreadable part or a non-zero ffmpeg exit; none may "copy the first part" or skip a part. `fast_merge_audio_files` refuses an `output_path` that is also a part.
- **Run dirs**: `smart_generate_long_text` writes `.part_NNNN.mp3` into `tempfile.mkdtemp(prefix="tts-ka-run-")`, never the CWD or `output_path`, merges, waits for the player, then `rmtree`s it (also on any exception). GUI streaming keeps it because mpv opens queued files lazily; `_sweep_stale_run_dirs()` removes `tts-ka-run-*` older than 12 h at the next run. Tests get a per-test `tempfile.tempdir` from `conftest._isolated_tempdir`.
- **Retries and concurrency**: `fast_audio._retry_edge` retries what `_is_retryable` accepts (timeouts, `ConnectionError`, aiohttp errors, HTTP 403/408/429/5xx, `NoAudioReceived` at most once) with jittered exponential backoff and `Retry-After`; `_edge_tts_transient` (403/429 text) only decides the `pip install -U edge-tts` hint. `MAX_PARALLEL_WORKERS = 6` is a fixed rate-limit cap (CPU count is irrelevant for network-bound synthesis); `-j` above it is clamped with a note.
- **Chunk cache**: `EdgeTTSGenerator.generate` (and `generate_audio_with_subs`, which also needs the `.words.json` sidecar for a hit) serve cache hits and store every success — failures and empty files are never stored. Because every caller goes through it, CLI, `--live`, MCP, REST and study mode all share it. Resume is a consequence: a failed run fails fast, but its finished chunks are cached. Tests run with `TTS_KA_CACHE=0` (`conftest._no_chunk_cache`) so synthesis mocks are never served from a real cache; cache tests opt in with `TTS_KA_CACHE=1` + a tmp `TTS_KA_CACHE_DIR` and call `chunk_cache.configure()` to reset the singleton.
- **Synthesis is edge-tts only**: the unofficial Bing HTTP shortcut was removed (it returned 401/403). edge-tts < 7.3.1 is also rejected with 403, hence the floor in `pyproject.toml`.
- **Failure contract**: `fast_generate_audio` returns `False` (it does not raise) when synthesis fails. Every caller must turn that into `GenerationFailed` via `fast_audio.generation_failed()`, which pulls the reason from `_last_error` (set by `EdgeTTSGenerator`) and adds the `pip install -U edge-tts` hint on 403s. One failed chunk fails the whole run — never merge around a gap — and cancels the chunks still in flight (finished ones are already cached, so a re-run resumes). The CLI exits 1 (also for `MergeFailed` and `ultra_fast.EmptyInputError`), REST returns 502, MCP counts it in `synths_failed`. `generate_audio_with_subs` (used by `--srt/--vtt` and `--study`) must pass `boundary="WordBoundary"` — edge-tts >= 7 defaults to `SentenceBoundary`, which yields zero word events — and raises `GenerationFailed` itself. CLI exit codes: 0 ok, 1 synthesis/merge failure, 2 usage error (no text, missing file), 130 Ctrl+C.
- **Languages**: add a language by adding it to `constants.VOICE_MAP`; CLI choices, config validation, REST/MCP validation, GUI dropdowns and completions all derive from it. `--lang ka` (Eka), `--lang ka-m` (Giorgi).
- **Console scripts are installed under two spellings**: `tts-ka*` (documented) and `TTS_ka*` (original). Both map to the same entry points in `pyproject.toml`; the lowercase set exists because Linux filesystems are case-sensitive and every doc/help string says `tts-ka`.
- **Linux clipboard** (`main._read_clipboard`): on Linux the session helper runs *before* tkinter — `wl-paste` when `WAYLAND_DISPLAY` is set, then `xclip`, then `xsel`. Under Wayland, tkinter talks to XWayland and silently returns a **stale** X11 selection when the compositor does not bridge clipboards, so trying tkinter first makes `cb` speak the wrong text rather than fail. `deps.check_clipboard()` reports which helper `--doctor` found.
- **`--live` AI-streaming mode**: `tts-ka --live -l en` reads stdin in raw `os.read` blocks through an incremental UTF-8 decoder (Georgian is 3 bytes/char), accumulates in `SentenceBuffer`, flushes on `[.!?]+\s` (not after abbreviations, initials or a line-leading `1.`), paragraph break, a run-on over `MAX_SENTENCE_CHARS`, or idle (default 800 ms via `--live-idle-ms`). Ctrl+C calls `player.stop()` instead of playing out the queue. Code fences (` ``` `) are held open until closed so `not_reading.replace_not_readable` can collapse them; per-sentence MP3s feed into `StreamingAudioPlayer` with `chunk_index` ordering. Use case: `claude --print | tts-ka --live`.
- **MCP server (`tts-ka-mcp`)**: stdio JSON-RPC server (`pip install -e ".[mcp]"`). Tools: `speak`, `stream_open`, `stream_append`, `stream_close`, `session_status`, `list_sessions`, `pause`, `resume`, `skip`, `stop`, `list_voices`. Failures raise `ToolError` (clients get `isError`), never `"error: …"` strings; lang/voice go through `voices.validate_lang_voice` (shared with REST). `_LiveSession._queued` is both the status-visible sentence count and each sentence's playback index (assigned synchronously in `feed`, so an empty/failed sentence can `skip_index` its slot); `_spoken` counts sentences handed to the player. `feed` uses `SentenceBuffer.feed(eager_end=True)` (an append is a complete message) and re-arms a `MCP_IDLE_FLUSH_MS` timer that drains a trailing fragment. `stop()` is async (player stop runs in a thread so it can't block the loop) and cancels pending synths. Idle sessions (`SESSION_IDLE_TIMEOUT_S`) are reaped lazily in `stream_open` / `list_sessions`. `speak` plays through a headless `StreamingAudioPlayer` (so `stop`/`pause` reach it and `blocking` waits for real) when `PlayerDetector.find()` finds one, else falls back to `play_audio` + ffprobe duration. `build_server(sessions=dict)` factory lets tests inject a session dict for inspection. MP3s live in per-session / per-`speak` temp dirs that can't be deleted when the tool returns (the player may still be reading them): they go after `wait_until_released()` (or, on the `play_audio` path, after the ffprobe duration + grace), and `main()` sweeps the `_tmp_dirs` registry on exit. Configure in Claude Code: `{"mcpServers": {"tts-ka": {"command": "tts-ka-mcp"}}}`.
- **MCP stdout safety**: stray `print()` from edge-tts/players must never reach the JSON-RPC stream. mcp >= 2's `stdio_server()` handles this itself: while serving it `dup2`s fd 1 onto stderr and frames on a private duplicate of the real stdout, so `main()` just calls `build_server().run("stdio")`. Do not swap `sys.stdout` by hand or pass `stdout=` to `stdio_server` (explicit streams skip the fd claim). `tests/test_mcp_server_e2e.py` hangs on `session.initialize()` if this regresses.
- **Study mode (`--study`)**: synchronized RSVP word-flash + audio playback over the same text. Reuses `fast_audio.generate_audio_with_subs` for the per-word `WordEvent` timing list; `study_session.StudySession` is the pure-logic model (binary-search lookup via `bisect_right` on a pre-extracted `_starts` array, O(log n) inside the 30 Hz sync loop). The Tk player polls `pygame.mixer.music.get_pos()` every 33 ms and updates a centred big-word label plus faded peripheral context. Quiz generation lives behind a `QuizProvider` Protocol so a future LLM backend can swap in without touching the player; the default `RuleBasedProvider._generate_for_chunk` is a TODO(human) slot — wrap of the slot raises `NotImplementedError`, intentionally, so the player surfaces it instead of silently returning empty results. Session log is plain JSONL at `~/.tts_ka_study.jsonl`.
