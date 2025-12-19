#!/bin/bash
# Complete setup for Git Bash - uses .venv properly

set -e  # Exit on error

echo "🚀 TTS_ka Setup for Git Bash"
echo "================================"
echo ""

# Get absolute path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Define venv paths
VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
VENV_PIP="$VENV_DIR/Scripts/pip.exe"

# Check Python
echo "📍 Checking Python..."
python --version || { echo "❌ Python not found"; exit 1; }

# Create venv if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv "$VENV_DIR"
fi

# Activate
echo "🔌 Activating virtual environment..."
source "$VENV_DIR/Scripts/activate"
export PATH="$SCRIPT_DIR/$VENV_DIR/Scripts:$PATH"

# Verify venv python
echo "✓ Using: $($VENV_PYTHON --version)"
echo "✓ Location: $VENV_PYTHON"

# Upgrade pip
echo ""
echo "⬆️  Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip -q

# Install runtime dependencies
echo ""
echo "📦 Installing runtime dependencies..."
"$VENV_PYTHON" -m pip install edge-tts pyperclip -q
echo "✓ edge-tts installed"

# Install package in editable mode
echo ""
echo "📦 Installing TTS_ka package..."
"$VENV_PYTHON" -m pip install -e ./src -q
echo "✓ Package installed"

# Install dev tools
echo ""
echo "🛠️  Installing development tools..."
"$VENV_PYTHON" -m pip install -r requirements-dev.txt -q
echo "✓ black, flake8, isort, mypy, pytest installed"

# Verify installation
echo ""
echo "✅ Verifying installation..."
"$VENV_PYTHON" -c "from TTS_ka.core import VOICES; print('✓ TTS_ka core:', list(VOICES.keys()))"
"$VENV_PYTHON" -c "import edge_tts; print('✓ edge-tts:', edge_tts.__version__)"
"$VENV_PYTHON" -c "import black; print('✓ black:', black.__version__)"
"$VENV_PYTHON" -c "import pytest; print('✓ pytest:', pytest.__version__)"

echo ""
echo "================================"
echo "✅ Setup Complete!"
echo "================================"
echo ""
echo "To activate venv:"
echo "  source activate.sh"
echo ""
echo "To run the app:"
echo "  python -m TTS_ka 'Hello world' --lang en"
echo ""
echo "Output saved to: .venv/data.mp3"

