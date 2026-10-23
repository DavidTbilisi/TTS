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
| `streaming_player.py` | `PlayerDetector` + queue-based background playback thread |
| `live_stream.py` | `--live` mode: read stdin incrementally, speak each sentence as it lands (for piping LLM output) |
| `mcp_server.py` | MCP server (`tts-ka-mcp`): `speak`, `stream_open` / `stream_append` / `stream_close`, `session_status`, `list_sessions`, `stop`, `list_voices` over stdio |
| `server.py` | `tts-ka serve` FastAPI REST server (`/voices`, `/synthesize`; `[server]` extra) |
| `gui.py` | tkinter GUI (`tts-ka-gui`): Setup / Speak / Config / Hotkeys / Windows shell (Windows only) / About tabs |
| `chunking.py` | WPM-based text splitting |
| `not_reading.py` | Text sanitization before generation |
| `readers/` | File → text by extension (txt/md/html/pdf/epub/docx; heavy deps via `[readers]`) |
| `voices.py` / `prosody.py` | Voice catalog (`--list-voices`, `--voice`); `--rate/--pitch/--volume` parsing |
| `metadata.py` / `subtitles.py` | ID3 tags + chapters (`[metadata]`); SRT/VTT from edge-tts WordBoundary events |
| `user_config.py` | JSON config loading, CLI defaults, `LANG_CODES` |
| `deps.py` | `--doctor` checks; shared `MissingExtraError` for optional extras |
| `rich_progress.py` | rich progress bar + `cprint` (stderr, so `--json` stdout stays clean) |
| `completion.py` / `simple_help.py` | `--print-completion` scripts; `--help-full` text |
| `native_hotkeys.py` / `windows_shell.py` | pynput global hotkeys (`[hotkeys]`); Explorer context-menu installer wrapper |
| `constants.py` | `VOICE_MAP` (`ka`, `ka-m`, `ru`, `en`, `en-US`) — the single source of supported languages — plus stream/worker limits |
| `extras/autohotkey/` | Windows: `TTS_ka_hotkeys.ahk` (hotkeys + Apps key / Ctrl+Alt+RButton language menu), `Install-TTS_ka-Hotkeys.ps1` (Startup) |
| `extras/windows/context_menu/` | `Install-TTS_ka-ContextMenu.ps1` — nested “Read with TTS_ka” on Explorer/Desktop background (clipboard) |

### Non-obvious design decisions

- **Streaming**: `StreamingAudioPlayer` plays chunks as they finish. `PlayerDetector` order is mpv → VLC → ffplay → mplayer (`--player` overrides). mpv gets a gapless stdin playlist; on Windows VLC gets one instance driven over TCP RC, else per-chunk `os.startfile`.
- **Merge fallbacks**: `soundfile` → PyDub → FFmpeg (`-c copy`, concat list in a temp file).
- **Synthesis is edge-tts only**: the unofficial Bing HTTP shortcut was removed (it returned 401/403). edge-tts < 7.3.1 is also rejected with 403, hence the floor in `pyproject.toml`.
- **Failure contract**: `fast_generate_audio` returns `False` (it does not raise) when synthesis fails. Every caller must turn that into `GenerationFailed` via `fast_audio.generation_failed()`, which pulls the reason from `_last_error` (set by `EdgeTTSGenerator`) and adds the `pip install -U edge-tts` hint on 403s. One failed chunk fails the whole run — never merge around a gap. The CLI exits 1, REST returns 502, MCP counts it in `synths_failed`.
- **Languages**: add a language by adding it to `constants.VOICE_MAP`; CLI choices, config validation, REST/MCP validation, GUI dropdowns and completions all derive from it. `--lang ka` (Eka), `--lang ka-m` (Giorgi).
- **Console scripts are installed under two spellings**: `tts-ka*` (documented) and `TTS_ka*` (original). Both map to the same entry points in `pyproject.toml`; the lowercase set exists because Linux filesystems are case-sensitive and every doc/help string says `tts-ka`.
- **Linux clipboard** (`main._read_clipboard`): on Linux the session helper runs *before* tkinter — `wl-paste` when `WAYLAND_DISPLAY` is set, then `xclip`, then `xsel`. Under Wayland, tkinter talks to XWayland and silently returns a **stale** X11 selection when the compositor does not bridge clipboards, so trying tkinter first makes `cb` speak the wrong text rather than fail. `deps.check_clipboard()` reports which helper `--doctor` found.
- **`--live` AI-streaming mode**: `tts-ka --live -l en` reads stdin line-by-line, accumulates in `SentenceBuffer`, flushes on `[.!?]+\s`, paragraph break, or idle (default 800 ms via `--live-idle-ms`). Code fences (` ``` `) are held open until closed so `not_reading.replace_not_readable` can collapse them; per-sentence MP3s feed into `StreamingAudioPlayer` with `chunk_index` ordering. Use case: `claude --print | tts-ka --live`.
- **MCP server (`tts-ka-mcp`)**: stdio JSON-RPC server (`pip install -e ".[mcp]"`). Tools: `speak`, `stream_open`, `stream_append`, `stream_close`, `session_status`, `list_sessions`, `stop`, `list_voices`. `_LiveSession` tracks two counters: `_idx` (output-file numbering, ticks inside `_speak`) and `_queued` (status-visible, ticks when `feed` extracts a sentence — so an agent can see backed-up synths via `synths_pending = _queued - done_tasks`). `build_server(sessions=dict)` factory lets tests inject a session dict for inspection. MP3s live in per-session / per-`speak` temp dirs that can't be deleted when the tool returns (the player may still be reading them): a session's dir goes after its playback thread *and* player process finish, a one-shot clip's after its ffprobe duration + grace, and `main()` sweeps the `_tmp_dirs` registry on exit. Configure in Claude Code: `{"mcpServers": {"tts-ka": {"command": "tts-ka-mcp"}}}`.
- **MCP stdout safety**: stray `print()` from edge-tts/players must never reach the JSON-RPC stream. mcp >= 2's `stdio_server()` handles this itself: while serving it `dup2`s fd 1 onto stderr and frames on a private duplicate of the real stdout, so `main()` just calls `build_server().run("stdio")`. Do not swap `sys.stdout` by hand or pass `stdout=` to `stdio_server` (explicit streams skip the fd claim). `tests/test_mcp_server_e2e.py` hangs on `session.initialize()` if this regresses.
