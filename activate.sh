#!/bin/bash
# Activate virtual environment in Git Bash

if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
    echo "✅ Virtual environment activated!"
    python --version
    echo "Python path: .venv/Scripts/python.exe"
    # Update PATH to prioritize venv
    export PATH="$(pwd)/.venv/Scripts:$PATH"
else
    echo "❌ .venv not found. Creating it now..."
    python -m venv .venv
    echo "✅ Created .venv. Now activating..."
    source .venv/Scripts/activate
    export PATH="$(pwd)/.venv/Scripts:$PATH"
    python --version
fi

