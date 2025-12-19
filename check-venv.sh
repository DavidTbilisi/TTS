#!/bin/bash
# Simple test to verify .venv setup

echo "Testing .venv setup..."
echo ""

# Use venv python directly
VENV_PY=".venv/Scripts/python.exe"

if [ ! -f "$VENV_PY" ]; then
    echo "❌ .venv/Scripts/python.exe not found"
    echo "Run: python -m venv .venv"
    exit 1
fi

echo "✓ Found venv Python"
"$VENV_PY" --version

echo ""
echo "Checking packages..."
"$VENV_PY" -c "import edge_tts; print('✓ edge-tts:', edge_tts.__version__)" 2>/dev/null || echo "✗ edge-tts not installed"
"$VENV_PY" -c "import pyperclip; print('✓ pyperclip installed')" 2>/dev/null || echo "✗ pyperclip not installed"
"$VENV_PY" -c "import black; print('✓ black:', black.__version__)" 2>/dev/null || echo "✗ black not installed"
"$VENV_PY" -c "import pytest; print('✓ pytest installed')" 2>/dev/null || echo "✗ pytest not installed"

echo ""
echo "Checking TTS_ka..."
"$VENV_PY" -c "from TTS_ka.core import VOICES; print('✓ TTS_ka OK - Languages:', list(VOICES.keys()))" 2>/dev/null || echo "✗ TTS_ka not installed - run: $VENV_PY -m pip install -e ./src"

echo ""
echo "To install missing packages:"
echo "  $VENV_PY -m pip install edge-tts pyperclip"
echo "  $VENV_PY -m pip install -r requirements-dev.txt"
echo "  $VENV_PY -m pip install -e ./src"

