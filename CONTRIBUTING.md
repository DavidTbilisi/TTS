# Contributing to TTS_ka

Thank you for your interest in contributing to TTS_ka! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites
- Python 3.8 or higher
- Git
- Make (optional, but recommended)

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/DavidTbilisi/TTS.git
cd TTS

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
make install
# Or manually:
pip install -e .
pip install -r requirements-dev.txt
pip install -r requirements-test.txt

# Install pre-commit hooks
pre-commit install
```

## Development Workflow

### 1. Make Your Changes

Follow the architecture principles:
- **Keep it minimal**: Don't add unnecessary abstraction layers
- **Single responsibility**: Each module should have one clear purpose
- **Sanitize all inputs**: Use `sanitize_text()` before any text generation
- **Preserve public API**: Don't break existing CLI commands or public functions

### 2. Format Your Code

```bash
make format
# Or manually:
black src/ tests/ --line-length 100
isort src/ tests/ --profile black
```

### 3. Run Linters

```bash
make lint
# Or manually:
bash lint.sh
```

All checks must pass:
- ✅ Black (code formatting)
- ✅ isort (import ordering)
- ✅ flake8 (style checking)
- ✅ mypy (type checking)

### 4. Run Tests

```bash
make test
# Or for quick tests:
make test-quick
# Or with coverage:
make test-coverage
```

### 5. Commit Your Changes

```bash
git add .
git commit -m "Brief description of changes"
```

Pre-commit hooks will automatically run formatters and linters.

## Code Standards

### Python Style
- **Line length**: 100 characters (enforced by Black)
- **Imports**: Organized by isort (stdlib, third-party, local)
- **Type hints**: Required for all public functions
- **Docstrings**: Required for all public modules, classes, and functions

### Architecture Rules

From `.github/copilot-instructions.md`:

1. **Do not break CLI compatibility**
2. **Do not rename public facade functions**
3. **Prefer consolidation over proliferation**
4. **If a module has no clear responsibility, remove or merge it**
5. **Update Mermaid diagrams and docs after code changes**

### Module Organization

- `cli.py`: Unified CLI with argparse (synth/ultra/list-voices)
- `audio.py`: Core audio generation and playback
- `fast_audio.py`: Optimized HTTP-based generation
- `ultra_fast.py`: Parallel generation orchestration
- `chunker.py`: Pure text splitting functions
- `chunking.py`: High-level chunking logic/heuristics
- `not_reading.py`: Text sanitization (mandatory in all paths)
- `parallel.py`: Parallel chunk processing utilities
- `streaming_player.py`: Streaming playback support

## Testing Guidelines

### Writing Tests

1. **Unit tests**: Test individual functions in isolation
2. **Integration tests**: Test end-to-end workflows
3. **Use fixtures**: Leverage pytest fixtures in `conftest.py`
4. **Mock external dependencies**: Patch network calls, file I/O

Example:
```python
import pytest
from TTS_ka import sanitize_text

def test_sanitize_removes_urls():
    """Test URL removal from text."""
    text = "Check out https://example.com for more info"
    result = sanitize_text(text)
    assert "https" not in result
```

### Test Coverage

Maintain high test coverage:
- Core modules: >90%
- CLI/integration: >80%
- Overall: >85%

## Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature`
3. **Make your changes** following the guidelines above
4. **Run all checks**: `make verify`
5. **Push to your fork**: `git push origin feature/your-feature`
6. **Open a Pull Request** with:
   - Clear description of changes
   - Reference to related issues (if any)
   - Test results/coverage report
   - Screenshots/examples (if applicable)

### PR Checklist

- [ ] Code follows style guidelines (Black + isort)
- [ ] All linters pass (flake8 + mypy)
- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated (for notable changes)
- [ ] No breaking changes to public API (or clearly documented)

## Common Tasks

### Running Examples

```bash
make run-example
make example-short
make example-long
make example-georgian
```

### Cleaning Up

```bash
make clean  # Remove all build artifacts and cache
```

### Building Distribution

```bash
make build  # Creates wheel and sdist in dist/
```

## Getting Help

- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions
- **Documentation**: Check `docs/architecture.md` for system design

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's technical standards

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to TTS_ka!** 🎉

