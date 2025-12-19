# Quick Start Guide - Development Setup

## 🚀 One-Command Setup (Windows)

```powershell
.\setup.ps1
```

This will:
- Create virtual environment
- Install all dependencies
- Install dev tools (black, flake8, isort, mypy, pytest)
- Set up the project for development

## 📋 Manual Setup

### 1. Create virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install everything
```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Install package in editable mode
pip install -e ./src

# Install runtime dependencies
pip install -r src/requirements.txt

# Install dev tools
pip install -r requirements-dev.txt

# Install test dependencies  
pip install -r requirements-test.txt
```

## ✅ Verify Installation

```powershell
python test_rebuild.py
```

This will check:
- ✓ Core modules work
- ✓ Chunker works
- ✓ Dev tools installed (black, flake8, isort, mypy, pytest)

## 🎯 Quick Commands

### Run the app
```powershell
python -m TTS_ka "Hello world" --lang en
```

Output saved to: `.venv/data.mp3`

### Format and lint
```powershell
# All-in-one
.\lint.ps1

# Individual commands
black src/ tests/ --line-length 100
flake8 src/ tests/
isort src/ tests/
mypy src/TTS_ka/
```

### Run tests
```powershell
pytest
pytest --cov  # With coverage
```

## 📖 Documentation

- **DEVELOPMENT.md** - Full development guide
- **README.md** - User guide
- **src/requirements.txt** - Runtime dependencies
- **requirements-dev.txt** - Dev tool dependencies
- **requirements-test.txt** - Test dependencies

## 🛠️ Installed Dev Tools

| Tool | Purpose | Command |
|------|---------|---------|
| **black** | Code formatter | `black src/ tests/` |
| **flake8** | Linter | `flake8 src/ tests/` |
| **isort** | Import sorter | `isort src/ tests/` |
| **mypy** | Type checker | `mypy src/TTS_ka/` |
| **pytest** | Test runner | `pytest` |

## 📁 Project Structure

```
TTS/
├── src/TTS_ka/         # Main package
│   ├── cli.py          # CLI entry point
│   ├── core.py         # Core TTS functionality
│   ├── chunker.py      # Text chunking
│   └── parallel.py     # Parallel processing
├── tests/              # Test files
├── .venv/              # Virtual environment
│   └── data.mp3        # Default output location
├── requirements-dev.txt
├── pyproject.toml      # Tool configs
├── .flake8            # Flake8 config
└── lint.ps1           # Lint script
```

## 🎓 Next Steps

1. Read **DEVELOPMENT.md** for coding guidelines
2. Run `python test_rebuild.py` to verify setup
3. Try the app: `python -m TTS_ka "Hello" --lang en`
4. Make changes and run `.\lint.ps1` before committing
5. Write tests and run `pytest`

## ⚠️ Requirements

- **Python 3.10+**
- **edge-tts** (core dependency)
- **ffmpeg** (for merging long audio - optional, will use pydub if available)
- **pyperclip** (for clipboard support - optional)

