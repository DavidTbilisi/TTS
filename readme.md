# TTS_ka 🚀 Ultra-Fast Text-to-Speech

**CLI + GUI + REST + MCP** text-to-speech for **Georgian (🇬🇪 ka, ka-m)**, **Russian (🇷🇺 ru)**, and **English (🇬🇧 en, 🇺🇸 en-US)** — built on Microsoft Edge neural voices. Smart chunking, parallel synthesis, streaming playback, ID3 + chapter tagging, SRT/VTT subtitles, document readers (PDF / EPUB / DOCX / HTML / Markdown), and an **AI-friendly `--live` stdin mode + MCP server** so an LLM can speak while it generates.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/TTS_ka.svg)](https://pypi.org/project/TTS_ka/)

---

## Why TTS_ka

- **Three input shapes**: a positional string, a file path (auto-detected by extension), or `clipboard` / `cb` / `clip` / `paste`.
- **Three output shapes**: an MP3 on disk, immediate playback, or live streaming chunks playing while the rest synthesizes.
- **Three integration shapes**: standalone CLI, REST server (`tts-ka serve`), or MCP server (`tts-ka-mcp`) for AI agents.
- **Auto-optimized by default**: just give it `--lang` (or rely on the config). Chunking and parallelism are picked from text length and machine. No flags needed for the common case.

## Install

```bash
pip install TTS_ka                 # core CLI (edge-tts, pydub, rich)
pip install "TTS_ka[readers]"      # + PDF / EPUB / DOCX / HTML readers
pip install "TTS_ka[metadata]"     # + mutagen for ID3 tags / chapters
pip install "TTS_ka[server]"       # + FastAPI / uvicorn (REST server)
pip install "TTS_ka[mcp]"          # + MCP SDK (AI-agent integration)
pip install "TTS_ka[soundfile]"    # + soundfile merges for non-MP3 output
pip install "TTS_ka[hotkeys]"      # + pynput (Windows native hotkeys)
pip install "TTS_ka[dev]"          # test tools + black / flake8 / mypy
```

`ffmpeg` must be installed and on `PATH` (used for merging chunked parts). The streaming player (`--stream`) prefers `mpv`, then VLC → `ffplay` → `mplayer` (override with `--player`); without any of those, Linux / macOS only play the first chunk via `mpg123` / `afplay`, so install `mpv` for real streaming.

Verify:

```bash
tts-ka --doctor      # alias: --check-deps
```

You should see `[OK]` rows for **edge-tts**, **pydub**, **ffmpeg**, and (if streaming is wanted) at least one streaming player. Exit code is `1` if a critical piece is missing.

## Quick start

```bash
# Direct text
python -m TTS_ka "Hello world" --lang en

# Clipboard (shorthand: cb / clip / paste)
python -m TTS_ka cb --lang ka
# Linux: needs wl-clipboard (Wayland) or xclip/xsel (X11) — `--doctor` reports which.

# File (auto-dispatched by extension)
python -m TTS_ka chapter1.pdf --lang en        # needs [readers] extra
python -m TTS_ka notes.md --lang en
python -m TTS_ka document.docx --lang en

# Save to a specific path, refuse to overwrite without --force
python -m TTS_ka "Lecture excerpt" --lang en -o lectures/lec1.mp3
```

Console-script aliases are installed under both spellings — `tts-ka` and `TTS_ka`
(likewise `tts-ka-gui` / `TTS_ka-gui`, `tts-ka-mcp` / `TTS_ka-mcp`). Linux
filesystems are case-sensitive, so pick whichever you prefer and it will resolve:

```bash
tts-ka "Hello" -l en
TTS_ka "Hello" -l en
```

`-l` is `--lang`; both are accepted everywhere below.

---

## AI-friendly modes

### `--live`: pipe LLM output and speak as it lands

Read stdin **incrementally** (raw blocks, not lines — a long line is spoken sentence by sentence), accumulate into a sentence buffer, and synthesize each complete sentence as it arrives — no waiting for the whole response. Sentence boundaries are `[.!?]+` followed by whitespace, or a `\n\n` paragraph break, or an idle timeout if the stream pauses. Abbreviations (`e.g.`, `Dr.`, `т.е.`), initials and `1.` list markers don't split; run-ons over 400 characters are cut at a comma. A sentence that fails to synthesize is skipped instead of holding back the rest, and Ctrl+C stops playback immediately.

```bash
# Pipe any tool that writes to stdout
claude --print "Explain B-trees in one paragraph" | python -m TTS_ka --live -l en

# Or hand the stream over a Unix pipe
my-llm-cli | tts-ka --live -l en --voice en-US-JennyNeural
```

**Idle flush**: if the upstream stalls mid-sentence, the buffer is flushed after `--live-idle-ms` (default `800`). Tighten for snappy local models, loosen for slow networks:

```bash
... | tts-ka --live --live-idle-ms 400 -l en      # responsive
... | tts-ka --live --live-idle-ms 2000 -l en     # patient
```

**Fenced code is held back until closed.** When the LLM emits a `` ``` `` fence, the buffer pauses; once the closing fence arrives, the whole block is collapsed by the sanitizer to "omitted fenced code block" instead of letting the voice read symbols. EOF flushes whatever remained.

### MCP server: AI agents call TTS_ka natively

Install the extra and configure your MCP client to launch `tts-ka-mcp`:

```bash
pip install "TTS_ka[mcp]"
```

Claude Code / Claude Desktop config:

```json
{
  "mcpServers": {
    "tts-ka": { "command": "tts-ka-mcp" }
  }
}
```

Tools exposed:

| Tool | Purpose |
|------|--------|
| `speak(text, lang?, voice?, blocking?, interrupt?)` | One-shot: synthesize and play. `blocking=True` returns when playback has finished so the agent can sequence speech; `interrupt=True` stops whatever is playing first. The return string echoes the resolved settings |
| `stream_open(lang?, voice?)` | Start a streaming session, returns `session_id` |
| `stream_append(session_id, text)` | Push text; speaks each complete sentence — including one that ends the appended text — and an unfinished tail after 500 ms of silence |
| `stream_close(session_id)` | Drain remaining buffer, end the session |
| `session_status(session_id)` | Inspect progress: total, pending synths, `synths_failed` + `last_error`, buffer preview, `controllable` |
| `list_sessions()` | All active session IDs |
| `pause` / `resume` / `skip(session_id?)` | Control one session, or everything playing (needs mpv on Linux/macOS) |
| `stop(session_id?)` | Tear down one session, or abort all playback and sessions |
| `list_voices(lang?)` | Voice catalog as JSON |

Errors (unknown `session_id`, invalid `lang`/`voice`, synthesis failure, no audio player) come back as MCP tool errors (`isError: true`), not as `"error: …"` strings. Sessions idle for 15 minutes are closed when the next session is opened or listed.

Why streaming over single `speak` calls: the LLM can push tokens as it generates them. Each completed sentence is synthesized immediately, so the user hears audio with sub-second latency from the LLM's first word. `session_status` reports `synths_pending` (queue backed up) and `synths_failed` / `last_error` (a synthesis failed) so the agent can react.

### `--json`: machine-readable progress

Suppresses decorative stdout; emits one JSON object per line on stdout (decorations move to stderr):

```bash
python -m TTS_ka large.pdf --lang en --json -o out.mp3
{"event": "start", "words": 1284, "lang": "en"}
{"event": "done",  "output": "out.mp3", "seconds": 12.317}
```

---

## Voices and prosody

### Voice catalog

12 curated Edge neural voices across **ka / ru / en** (en covers GB, US and AU), listable from the CLI:

```bash
python -m TTS_ka --list-voices              # all
python -m TTS_ka --list-voices --lang ka    # filter to Georgian

python -m TTS_ka --preview-voice en-US-JennyNeural    # short sample, then exits
```

Built-in defaults via `--lang`:

| `--lang` | Voice | Notes |
|----------|-------|-------|
| `ka` | `ka-GE-EkaNeural` | Georgian, female |
| `ka-m` | `ka-GE-GiorgiNeural` | Georgian, male |
| `ru` | `ru-RU-SvetlanaNeural` | Russian, female |
| `en` | `en-GB-SoniaNeural` | British English, female |
| `en-US` | `en-US-SteffanNeural` | American English, male |

Override per-call with `--voice`. When `--voice` is given, `--lang` is inferred from the voice locale — pass both only if you want the parser to validate they agree (it errors on mismatch):

```bash
python -m TTS_ka "Hello" --voice en-US-AriaNeural    # lang auto = en
python -m TTS_ka "Привет" --voice ru-RU-DmitryNeural # lang auto = ru
```

### Speech rate / pitch / volume

Passed through to edge-tts as prosody settings. Values are **signed percentages** (or Hz for pitch). Both shells need `%%` literal escapes only inside Windows batch files — in PowerShell / bash, plain `%` works:

```bash
python -m TTS_ka "Slow and low" --lang en --rate=-20% --pitch=-5Hz
python -m TTS_ka "Energetic" --lang en --rate=+30% --volume=+10%
```

Out-of-range values are clamped at parse time (so `--rate=+500%` becomes the max the engine accepts) rather than failing the call.

---

## Document readers

With `pip install "TTS_ka[readers]"`, file inputs are dispatched by extension:

| Extension | Reader | Optional dep |
|-----------|--------|--------------|
| `.txt`, `.rst` | plain UTF-8 | — |
| `.md`, `.markdown` | strips fences, links, emphasis, headers | — |
| `.html`, `.htm` | BeautifulSoup if available, regex fallback | `beautifulsoup4` |
| `.pdf` | text per page, joined; `--pages` selects pages | `pdftotext` (poppler) if installed, else `pypdf` |
| `.epub` | each item's text, joined | `ebooklib` + `beautifulsoup4` |
| `.docx` | paragraph text | `python-docx` |

Unknown extensions fall back to UTF-8 plain reading. Missing extras raise `MissingExtraError` with the exact `pip install` line.

For PDFs, install poppler (`sudo apt install poppler-utils`, `brew install poppler`) when you can. Typeset books mark hyphenation points with soft hyphens, and `pypdf` extracts those as spaces, so `different` is read aloud as "dif fer ent". `pdftotext` keeps them as soft hyphens, which TTS_ka removes. `--doctor` shows which extractor is in use.

```bash
python -m TTS_ka book.epub --lang en -o book.mp3 --chapters book-chapters.json
```

For a PDF, `--pages` reads only part of it: 1-based page numbers, comma-separated, with `N-` running to the last page and `-M` starting at the first. Only the selected pages are extracted, so picking a chapter out of a long book is fast. A page past the end, a malformed range, or `--pages` on anything that isn't a PDF file exits 2.

```bash
python -m TTS_ka book.pdf --lang en --pages 20-24 --stream   # one chapter
python -m TTS_ka book.pdf --lang en --pages 1-3,7,410-      # several ranges, in the order given
```

---

## Streaming playback

`--stream` starts playback while later chunks are still synthesizing. Order is preserved by chunk index even when chunks complete out of order.

```bash
# Audio starts within seconds
python -m TTS_ka long_article.txt --lang en --stream

# Headless VLC (no GUI window on Windows)
python -m TTS_ka chapter.epub --lang en --stream --no-gui

# Pick a specific player
python -m TTS_ka text.txt --lang en --stream --player mpv
```

On Windows with VLC, a single VLC window receives chunks over TCP remote-control as they finish (`TTS_KA_VLC_RC=0` disables this and falls back to one VLC process per chunk). On Linux / macOS, headless `mpv` (MCP, `--no-gui`) is driven over its JSON IPC socket: it idles between chunks, so a slow chunk never ends playback early, and it can be paused, resumed and skipped. GUI `mpv` receives chunks over a stdin playlist (`--keep-open` bridges the gaps); `ffplay` plays them one by one; VLC and `mplayer` start once every chunk is ready.

Ctrl+C cancels generation and terminates the active player without waiting for the playback-join timeout.

---

## Metadata, chapters, and subtitles

ID3 tags require `pip install "TTS_ka[metadata]"` (mutagen). Subtitle export does not need an extra.

```bash
python -m TTS_ka chapter.txt --lang en -o ch1.mp3 \
    --title "Chapter 1" --author "Jane Doe" --album "My Book" \
    --cover cover.jpg \
    --chapters chapters.json \
    --srt --vtt
```

`chapters.json` shape:

```json
[
  {"title": "Intro",     "start_ms": 0,      "end_ms": 12500},
  {"title": "Main idea", "start_ms": 12500,  "end_ms": 45000}
]
```

The SRT/VTT writer uses real edge-tts `WordBoundary` events, so timings line up to spoken-word boundaries (not estimated). Files are written next to the MP3 (`ch1.srt`, `ch1.vtt`).

---

## REST server (`tts-ka serve`)

```bash
pip install "TTS_ka[server]"
tts-ka serve --host 127.0.0.1 --port 7777 --token "$(openssl rand -hex 32)"
# or set TTS_API_TOKEN in the environment
```

Endpoints:

```
GET  /voices                 → JSON catalog (same shape as --list-voices)
POST /synthesize             → audio/mpeg stream
     body: {"text": "...", "lang": "en", "voice": "..."}   # lang: any --lang code
     auth: Authorization: Bearer <token>
```

Concurrency is capped at `MAX_PARALLEL_WORKERS` (6; see `constants.py`). Each request is synthesized to a temporary MP3 that is streamed back as `audio/mpeg` and then deleted.

---

## GUI (`tts-ka-gui`)

```bash
tts-ka-gui
# or: python -m TTS_ka.gui
```

Tkinter window with these tabs:

- **Setup** — guided first run: verify dependencies, pick and preview a voice, then speak.
- **Speak** — paste text or point at a UTF-8 file, choose language and voice, hit **Speak** with optional **Stream**.
- **Config** — edit the JSON config (path, defaults), Save / Reload.
- **Hotkeys** — edit and start the native global hotkeys.
- **Windows shell** (Windows only) — install / uninstall the Explorer context menu.
- **About** — version and project links.

The GUI picks a system font that handles Georgian + Cyrillic (Segoe UI / Sylfaen on Windows, Noto Sans / Noto Sans Georgian on Linux). Symbol-only fonts that lack Mkhedruli are avoided.

Debian/Ubuntu may need Tk: `sudo apt install python3-tk`.

---

## Windows extras

### One-step setup (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File .\extras\windows\Install-TTS_ka-Windows.ps1
```

Checks that TTS_ka is runnable and that AutoHotkey v2 is present (printing
`winget install AutoHotkey.AutoHotkey` if not), then installs the Explorer/Desktop
context menu and the global hotkeys, and prints a short "what you can do now" summary.
Flags: `-SkipHotkeys`, `-SkipContextMenu`, `-PythonPath`, `-Uninstall`, `-WhatIf`. The
individual installers below still work if you want finer control.

### Native global hotkeys (no AutoHotkey)

```bash
pip install "TTS_ka[hotkeys]"
tts-ka-hotkeys             # or enable on the GUI's "Windows shell" tab
```

Defaults map **Ctrl+Alt+1..4** → `en` / `ru` / `ka` / `ka-m`. Each press spawns `python -m TTS_ka clipboard --lang …` in a new process. Override in `~/.tts_config.json` under the `hotkeys` key (see [extras/tts_config.example.json](extras/tts_config.example.json)). JSON `null` removes a default combo.

### AutoHotkey v2 scripts

```powershell
powershell -ExecutionPolicy Bypass -File .\extras\autohotkey\Install-TTS_ka-Hotkeys.ps1
```

Copies `TTS_ka_hotkeys.ahk` into Startup and launches it. Defaults: **Alt+E / Alt+R / Alt+X** for en / ru / ka. The **Menu key** or **Ctrl+Alt+RightClick** pops a small language menu at the cursor for in-app selections (Chrome, Word, etc.) where third-party right-click menu items are blocked. Pass `-Uninstall` / `-NoStart` / `-WhatIf` as needed.

### Explorer / Desktop context menu

```powershell
powershell -ExecutionPolicy Bypass -File .\extras\windows\context_menu\Install-TTS_ka-ContextMenu.ps1
```

Adds "Read with TTS_ka" → submenu of languages on empty Explorer space and the Desktop (reads clipboard). Options:

| Flag | Meaning |
|------|--------|
| `-FlatMenu` | One top-level entry per language |
| `-Languages @('en','ru')` | Subset only |
| `-IncludeTextFiles` | Also add a "read this file" entry on `.txt` files |
| `-Uninstall` | Remove all entries |

On Windows 11, the entries land under **Show more options** (classic shell).

---

## Shell completions

```bash
tts-ka --print-completion bash > /etc/bash_completion.d/tts-ka
tts-ka --print-completion zsh  > "${fpath[1]}/_tts-ka"
tts-ka --print-completion fish > ~/.config/fish/completions/tts-ka.fish
```

The scripts register both `tts-ka` and `TTS_ka`, and complete every flag plus the values of `--lang`, `--voice`, `--player`, and file arguments.

---

## CLI reference

```
tts-ka [TEXT] [OPTIONS]          # or: python -m TTS_ka
tts-ka serve [--host HOST] [--port PORT] [--token TOK]
tts-ka-gui
tts-ka-mcp        # stdio JSON-RPC for MCP clients
tts-ka-hotkeys    # background hotkey listener (Windows, [hotkeys] extra)
```

### Core flags

| Flag | Description |
|------|-------------|
| `-l`, `--lang {ka,ka-m,ru,en,en-US}` | Voice language |
| `--voice ID` | Specific voice (overrides default for `--lang`) |
| `-o`, `--output PATH` | Output MP3 path (default `data.mp3`); refuses overwrite without `--force` |
| `--force` | Overwrite an existing output file |
| `-c`, `--chunk-seconds N` | Chunk size (`0` = auto, `20–60` is the sweet spot) |
| `-j`, `--parallel N` | Workers (`0` = auto, capped at `MAX_PARALLEL_WORKERS` = 6) |
| `-n`, `--no-play` | Skip automatic playback after generation |
| `-s`, `--stream` | Play chunks as they finish |
| `--no-gui` | With `--stream`, run VLC headless |
| `--player NAME` | Preferred streaming player (vlc, mpv, ffplay, mplayer) |
| `--no-turbo`, `--legacy` | Disable auto-optimization |

### Prosody

| Flag | Format | Example |
|------|--------|---------|
| `--rate` | signed % | `--rate=+30%`, `--rate=-20%` |
| `--pitch` | Hz or signed % | `--pitch=+5Hz`, `--pitch=-10%` |
| `--volume` | signed % | `--volume=+10%` |

### Audio metadata (needs `[metadata]` extra)

| Flag | ID3 frame |
|------|-----------|
| `--title` | TIT2 |
| `--author` | TPE1 |
| `--album` | TALB |
| `--cover PATH` | APIC (JPEG/PNG) |
| `--chapters PATH` | CHAP + CTOC from a JSON file |

### Subtitles

| Flag | Output |
|------|--------|
| `--srt` | `<output>.srt` next to the MP3 |
| `--vtt` | `<output>.vtt` next to the MP3 |

### AI integration

| Flag | Purpose |
|------|--------|
| `--live` | Read stdin incrementally, speak each sentence |
| `--live-idle-ms N` | Flush a partial sentence after N ms of silence (default `800`) |
| `--json` | One JSON event per line on stdout |

### Utility

| Flag | Purpose |
|------|--------|
| `-V`, `--version` | Print version, Python, platform, distribution metadata |
| `--doctor`, `--check-deps` | Print ffmpeg + player + Python dep status; exit 1 if critical deps missing |
| `--list-voices` | Print voice catalog (filterable with `--lang`) |
| `--preview-voice ID` | Play a short sample with that voice, then exit |
| `--help-full`, `-H` | Comprehensive help screen |
| `--print-completion {bash,zsh,fish}` | Emit a completion script |
| `--config PATH` | Use this JSON config (also `TTS_KA_CONFIG` env var) |
| `--no-cache` | Synthesize everything fresh this run (don't read or write the chunk cache) |
| `--clear-cache` | Delete the chunk cache, report the space freed, exit |

---

## Configuration

A JSON file is loaded from (first hit wins):

1. `--config PATH` on the CLI
2. `TTS_KA_CONFIG` environment variable
3. `~/.tts_config.json`

All keys are optional. Real, supported schema:

```json
{
  "lang":          "en",
  "output":        "data.mp3",
  "chunk_seconds": 0,
  "parallel":      0,
  "no_play":       false,
  "stream":        false,
  "no_turbo":      false,
  "no_gui":        false,

  "rate":          "+30%",
  "pitch":         "+0Hz",
  "volume":        "+0%",

  "vlc_rc":        true,
  "cache":         true,
  "cache_max_mb":  500,

  "hotkeys": {
    "<ctrl>+<alt>+1": "en",
    "<ctrl>+<alt>+2": "ru",
    "<ctrl>+<alt>+3": "ka",
    "<ctrl>+<alt>+4": "ka-m"
  }
}
```

`rate` / `pitch` / `volume` are signed strings in the same form `--rate` / `--pitch` / `--volume` accept on the CLI. They become the default for **every** invocation — CLI, GUI, REST server, and MCP server. Pass them per-call on `mcp__tts-ka__speak` / `stream_open` to override for one call; pass `--rate` etc. on the CLI to override one run.

`"vlc_rc": false` sets `TTS_KA_VLC_RC=0` for the process (unless that variable is already set), so you don't have to export it in every shell. Likewise `"cache": false` → `TTS_KA_CACHE=0` and `"cache_max_mb"` → `TTS_KA_CACHE_MAX_MB`.

`hotkeys`: pynput combo strings → `--lang` codes. JSON `null` removes a default.

### Environment variables

| Variable | Effect |
|----------|--------|
| `TTS_KA_CONFIG` | Alternate config file path |
| `TTS_KA_VLC_RC` | `0` → disable VLC remote-control mode (one VLC per chunk instead) |
| `TTS_KA_MPV_IPC` | `0` → don't drive headless mpv over JSON IPC (falls back to a stdin playlist; no pause/skip) |
| `TTS_KA_CACHE` | `0` → disable the chunk cache |
| `TTS_KA_CACHE_DIR` | Chunk cache location (default `$XDG_CACHE_HOME/tts-ka`, `~/Library/Caches/tts-ka`, `%LOCALAPPDATA%\tts-ka\Cache`) |
| `TTS_KA_CACHE_MAX_MB` | Chunk cache size cap, least-recently-used pruned (default `500`, ≈ 23 h of speech) |
| `TTS_API_TOKEN` | Bearer token required by `tts-ka serve` |

---

## Text sanitization

Before TTS, the pipeline rewrites noisy input so the voice does not read raw syntax. Implemented in `TTS_ka.not_reading.replace_not_readable`.

| Kind of input | What the voice says |
|---------------|--------------------|
| `` ```code``` `` / `` `inline` `` | "omitted fenced code block" / "omitted inline code snippet" |
| `https://…`, `www.…` | "omitted hyperlink" |
| `#!/usr/bin/env python` | "omitted script shebang line" |
| `<div>…</div>` and similar | "omitted markup tag" |
| `file.ts`, `app.py` | "TypeScript", "Python", … (60+ extensions) |
| `API`, `HTTPS`, `JSON`, `k8s`, `OAuth`, … | Spelled or expanded (160+ acronyms) |
| `=>`, `≤`, `∞`, `∀`, … | Spoken words ("implies", "less than or equal to", "infinity", …) |
| 7+ digit runs | "a large number" |

The filter list is composable: import `TextProcessingPipeline` from `not_reading` and build your own ordering if you need to skip a filter.

---

## Performance notes

The shape of the call is what matters, not magic flags:

- **Short text** (under ~200 words, no streaming): one direct edge-tts call. Latency is dominated by the network round-trip.
- **Long text**: split into ~30-second chunks, synthesized in parallel (`--parallel` workers) into a private temp dir, then joined losslessly by byte-concatenating the MP3 parts (no re-encode). Non-MP3 output falls back to `soundfile` → `pydub` → `ffmpeg`. A merge that would drop a chunk fails the run instead of writing a shorter file.
- **Streaming**: chunk size drops to `STREAMING_CHUNK_SECONDS = 15` so the first chunk lands fast and feeds the player while the rest synthesizes.
- **Chunk cache**: every synthesized chunk is cached by (text, voice, rate/pitch/volume), so re-reading the same text is near-instant and a run that failed part-way **resumes**: re-run the same command and only the missing chunks are synthesized. Resuming needs the same chunking — keep `--chunk-seconds`, `-j` and `--stream` unchanged. `tts-ka --doctor` shows the cache size; `--clear-cache` empties it.
- **Retries**: timeouts, dropped connections and 403/408/429/5xx responses are retried with jittered exponential backoff (honouring `Retry-After`). The first chunk that still fails stops the run at once rather than spending requests on a result that can't be used.

For honest timings, run `python -m TTS_ka your-real-text --lang en` and read the printed `Completed in X.XXs` line. Numbers depend heavily on your network to Edge's TTS endpoint, so machine-published benchmarks are not meaningful.

If you hit `403` or `Invalid response status`:

```bash
pip install -U edge-tts                 # Microsoft rotates access tokens; 7.2.x is already rejected
# then reduce workers if many chunks still fail:
python -m TTS_ka your-text --lang en --parallel 2
```

---

## Troubleshooting

**`No module named 'edge_tts'`** — `pip install -U edge-tts`.

**`FFmpeg not found`** — install ffmpeg and ensure it is on `PATH`. Verify with `ffmpeg -version`. On Windows, [download](https://ffmpeg.org/download.html) and add the `bin\` folder to PATH. On macOS, `brew install ffmpeg`. On Debian/Ubuntu, `sudo apt install ffmpeg`.

**Empty clipboard** — copy text first, then re-run with `cb` / `clipboard`. On Linux the reader uses `wl-paste` (Wayland), then `xclip` / `xsel`, before tkinter; elsewhere tkinter first, then PowerShell `Get-Clipboard` on Windows or `pbpaste` on macOS. `tts-ka --doctor` shows which helper was found.

**`--stream` does nothing visible** — no player was detected. Install `mpv` (recommended; Linux: `apt install mpv`, macOS: `brew install mpv`) or VLC (Windows: from videolan.org).

**MCP client doesn't see the server** — confirm `tts-ka-mcp` is on `PATH` (it is installed by `[mcp]` extra). Try running it manually; you should see nothing on stdout and JSON-RPC handshake output only when a client connects.

**Hung `--live` process** — the live loop blocks on stdin until EOF. Send Ctrl+D (Unix) / Ctrl+Z + Enter (Windows) to close the input stream, or Ctrl+C to abort.

**Ctrl+C left a partial file** — chunks are written to a per-run `tts-ka-run-*` dir in the system temp dir and removed on success, failure, or Ctrl+C; the output file is only replaced once the merge succeeds. Dirs left behind by a crash (or by GUI streaming, whose player reads them lazily) are swept on a later run after 12 hours.

**Exit codes** — `0` success, `1` synthesis or merge failure, `2` usage error (no text, empty stdin/clipboard, file not found, bad option), `130` Ctrl+C. A single word that looks like a path (`notes.txt`, `docs/intro`) but doesn't exist is reported as *file not found* rather than read aloud; pipe it in (`echo notes.txt | tts-ka -`) to speak it literally.

---

## Development

```bash
git clone https://github.com/DavidTbilisi/TTS.git
cd TTS
pip install -e ".[dev]"
pytest                              # full suite; coverage gate at 70%
pytest tests/test_live_stream.py    # one file
pytest -m "not slow"                # skip the subprocess-spawning E2E
black src/ tests/
flake8 src/ tests/
mypy src/
```

To release: `python scripts/release.py minor` bumps the version, commits, tags, and pushes; then publish the GitHub Release for the tag to trigger PyPI upload.

---

## License & credits

MIT — see [LICENSE](LICENSE).

Built on **edge-tts** (Microsoft Edge voices), **pydub** + **soundfile** + **ffmpeg** (audio merge / encode), **rich** (terminal progress), **mutagen** (ID3 tags), **mcp** (Model Context Protocol SDK), **FastAPI** + **uvicorn** (REST server), **pynput** (Windows hotkeys).

**Author**: David Chincharashvili — davidchincharashvili@gmail.com — [github.com/DavidTbilisi/TTS](https://github.com/DavidTbilisi/TTS)
