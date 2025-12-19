#!/bin/bash
# Setup script for Git Bash

echo "🚀 Setting up TTS_ka development environment (Git Bash)..."

# Check Python version
echo ""
echo "📍 Checking Python version..."
python --version

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python -m venv .venv
else
    echo ""
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "🔌 Activating virtual environment..."
source .venv/Scripts/activate

# Upgrade pip
echo ""
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install the package
echo ""
echo "📦 Installing TTS_ka package..."
pip install -e ./src --quiet

# Install runtime dependencies
echo ""
echo "📦 Installing runtime dependencies..."
pip install -r src/requirements.txt --quiet

# Install dev dependencies
echo ""
echo "🛠️  Installing development tools..."
pip install -r requirements-dev.txt --quiet

# Install test dependencies
if [ -f "requirements-test.txt" ]; then
    echo ""
    echo "🧪 Installing test dependencies..."
    pip install -r requirements-test.txt --quiet
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Quick commands:"
echo "  • Activate venv:  source activate.sh"
echo "  • Run app:        python -m TTS_ka 'Hello' --lang en"
echo "  • Format code:    black src/ tests/"
echo "  • Lint code:      flake8 src/ tests/"
echo "  • Run tests:      pytest"
echo "  • Quick lint:     ./lint.sh"
echo ""
echo "📖 See DEVELOPMENT.md for full guide"

