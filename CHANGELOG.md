# Changelog

All notable changes to TTS_ka will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2024-12-19

### 🎯 Major Refactoring & Cleanup

#### Added
- Comprehensive test suite with >85% coverage
- Makefile for common development tasks
- CONTRIBUTING.md with detailed development guidelines
- CLEANUP_SUMMARY.md documenting architectural improvements
- LINT_RESULTS.md documenting code quality status
- Enhanced .gitignore with comprehensive patterns

#### Changed
- **Architecture Simplification**: Removed redundant `core.py` and `facades.py` layers
- **Unified CLI**: Consolidated CLI into single `cli.py` with subcommands (synth/ultra/list-voices)
- **Module Separation**: Clear distinction between `chunker.py` (pure splitting) and `chunking.py` (high-level logic)
- **Sanitization**: Made `sanitize_text()` mandatory in all generation paths
- **Streaming**: Updated streaming to fall back gracefully when VLC not available
- **Type Safety**: Added comprehensive type annotations (mypy passes with 0 errors)
- **Code Quality**: All code formatted with Black and isort

#### Removed
- **Files Deleted** (~30+ files):
  - Removed `core.py` (redundant orchestration)
  - Removed `facades.py` (unnecessary wrapper)
  - Removed `help_system.py` (functionality in `simple_help.py`)
  - Removed all test artifacts (*.mp3, *.ahk, temp files)
  - Removed redundant documentation (5 MD files)
  - Removed `test_facades.py`
  - Cleaned all __pycache__ directories

- **Code Reduction**: ~720 lines of redundant code removed

#### Fixed
- Import organization (all imports at top of files)
- Unused imports removed (ThreadPoolExecutor, sys, Dict, etc.)
- Bare except clauses replaced with specific Exception
- Mypy type errors (SimpleArgs → argparse.Namespace)
- Boolean return type issues
- Example code updated to use new public API

### 📊 Code Quality Metrics

- **Mypy**: ✅ PASSING (0 errors)
- **Black**: ✅ Code formatted
- **isort**: ✅ Imports organized  
- **flake8**: ⚠️ Style warnings only (acceptable)
- **Test Coverage**: >85%
- **Module Count**: 14 essential modules (down from 17)

## [1.0.0] - 2024-12-18

### Initial Release

#### Features
- Ultra-fast parallel text-to-speech generation
- Support for Georgian (ka), Russian (ru), and English (en)
- Smart chunking for long texts
- Streaming playback support
- Clipboard integration
- Auto-optimization (turbo mode)
- CLI with multiple commands
- Rich progress display
- Fallback audio generation

#### Supported Languages
- 🇬🇪 Georgian (ka-GE-EkaNeural)
- 🇷🇺 Russian (ru-RU-SvetlanaNeural)
- 🇬🇧 English (en-GB-SoniaNeural)

#### Performance
- 6-15 seconds for 1000 words (vs 25+ seconds traditional)
- Up to 8 parallel workers
- HTTP/2 optimization
- Connection pooling

---

## Version History

- **1.1.0** (2024-12-19): Major refactoring, cleanup, and quality improvements
- **1.0.0** (2024-12-18): Initial public release

[1.1.0]: https://github.com/DavidTbilisi/TTS/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/DavidTbilisi/TTS/releases/tag/v1.0.0

