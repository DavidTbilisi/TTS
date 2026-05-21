# TTS_ka 🚀 Ultra-Fast Text-to-Speech

**CLI + GUI + REST + MCP** text-to-speech for **Georgian (🇬🇪 ka, ka-m)**, **Russian (🇷🇺 ru)**, and **English (🇬🇧 en)** — built on Microsoft Edge neural voices. Smart chunking, parallel synthesis, streaming playback, ID3 + chapter tagging, SRT/VTT subtitles, document readers (PDF / EPUB / DOCX / HTML / Markdown), and an **AI-friendly `--live` stdin mode + MCP server** so an LLM can speak while it generates.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.8.0-brightgreen.svg)](https://pypi.org/project/TTS_ka/)

---

## Why TTS_ka

- **Three input shapes**: a positional string, a file path (auto-detected by extension), or `clipboard` / `cb` / `clip` / `paste`.
- **Three output shapes**: an MP3 on disk, immediate playback, or live streaming chunks playing while the rest synthesizes.
- **Three integration shapes**: standalone CLI, REST server (`TTS_ka serve`), or MCP server (`TTS_ka-mcp`) for AI agents.
- **Auto-optimized by default**: just give it `--lang` (or rely on the config). Chunking, parallelism, and the HTTP-vs-edge-tts route are picked from text length and machine. No flags needed for the common case.

## Install

```bash
pip install TTS_ka                 # core CLI (edge-tts, pydub, tqdm, httpx)
pip install "TTS_ka[readers]"      # + PDF / EPUB / DOCX / HTML readers
pip install "TTS_ka[metadata]"     # + mutagen for ID3 tags / chapters
pip install "TTS_ka[server]"       # + FastAPI / uvicorn (REST server)
pip install "TTS_ka[mcp]"          # + MCP SDK (AI-agent integration)
pip install "TTS_ka[soundfile]"    # + faster merges via soundfile
pip install "TTS_ka[hotkeys]"      # + pynput (Windows native hotkeys)
pip install "TTS_ka[dev]"          # everything + tests + linters
```

`ffmpeg` must be installed and on `PATH` (used for merging chunked parts). The streaming player (`--stream`) prefers VLC and falls back to `mpv` → `ffplay` → `mplayer`; without any of those, `--stream` is disabled silently.

Verify:

```bash
python -m TTS_ka --check-deps
```

You should see `[OK]` rows for **edge-tts**, **pydub**, **ffmpeg**, and (if streaming is wanted) at least one streaming player. Exit code is `1` if a critical piece is missing.

## Quick start

```bash
# Direct text
python -m TTS_ka "Hello world" --lang en

# Clipboard (shorthand: cb / clip / paste)
python -m TTS_ka cb --lang ka

# File (auto-dispatched by extension)
python -m TTS_ka chapter1.pdf --lang en        # needs [readers] extra
python -m TTS_ka notes.md --lang en
python -m TTS_ka document.docx --lang en

# Save to a specific path, refuse to overwrite without --force
python -m TTS_ka "Lecture excerpt" --lang en -o lectures/lec1.mp3
```

A short console-script alias is installed as `TTS_ka`:

```bash
TTS_ka "Hello" -l en
```

`-l` is `--lang`; both are accepted everywhere below.

---

## AI-friendly modes

### `--live`: pipe LLM output and speak as it lands

Read stdin **incrementally**, accumulate into a sentence buffer, and synthesize each complete sentence as it arrives — no waiting for the whole response. Sentence boundaries are `[.!?]+` followed by whitespace, or a `\n\n` paragraph break, or an idle timeout if the stream pauses.

```bash
# Pipe any tool that writes to stdout
claude --print "Explain B-trees in one paragraph" | python -m TTS_ka --live -l en

# Or hand the stream over a Unix pipe
my-llm-cli | TTS_ka --live -l en --voice en-US-JennyNeural
```

**Idle flush**: if the upstream stalls mid-sentence, the buffer is flushed after `--live-idle-ms` (default `800`). Tighten for snappy local models, loosen for slow networks:

```bash
... | TTS_ka --live --live-idle-ms 400 -l en      # responsive
... | TTS_ka --live --live-idle-ms 2000 -l en     # patient
```

**Fenced code is held back until closed.** When the LLM emits a `` ``` `` fence, the buffer pauses; once the closing fence arrives, the whole block is collapsed by the sanitizer to "omitted fenced code block" instead of letting the voice read symbols. EOF flushes whatever remained.

### MCP server: AI agents call TTS_ka natively

Install the extra and configure your MCP client to launch `TTS_ka-mcp`:

```bash
pip install "TTS_ka[mcp]"
```

Claude Code / Claude Desktop config:

```json
{
  "mcpServers": {
    "tts-ka": { "command": "TTS_ka-mcp" }
  }
}
```

Tools exposed:

| Tool | Purpose |
|------|--------|
| `speak(text, lang?, voice?)` | One-shot: synthesize and play immediately |
| `stream_open(lang?, voice?)` | Start a streaming session, returns `session_id` |
| `stream_append(session_id, text)` | Push text; speaks each complete sentence |
| `stream_close(session_id)` | Drain remaining buffer, end the session |
| `session_status(session_id)` | Inspect progress: total, pending synths, buffer preview |
| `list_sessions()` | All active session IDs |
| `stop()` | Abort all playback and tear down sessions |
| `list_voices(lang?)` | Voice catalog as JSON |

Why streaming over single `speak` calls: the LLM can push tokens as it generates them. Each completed sentence is synthesized immediately, so the user hears audio with sub-second latency from the LLM's first word. `session_status` reports `synths_pending` so the agent knows when the queue is backed up.

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

12 curated Edge neural voices across **ka / ru / en**, listable from the CLI:

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

Override per-call with `--voice`. When `--voice` is given, `--lang` is inferred from the voice locale — pass both only if you want the parser to validate they agree (it errors on mismatch):

```bash
python -m TTS_ka "Hello" --voice en-US-AriaNeural    # lang auto = en
python -m TTS_ka "Привет" --voice ru-RU-DmitryNeural # lang auto = ru
```

### Speech rate / pitch / volume

SSML `<prosody>` parameters. Values are **signed percentages** (or Hz for pitch). Both shells need `%%` literal escapes only inside Windows batch files — in PowerShell / bash, plain `%` works:

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
| `.pdf` | text per page, joined | `pypdf` |
| `.epub` | each item's text, joined | `ebooklib` + `beautifulsoup4` |
| `.docx` | paragraph text | `python-docx` |

Unknown extensions fall back to UTF-8 plain reading. Missing extras raise `MissingExtraError` with the exact `pip install` line.

```bash
python -m TTS_ka book.epub --lang en -o book.mp3 --chapters book-chapters.json
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

On Windows with VLC, a single VLC window receives chunks over TCP remote-control as they finish (`TTS_KA_VLC_RC=0` disables this and falls back to one VLC process per chunk). On Linux / macOS the player is started once on the full chunk list.

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

## REST server (`TTS_ka serve`)

```bash
pip install "TTS_ka[server]"
TTS_ka serve --host 127.0.0.1 --port 7777 --token "$(openssl rand -hex 32)"
# or set TTS_API_TOKEN in the environment
```

Endpoints:

```
GET  /voices                 → JSON catalog (same shape as --list-voices)
POST /synthesize             → audio/mpeg stream
     body: {"text": "...", "lang": "en", "voice": "...", "rate": "...", ...}
     auth: Authorization: Bearer <token>
```

Concurrency is capped at `MAX_PARALLEL_WORKERS` (32 by default; see `constants.py`). The server streams `audio/mpeg` chunks as they synthesize — no temp file on the server side.

---

## GUI (`TTS_ka-gui`)

```bash
TTS_ka-gui
# or: python -m TTS_ka.gui
```

Tkinter window with three tabs:

- **Speak** — paste text or point at a UTF-8 file, choose language and voice, hit **Speak** with optional **Stream**.
- **Config** — edit the JSON config (path, defaults, hotkeys), Save / Reload.
- **Windows shell** (Windows only) — install / uninstall the Explorer context menu and enable native global hotkeys.

The GUI picks a system font that handles Georgian + Cyrillic (Segoe UI / Sylfaen on Windows, Noto Sans / Noto Sans Georgian on Linux). Symbol-only fonts that lack Mkhedruli are avoided.

Debian/Ubuntu may need Tk: `sudo apt install python3-tk`.

---

## Windows extras

### Native global hotkeys (no AutoHotkey)

```bash
pip install "TTS_ka[hotkeys]"
TTS_ka-hotkeys             # or enable on the GUI's "Windows shell" tab
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
TTS_ka --print-completion bash > /etc/bash_completion.d/TTS_ka
TTS_ka --print-completion zsh  > "${fpath[1]}/_TTS_ka"
TTS_ka --print-completion fish > ~/.config/fish/completions/TTS_ka.fish
```

Completions cover `--lang`, `--voice`, `--player`, and the file/clipboard positional.

---

## CLI reference

```
python -m TTS_ka [TEXT] [OPTIONS]
TTS_ka serve     [--host HOST] [--port PORT] [--token TOK]
TTS_ka-gui
TTS_ka-mcp        # stdio JSON-RPC for MCP clients
TTS_ka-hotkeys    # background hotkey listener (Windows, [hotkeys] extra)
```

### Core flags

| Flag | Description |
|------|-------------|
| `-l`, `--lang {ka,ka-m,ru,en}` | Voice language |
| `--voice ID` | Specific voice (overrides default for `--lang`) |
| `-o`, `--output PATH` | Output MP3 path (default `data.mp3`); refuses overwrite without `--force` |
| `--force` | Overwrite an existing output file |
| `-c`, `--chunk-seconds N` | Chunk size (`0` = auto, `20–60` is the sweet spot) |
| `-j`, `--parallel N` | Workers (`0` = auto, max from `MAX_PARALLEL_WORKERS`) |
| `-n`, `--no-play` | Skip automatic playback after generation |
| `-s`, `--stream` | Play chunks as they finish |
| `--no-gui` | With `--stream`, run VLC headless |
| `--player NAME` | Preferred streaming player (vlc, mpv, ffplay, mplayer) |
| `--no-turbo`, `--legacy` | Disable auto-optimization |

### Prosody (SSML `<prosody>` attributes)

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
| `--check-deps` | Print ffmpeg + player + Python dep status; exit 1 if critical deps missing |
| `--list-voices` | Print voice catalog (filterable with `--lang`) |
| `--preview-voice ID` | Play a short sample with that voice, then exit |
| `--help-full`, `-H` | Comprehensive help screen |
| `--print-completion {bash,zsh,fish}` | Emit a completion script |
| `--config PATH` | Use this JSON config (also `TTS_KA_CONFIG` env var) |

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

  "skip_http":     false,
  "verbose":       false,
  "vlc_rc":        true,

  "hotkeys": {
    "<ctrl>+<alt>+1": "en",
    "<ctrl>+<alt>+2": "ru",
    "<ctrl>+<alt>+3": "ka",
    "<ctrl>+<alt>+4": "ka-m"
  }
}
```

`rate` / `pitch` / `volume` are signed strings in the same form `--rate` / `--pitch` / `--volume` accept on the CLI. They become the default for **every** invocation — CLI, GUI, REST server, and MCP server. Pass them per-call on `mcp__tts-ka__speak` / `stream_open` to override for one call; pass `--rate` etc. on the CLI to override one run.

Boolean keys like `skip_http`, `verbose`, and `vlc_rc` set the matching environment variables (`TTS_KA_SKIP_HTTP=1`, `TTS_KA_VERBOSE=1`, `TTS_KA_VLC_RC=0`) for the process — useful so you don't have to export them in every shell.

`hotkeys`: pynput combo strings → `--lang` codes. JSON `null` removes a default.

### Environment variables

| Variable | Effect |
|----------|--------|
| `TTS_KA_CONFIG` | Alternate config file path |
| `TTS_KA_SKIP_HTTP` | `1` → skip the unofficial Bing HTTP path and use edge-tts only |
| `TTS_KA_VERBOSE` | `1` → log when falling back from HTTP to edge-tts |
| `TTS_KA_VLC_RC` | `0` → disable VLC remote-control mode (one VLC per chunk instead) |
| `TTS_API_TOKEN` | Bearer token required by `TTS_ka serve` |

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
- **Long text**: split into ~30-second chunks, synthesized in parallel (`--parallel` workers), merged via `soundfile` → `pydub` → `ffmpeg` fallbacks.
- **Streaming**: chunk size drops to `STREAMING_CHUNK_SECONDS = 15` so the first chunk lands fast and feeds the player while the rest synthesizes.

For honest timings, run `python -m TTS_ka your-real-text --lang en` and read the printed `Completed in X.XXs` line. Numbers depend heavily on your network to Edge's TTS endpoint, so machine-published benchmarks are not meaningful.

If you hit `403` or `Invalid response status`:

```bash
pip install -U "edge-tts>=7.2.7"        # Microsoft rotates access tokens
# or skip the unofficial HTTP path entirely:
export TTS_KA_SKIP_HTTP=1               # bash / zsh
$env:TTS_KA_SKIP_HTTP = "1"             # PowerShell
set TTS_KA_SKIP_HTTP=1                  # cmd
# then reduce workers if many chunks still fail:
python -m TTS_ka your-text --lang en --parallel 2
```

---

## Troubleshooting

**`No module named 'edge_tts'`** — `pip install -U "edge-tts>=7.2.7"`.

**`FFmpeg not found`** — install ffmpeg and ensure it is on `PATH`. Verify with `ffmpeg -version`. On Windows, [download](https://ffmpeg.org/download.html) and add the `bin\` folder to PATH. On macOS, `brew install ffmpeg`. On Debian/Ubuntu, `sudo apt install ffmpeg`.

**Empty clipboard** — copy text first, then re-run with `cb` / `clipboard`. The reader is stdlib-only (tkinter first, then PowerShell `Get-Clipboard` on Windows, `pbpaste` on macOS).

**`--stream` does nothing visible** — no player was detected. Install VLC (Windows: from videolan.org; macOS: `brew install --cask vlc`; Linux: distro package) or set `--player mpv` after `apt install mpv`.

**MCP client doesn't see the server** — confirm `TTS_ka-mcp` is on `PATH` (it is installed by `[mcp]` extra). Try running it manually; you should see nothing on stdout and JSON-RPC handshake output only when a client connects.

**Hung `--live` process** — the live loop blocks on stdin until EOF. Send Ctrl+D (Unix) / Ctrl+Z + Enter (Windows) to close the input stream, or Ctrl+C to abort.

**Ctrl+C left a partial file** — generation cleanups remove `*.part_*.mp3` chunks on cancel, but the final merged output is left if it had already been written.

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

Built on **edge-tts** (Microsoft Edge voices), **pydub** + **soundfile** + **ffmpeg** (audio merge / encode), **httpx** (async HTTP), **mutagen** (ID3 tags), **mcp** (Model Context Protocol SDK), **FastAPI** + **uvicorn** (REST server), **pynput** (Windows hotkeys).

**Author**: David Chincharashvili — davidchincharashvili@gmail.com — [github.com/DavidTbilisi/TTS](https://github.com/DavidTbilisi/TTS)
