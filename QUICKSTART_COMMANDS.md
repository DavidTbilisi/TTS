# TTS_ka Quick Start Guide

After all cleanup and improvements, here's how to use TTS_ka effectively.

---

## 🚀 Installation

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install in development mode
pip install -e .
```

---

## 📋 Common Commands

### Using Makefile (Recommended)

```bash
# Show all available commands
make help

# Development setup
make install              # Install all dependencies
make setup-dev           # Complete environment setup

# Testing
make test                # Run all tests
make test-quick          # Skip slow integration tests
make test-coverage       # Generate coverage report

# Code Quality
make lint                # Run all linters (black, isort, flake8, mypy)
make format              # Auto-format code

# Cleanup
make clean               # Remove build artifacts and cache

# Build
make build               # Create distribution packages

# Examples
make run-example         # Run API example
make example-short       # Quick CLI example
make example-long        # Streaming example
make example-georgian    # Georgian language example

# All-in-one
make verify              # Format + Lint + Test
```

---

## 🎯 CLI Usage

### Simple Mode (No Subcommand)

```bash
# Basic usage
python -m TTS_ka "Your text here" --lang en

# With output file
python -m TTS_ka "Text" --lang ru -o output.mp3

# Different languages
python -m TTS_ka "Hello" --lang en
python -m TTS_ka "Привет" --lang ru
python -m TTS_ka "გამარჯობა" --lang ka
```

### Synth Command (Lightweight)

```bash
# Simple synthesis
python -m TTS_ka synth "Text to speak" --lang en

# Custom output
python -m TTS_ka synth "Text" --lang ru --output my_audio.mp3

# Don't auto-play
python -m TTS_ka synth "Text" --lang en --no-play

# Adjust workers for long text
python -m TTS_ka synth "Long text..." --workers 8
```

### Ultra Command (Advanced)

```bash
# Auto-optimized (recommended)
python -m TTS_ka ultra "Long text here..." --lang en

# Streaming playback (audio plays while generating)
python -m TTS_ka ultra "Long text..." --stream

# Custom chunk size and workers
python -m TTS_ka ultra "Text..." --chunk-seconds 30 --parallel 8

# Disable auto-optimization
python -m TTS_ka ultra "Text..." --no-turbo

# From file
python -m TTS_ka ultra myfile.txt --lang en

# From clipboard
python -m TTS_ka ultra clipboard --lang ru
```

### List Voices

```bash
python -m TTS_ka list-voices
```

---

## 🐍 Python API Usage

### Basic Generation

```python
import asyncio
from TTS_ka import generate_audio, play_audio

async def main():
    # Generate audio file
    success = await generate_audio(
        text="Hello world!",
        language="en",
        output_path="output.mp3"
    )
    
    if success:
        print("Audio generated!")
        play_audio("output.mp3")

asyncio.run(main())
```

### With Text Sanitization

```python
import asyncio
from TTS_ka import generate_audio, sanitize_text

async def main():
    # Best practice: sanitize text first
    text = "Check out https://example.com for more!"
    clean_text = sanitize_text(text)  # Removes URLs, code, etc.
    
    await generate_audio(clean_text, "en", "output.mp3")

asyncio.run(main())
```

### Using CLI Programmatically

```python
from TTS_ka import main

# Call CLI with arguments
main(["ultra", "Hello world", "--lang", "en", "--no-play"])
```

---

## 🛠️ Development Commands

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_chunking.py

# Specific test
pytest tests/test_chunking.py::TestChunking::test_split_text_into_chunks_basic

# With output
pytest -v

# With coverage
pytest --cov=src/TTS_ka --cov-report=html

# Fast (skip slow tests)
pytest -m "not integration"
```

### Linting & Formatting

```bash
# Format code
black src/ tests/ --line-length 100
isort src/ tests/ --profile black

# Check style
flake8 src/ tests/

# Type check
mypy src/TTS_ka/ --ignore-missing-imports

# All checks
bash lint.sh
```

### Package Management

```bash
# Reinstall package
pip install -e . --force-reinstall --no-deps

# Uninstall
pip uninstall TTS_ka -y

# Build distribution
python -m build

# Install from wheel
pip install dist/tts_ka-*.whl
```

---

## 🔍 Debugging

### Check Installation

```python
# Verify imports
python -c "from TTS_ka import main, generate_audio; print('OK')"

# Check version
python -c "from TTS_ka import __version__; print(__version__)"

# List installed package
pip show TTS_ka
```

### Check Module Path

```python
import TTS_ka
print(TTS_ka.__file__)
```

### Verbose Mode

```bash
# Add -v for verbose pytest output
pytest -v

# Check what pytest collects
pytest --collect-only
```

---

## 📁 Project Structure

```
TTS_ka/
├── src/TTS_ka/          # Source code (14 modules)
│   ├── __init__.py      # Public API
│   ├── cli.py           # CLI commands
│   ├── audio.py         # Audio generation
│   ├── fast_audio.py    # Optimized HTTP
│   ├── ultra_fast.py    # Parallel processing
│   └── ...
├── tests/               # Test suite
├── examples/            # Usage examples
├── docs/                # Documentation
├── Makefile             # Development tasks
├── CONTRIBUTING.md      # Contribution guide
├── CHANGELOG.md         # Version history
└── requirements*.txt    # Dependencies
```

---

## 💡 Tips

1. **Use `make help`** to see all available commands
2. **Run `make verify`** before committing
3. **Check `CONTRIBUTING.md`** for development guidelines
4. **Use streaming mode** for long texts: `--stream`
5. **Auto-optimization works great** - just use `--lang`
6. **Sanitize text** with `sanitize_text()` for best results
7. **Use Makefile** for consistency across environments

---

## 📞 Support

- **Issues**: GitHub Issues
- **Docs**: `docs/architecture.md`
- **Examples**: `examples/example_api.py`
- **Contributing**: `CONTRIBUTING.md`

---

**Status**: ✅ Ready to use!

Run `make help` to get started.

