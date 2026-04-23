# TTS_ka 🚀 Ultra-Fast Text-to-Speech

**Ultra-fast text-to-speech** (CLI + optional **desktop GUI**): smart chunking, parallel generation, clipboard input, optional streaming playback, and a **`--check-deps`** sanity check for ffmpeg and players. **Auto-optimized by default.** Languages: **Georgian (🇬🇪)**, **Russian (🇷🇺)**, **English (🇬🇧)**.

> ✨ **Simplified UX**: Auto-optimization is now enabled by default. Just specify `--lang` and go!

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## ✨ Features

- 🚀 **Ultra-Fast Generation**: 6-15 seconds for 1000 words (vs 25+ seconds traditional)
- 🔊 **Streaming Playback**: Audio starts playing while still generating (NEW!)
- 🧠 **Smart Chunking**: Automatic text splitting for optimal performance  
- ⚡ **Parallel Processing**: Multi-threaded generation with up to 8 workers
- 📋 **Clipboard Integration**: Direct clipboard-to-speech workflow
- 🎯 **Auto-Optimization**: Turbo mode automatically optimizes all settings
- 🎵 **High-Quality Voices**: Premium neural voices for all languages
- 📁 **File Support**: Process text files directly
- 🔄 **Real-time Playback**: Automatic audio playback with system player
- **Dependency check**: `python -m TTS_ka --check-deps` reports ffmpeg, streaming players (VLC/mpv/ffplay), and Python packages; exits with code 1 if critical pieces are missing.
- **Optional GUI**: `TTS_ka-gui` opens a small window to paste text, choose language, and speak (stdlib **tkinter**).
- **Speakable text cleanup**: Before TTS, the pipeline rewrites noisy input so the voice does not read raw syntax — fenced and inline code, URLs, shebang lines, HTML-like tags, file extensions (for example `.ts` → “TypeScript”), common IT acronyms (HTTPS, JSON, API, …), math symbols (for example `⇒` → “implies”), and very long digit runs. Implemented in `TTS_ka.not_reading` (`replace_not_readable`).
- **Ctrl+C**: Cancels generation and stops active streaming playback (including VLC) without waiting for the full join timeout.

## 🎯 Quick Start

### 1. Installation

```bash
# Install from PyPI (recommended)
pip install TTS_ka

# Or install from source
git clone https://github.com/DavidTbilisi/TTS.git
cd TTS
pip install -e .
```

Verify **ffmpeg** is on your `PATH` (required for merging chunks and reliable MP3 handling). Then:

```bash
python -m TTS_ka --check-deps
```

You should see `[OK]` for **edge-tts**, **pydub**, and **ffmpeg**. A streaming player (VLC, mpv, …) is optional unless you use `--stream`.

**Optional desktop window** (paste → Speak):

```bash
TTS_ka-gui
# or: python -m TTS_ka.gui
```

On Debian/Ubuntu, install Tk if needed: `sudo apt install python3-tk`.

### 2. Basic Usage (Auto-Optimized by Default)

```bash
# Ultra-fast generation with auto-optimization (default behavior)
python -m TTS_ka "Hello, how are you today?" --lang en

# Georgian text with automatic optimization
python -m TTS_ka "გამარჯობა, როგორ ხართ?" --lang ka

# Russian text with smart chunking
python -m TTS_ka "Привет, как дела?" --lang ru
```

### 3. Clipboard Workflow (FASTEST)

```bash
# Copy any text, then run (fastest workflow):
python -m TTS_ka clipboard --lang en

# For different languages:
python -m TTS_ka clipboard --lang ka  # Georgian
python -m TTS_ka clipboard --lang ru  # Russian
```

### 4. File Processing

```bash
# Process text files directly (auto-optimized)
python -m TTS_ka document.txt --lang en

# Long files with custom settings
python -m TTS_ka large_file.txt --chunk-seconds 30 --parallel 6 --lang ru
```

### 5. Demo: ~60 seconds in the terminal

```text
$ pip install TTS_ka
$ python -m TTS_ka --check-deps
TTS_ka dependency check
========================================
  [OK]  edge-tts   import ok (…)
  [OK]  pydub      import ok (…)
  [OK]  ffmpeg     ffmpeg version …
  [opt] soundfile  optional …            # faster merges if installed
  [OK]  streaming player  first match: vlc   # [opt] if none — only needed for --stream

$ python -m TTS_ka "Hello from TTS_ka" --lang en
OPTIMIZED MODE - English
…
⚡ Completed in …s (direct)

$ python -m TTS_ka clipboard --lang ka    # after copying Georgian text to the clipboard
…

$ TTS_ka-gui    # optional: paste text in the window and click Speak
```

*(Timings and exact log lines depend on your machine and network.)*

## 📖 Complete Usage Guide

### Command Syntax
```
python -m TTS_ka [TEXT_SOURCE] [OPTIONS]
```

### Text Sources
- **Direct text**: `"Your text here"`
- **Clipboard**: `clipboard` (copy text first)
- **File path**: `file.txt`, `document.md`, etc.

### Essential Options

| Option | Description | Examples |
|--------|-------------|----------|
| `--lang` | `ka` Georgian (female), `ka-m` Georgian (male), `ru`, `en` | `--lang ka` |
| `-o`, `--output` | Output MP3 path (default `data.mp3`) | `-o speech.mp3` |
| `--stream` | 🆕 Enable streaming playback (audio starts while generating) | `--stream` |
| `--chunk-seconds` | Chunk size in seconds (0=auto, 20-60 optimal) | `--chunk-seconds 30` |
| `--parallel` | Workers (0=auto, 2-8 recommended) | `--parallel 6` |
| `--no-play` | Skip automatic audio playback | `--no-play` |
| `--no-gui` | With `--stream`: headless VLC (dummy UI). Default is one GUI window on Windows. | `--stream --no-gui` |
| `--no-turbo` | Disable auto-optimization (legacy mode) | `--no-turbo` |
| `--help-full` | Show comprehensive help with examples | `--help-full` |
| `-V`, `--version` | Print version, Python, platform, and PyPI package metadata | `--version` |
| `--check-deps` | Print dependency status (ffmpeg, players, Python stack); exit code 1 if critical deps missing | `--check-deps` |

### Text cleanup rules (summary)

| Kind of input | What you hear instead |
|----------------|----------------------|
| `` ```code``` `` / `` `inline` `` | Short phrases like “omitted fenced code block” / “omitted inline code snippet” |
| `https://…` / `www.…` | “omitted hyperlink” |
| `#!/usr/bin/env python` | “omitted script shebang line” |
| `<div>…</div>`-style tags | “omitted markup tag” |
| `file.ts`, `app.py` | Spoken language or format name (TypeScript, Python, …) |
| `API`, `HTTPS`, `JSON`, … | Letter-by-letter or expanded forms (A P I, H T T P S, …) |
| `=>`, `≤`, `∞`, … | Words (“implies”, “less than or equal to”, “infinity”, …) |
| 7+ digit numbers | “a large number” |

Chunk playback order matches document order even when chunks finish generating in parallel.

## 🏃‍♂️ Performance Examples

### Speed Comparison (1000 words)
- **Traditional TTS**: 25-40 seconds
- **TTS_ka Direct**: 15-25 seconds  
- **TTS_ka Turbo**: 8-15 seconds
- **TTS_ka Chunked**: 6-12 seconds ⚡
- **TTS_ka Streaming**: 🔊 2-3 seconds to first audio (NEW!)

### 🆕 Streaming Playback - Audio Starts Immediately!

The new streaming feature starts playing audio within **2-3 seconds** while the rest continues generating in the background. This provides an **85-90% reduction in perceived wait time**!

**Quick Usage:**
```bash
# Basic streaming - audio starts almost instantly!
python -m TTS_ka "Your long text..." --lang en --stream

# From file with streaming
python -m TTS_ka article.txt --lang ka --stream

# Clipboard with streaming (fastest workflow)
python -m TTS_ka clipboard --stream
```

**How It Works:**
1. Text is split into chunks (if needed)
2. Chunks generate in parallel (2-8 workers)
3. **First chunk plays quickly** (~2-3 seconds); with VLC (default on Windows), **one window** builds a playlist **in text order** as chunks finish (`--no-gui` uses a headless session). Set `TTS_KA_VLC_RC=0` to fall back to launching VLC once per chunk instead of one remote-control session.
4. Remaining chunks continue generating in background
5. Final merged audio file is saved

**Performance:**
- **Without streaming**: Wait 10-30+ seconds for all audio
- **With streaming**: Hear audio in 2-3 seconds ⚡
- **Platform support**: Windows, Linux, macOS

**Advanced Streaming:**
```bash
# Custom chunking for optimal streaming
python -m TTS_ka longtext.txt --stream --chunk-seconds 25 --parallel 6

# Streaming without final playback
python -m TTS_ka text.txt --stream --no-play
```

### Real-World Examples

```bash
# 1. Quick phrases (instant generation)
python -m TTS_ka "Thank you very much!" --lang en
# ⚡ Completed in 2.3s (optimized)

# 2. Medium text (paragraph)
python -m TTS_ka "Lorem ipsum dolor sit amet..." --lang en  
# ⚡ Completed in 5.7s (direct)

# 3. Long document (chunked processing)
python -m TTS_ka large_document.txt --lang en
# Strategy: chunked generation, 6 workers
# ⚡ Completed in 12.4s (chunked)

# 4. Clipboard workflow (daily usage)
python -m TTS_ka clipboard --lang ka
# OPTIMIZED MODE - Georgian
# Processing: 45 words, 287 characters
# ⚡ Completed in 4.1s
```

## 🌍 Language Support

| Language | Code | Voice Quality | Speed | Example |
|----------|------|---------------|-------|---------|
| **Georgian** 🇬🇪 | `ka` | Neural (Eka, female) | Fast | `--lang ka` |
| **Georgian** 🇬🇪 | `ka-m` | Neural (Giorgi, male) | Fast | `--lang ka-m` |
| **Russian** 🇷🇺 | `ru` | High Quality | Very Fast | `--lang ru` |
| **English** 🇬🇧 | `en` | Premium Neural | Maximum | `--lang en` |

### Voice Details
- **Georgian (female)**: `ka-GE-EkaNeural` — `--lang ka`
- **Georgian (male)**: `ka-GE-GiorgiNeural` — `--lang ka-m`
- **Russian**: `ru-RU-SvetlanaNeural` - High-quality female voice  
- **English**: `en-GB-SoniaNeural` - British English neural voice

## ⚙️ Advanced Usage

### Custom Optimization

```bash
# Manual chunking for very long texts
python -m TTS_ka book_chapter.txt --chunk-seconds 45 --parallel 4 --lang en

# Maximum parallelization (for powerful systems)
python -m TTS_ka large_text.txt --parallel 8 --lang ru

# Batch processing (no audio playback)  
python -m TTS_ka document.txt --no-play --lang ka

# Legacy mode (disable auto-optimization)
python -m TTS_ka "text" --no-turbo --lang en
```

### Workflow Integration

```bash
# Create alias for daily use
alias speak='python -m TTS_ka clipboard --lang en'

# Windows batch file (speak.bat)
@echo off
python -m TTS_ka clipboard --lang en

# Read web articles (with browser copy)
# 1. Copy article text
# 2. Run: python -m TTS_ka clipboard --lang en
```

## 🔧 Installation & Requirements

### System Requirements
- **Python**: 3.9+ (required: async CLI, `httpx`, and PEP 639 build metadata)
- **OS**: Windows, macOS, Linux
- **Memory**: 256MB+ available RAM
- **Network**: Internet connection for voice synthesis

### Dependencies

**Required (same as `pip install TTS_ka`):**
```bash
pip install "edge-tts>=7.2.7"      # Core TTS engine
pip install pydub>=0.25.1        # Audio processing
pip install tqdm>=4.65.0         # Progress bars
pip install "httpx>=0.28.1"      # Async HTTP (CLI)
```

**System Requirements:**
- **FFmpeg**: Required for audio processing
  - Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`

### Complete Installation

```bash
# Method 1: PyPI installation (simplest)
pip install TTS_ka

# Method 2: Development installation
git clone https://github.com/DavidTbilisi/TTS.git
cd TTS
pip install -e .

# Method 3: Manual dependencies
pip install "edge-tts>=7.2.7" pydub tqdm "httpx>=0.28.1"

# Verify installation
python -m TTS_ka "Installation successful!" --turbo --lang en
```

## 🎮 AutoHotkey Integration (Windows)

Bundled scripts live under [`extras/autohotkey/`](extras/autohotkey/): a **commented template** (`TTS_ka_hotkeys.ahk`) and a **Startup installer** (`Install-TTS_ka-Hotkeys.ps1`). Defaults match the old readme: **Alt+E** / **Alt+R** / **Alt+X** for English, Russian, Georgian (clipboard).

### One-time install (recommended)

1. Install [AutoHotkey v2](https://www.autohotkey.com/) (64-bit is typical).
2. From the **repository root**, run PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\extras\autohotkey\Install-TTS_ka-Hotkeys.ps1
```

This copies `TTS_ka_hotkeys.ahk` into your user **Startup** folder and launches it. Re-run the same command after you edit the script in the repo to refresh the Startup copy.

Options:

| Flag | Meaning |
|------|--------|
| `-WhatIf` | Print paths only; no copy/start |
| `-NoStart` | Copy to Startup but do not launch now |
| `-Uninstall` | Remove the script from Startup |

3. Confirm Python works in a new Command Prompt: `python -m TTS_ka --version` (use the same `python` / `py` you set in `g_Python` inside the `.ahk` file).

### Manual install

1. Copy `extras/autohotkey/TTS_ka_hotkeys.ahk` anywhere (e.g. `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`).
2. Double-click the `.ahk` file (or right-click → Run with AutoHotkey).

### Customising

Open `TTS_ka_hotkeys.ahk` in a text editor. At the top, set **`g_Python`**, **`g_CopyFirst`** (send Ctrl+C before TTS), **`g_ExtraFlags`** (e.g. `--stream`), and **`g_CmdKeepOpen`**. Further down, many hotkeys and variants are **commented** with `;` — delete the semicolon on the lines you want.

### Daily workflow

1. **Copy** (or highlight and set `g_CopyFirst := true`) your text  
2. **Alt+E** / **Alt+R** / **Alt+X** → speech in that language  
3. Right-click the **green H** tray icon → Reload / Exit

### Select text → “Read” → language (Windows limits)

**Inside Chrome, Edge, Word, etc.**, Windows does **not** let third parties add a “Read” item to the **native** right‑click menu for a text selection (that menu is drawn by each app). Two supported options:

1. **AutoHotkey (in-app)** — with `TTS_ka_hotkeys.ahk` loaded: **select text**, then either press the **Menu / Apps** key (next to Right Ctrl) or **Ctrl+Alt+right‑click**; a small **language menu** appears at the cursor (the script sends Ctrl+C first). Comment those lines in the script if they clash with other tools.

2. **Explorer / Desktop context menu** — after **Ctrl+C**, right‑click **empty** space in a folder window or on the **desktop**, then **Read with TTS_ka** → choose a language (nested menu). Installer:

```powershell
powershell -ExecutionPolicy Bypass -File .\extras\windows\context_menu\Install-TTS_ka-ContextMenu.ps1
```

| Flag | Meaning |
|------|--------|
| `-FlatMenu` | One top-level item per language instead of a submenu |
| `-Languages @('en','ru')` | Subset of languages (PowerShell array) |
| `-IncludeTextFiles` | Add “read this file” on `.txt` right‑click |
| `-Uninstall` | Remove TTS_ka menu entries |

On **Windows 11**, classic shell entries may appear under **Show more options**.

## 🔍 Troubleshooting

### Common Issues

**1. "No module named 'edge_tts'"**
```bash
pip install "edge-tts>=7.2.7"
```

**2. "FFmpeg not found"**
```bash
# Windows: Download and add to PATH
# macOS: brew install ffmpeg  
# Linux: sudo apt install ffmpeg
```

**3. Slow generation**
```bash
# Auto-optimization is enabled by default
python -m TTS_ka "text" --lang en

# Reduce parallel workers if network issues
python -m TTS_ka "text" --parallel 2 --lang en

# Use legacy mode only if needed
python -m TTS_ka "text" --no-turbo --lang en
```

**4. Empty clipboard**
```bash
# Ensure text is copied first
# Then run: python -m TTS_ka clipboard --turbo --lang en
```

**5. `403` / `Invalid response status` (HTTP or edge-tts)**
```bash
# Microsoft rotates access; upgrade edge-tts (includes updated websocket tokens)
pip install -U "edge-tts>=7.2.7"

# Optional: skip the unofficial Bing HTTP path and use edge-tts only
set TTS_KA_SKIP_HTTP=1   # Windows CMD
# export TTS_KA_SKIP_HTTP=1   # macOS / Linux

# Optional: log when the app falls back from HTTP to edge-tts (off by default)
set TTS_KA_VERBOSE=1

# If many parallel chunks still fail, reduce workers
python -m TTS_ka "your long text" --lang en --parallel 2
```

**6. Streaming / VLC (Windows)**  
- Default: one VLC window with a growing playlist (TCP remote control).  
- `TTS_KA_VLC_RC=0`: disable that mode and use one VLC process per chunk (legacy).

**7. Ctrl+C**  
Press **Ctrl+C** to cancel synthesis and stop streaming playback; partial part files are cleaned up.

### Performance Optimization

**For Maximum Speed:**
```bash
# Use these exact settings for best performance (auto-optimized by default)
python -m TTS_ka clipboard --chunk-seconds 30 --parallel 6 --lang en
```

**For System with Limited Resources:**
```bash
# Reduce workers and chunk size
python -m TTS_ka text --parallel 2 --chunk-seconds 60 --lang en
```

## 📊 Performance Benchmarks

### Text Length vs Generation Time

| Words | Direct Mode | Turbo Mode | Chunked (6 workers) |
|-------|-------------|------------|---------------------|
| 10-50 | 2-4s | 1-3s | 2-4s |
| 100-300 | 8-12s | 5-8s | 4-6s |
| 500-1000 | 18-25s | 12-15s | 8-12s |
| 1000+ | 30-45s | 18-25s | 10-18s |

### Optimal Settings by Text Length

```bash
# Short text (< 100 words): Direct generation (auto-optimized)
python -m TTS_ka "short text" --lang en

# Medium text (100-500 words): Auto-optimized mode
python -m TTS_ka medium_text.txt --lang en  

# Long text (500+ words): Chunked processing (auto-detected)
python -m TTS_ka long_text.txt --chunk-seconds 30 --parallel 6 --lang en
```

## 🚀 Examples & Use Cases

### Daily Workflows

**1. Article Reading**
```bash
# Copy web article → instant speech
python -m TTS_ka clipboard --lang en
```

**2. Document Processing**  
```bash
# Process research papers, books, etc.
python -m TTS_ka research_paper.pdf.txt --lang en
```

**3. Language Learning**
```bash
# Practice pronunciation with different languages
python -m TTS_ka "სწავლობდი ქართულს" --lang ka
python -m TTS_ka "Learning Russian язык" --lang ru
```

**4. Accessibility**
```bash
# Screen reader alternative
python -m TTS_ka clipboard --no-play --lang en > audio_file.mp3
```

### Batch Processing

```bash
# Process multiple files
for file in *.txt; do
    python -m TTS_ka "$file" --no-play --lang en
done

# Windows batch processing
for %f in (*.txt) do python -m TTS_ka "%f" --no-play --lang en
```

## 🛠️ Advanced Configuration

### Environment Variables
```bash
# Set default language
export TTS_DEFAULT_LANG=ka

# Set default mode  
export TTS_DEFAULT_MODE=turbo

# Custom output directory
export TTS_OUTPUT_DIR=/path/to/audio/files
```

### Configuration File
Create `~/.tts_config.json`:
```json
{
    "default_lang": "en",
    "turbo_mode": true,
    "chunk_seconds": 30,
    "parallel_workers": 6,
    "auto_play": true
}
```

## 🔌 API Integration

### Python Script Integration
```python
#!/usr/bin/env python3
import subprocess
import sys

def text_to_speech(text, lang="en", turbo=True):
    """Convert text to speech using TTS_ka"""
    cmd = [
        "python", "-m", "TTS_ka", 
        text, 
        "--lang", lang
    ]
    if turbo:
        cmd.append("--turbo")
    
    subprocess.run(cmd)

# Usage
text_to_speech("Hello world!", "en")
text_to_speech("გამარჯობა!", "ka")
```

### Web Integration
```bash
# URL to speech (with curl + TTS_ka)
curl -s "https://example.com/article" | \
python -m TTS_ka /dev/stdin --turbo --lang en
```

## 📱 Mobile & Remote Usage

### SSH/Remote Usage
```bash
# Generate audio on remote server
ssh user@server "python -m TTS_ka 'Remote generation' --turbo --no-play"

# Download and play locally
scp user@server:data.mp3 ./remote_audio.mp3
```

### Docker Usage
```dockerfile
FROM python:3.9
RUN pip install TTS_ka
RUN apt-get update && apt-get install -y ffmpeg
ENTRYPOINT ["python", "-m", "TTS_ka"]
```

```bash
# Docker usage
docker run tts_container "Hello Docker!" --turbo --lang en
```

## 🎯 Tips & Best Practices

### Performance Tips
1. **Auto-optimization is enabled by default** - no flags needed!
2. **Use clipboard workflow** for fastest daily usage  
3. **Chunk long texts** with `--chunk-seconds 30`
4. **Optimize workers** with `--parallel 4-6` for most systems
5. **Pre-install FFmpeg** for best audio processing

### Quality Tips
1. **Georgian text**: Use `--lang ka` for best quality
2. **Mixed languages**: Process separately for optimal results
3. **Technical text**: Use shorter chunks (`--chunk-seconds 20`)
4. **Clean input**: Remove extra whitespace and formatting

### Workflow Tips
1. **Create aliases** for frequent commands
2. **Use hotkeys** (AutoHotkey on Windows)
3. **Batch process** large document collections
4. **Test settings** with small text first

## 📄 File Format Support

### Supported Input Formats
- **Text files**: `.txt`, `.md`, `.rst`  
- **Code files**: `.py`, `.js`, `.html` (extracts text)
- **Clipboard**: Any copied text
- **Direct input**: Command-line strings

### Output Format
- **Audio**: MP3 (high quality, compressed)
- **Bitrate**: 128kbps (optimal size/quality balance)
- **Sample Rate**: 24kHz (neural voice quality)

## 🔄 Updates & Maintenance

### Keeping Updated
```bash
# Update to latest version
pip install --upgrade TTS_ka

# Check current version  
python -m TTS_ka --version

# Update dependencies
pip install --upgrade edge-tts pydub tqdm httpx
```

### Health Check
```bash
# Test installation
python -m TTS_ka "System check" --turbo --lang en

# Verify FFmpeg  
ffmpeg -version

# Check Python version
python --version  # Should be 3.9+
```

## 🤝 Contributing

We welcome contributions! See our [GitHub repository](https://github.com/DavidTbilisi/TTS) for:

- **Bug reports** and feature requests
- **Code contributions** and pull requests  
- **Documentation** improvements
- **Language support** additions

### Development Setup
```bash
git clone https://github.com/DavidTbilisi/TTS.git
cd TTS
pip install -e ".[dev]"
pytest  # Run tests
```

## 📞 Support

### Getting Help
1. **Documentation**: Use `--help-full` for comprehensive help
2. **Issues**: Report bugs on [GitHub Issues](https://github.com/DavidTbilisi/TTS/issues)
3. **Discussions**: Join [GitHub Discussions](https://github.com/DavidTbilisi/TTS/discussions)

### Quick Diagnostics
```bash
# Check system compatibility  
python -m TTS_ka --help-full

# Test with minimal command
python -m TTS_ka "test" --turbo --lang en

# Verify FFmpeg installation
ffmpeg -version
```

## 📜 License & Credits

**License**: MIT License - see [LICENSE](LICENSE) file

**Credits**:
- **Edge-TTS**: Microsoft's edge-tts library for voice synthesis
- **PyDub**: Audio processing and manipulation  
- **FFmpeg**: Audio encoding and format conversion

**Author**: David Chincharashvili (davidchincharashvili@gmail.com)

---

⭐ **Star this project** on GitHub if you find it useful!  
🐛 **Report issues** to help improve the tool  
🤝 **Contribute** to make it even better
