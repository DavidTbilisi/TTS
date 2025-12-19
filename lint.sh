#!/usr/bin/env bash
# Format and lint script for the TTS project

set -e

echo "🎨 Running Black formatter..."
black src/ tests/ --line-length 100

echo "📦 Running isort..."
isort src/ tests/ --profile black

echo "🔍 Running flake8..."
flake8 src/ tests/

echo "🔎 Running mypy..."
mypy src/TTS_ka/ --ignore-missing-imports

echo "✅ All checks passed!"

