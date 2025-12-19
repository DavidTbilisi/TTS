# Quick setup script for TTS_ka development environment

Write-Host "🚀 Setting up TTS_ka development environment..." -ForegroundColor Cyan

# Check Python version
Write-Host "`n📍 Checking Python version..." -ForegroundColor Yellow
python --version

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "`n📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "`n✓ Virtual environment already exists" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "`n🔌 Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "`n⬆️  Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet

# Install the package
Write-Host "`n📦 Installing TTS_ka package..." -ForegroundColor Yellow
pip install -e ./src --quiet

# Install runtime dependencies
Write-Host "`n📦 Installing runtime dependencies..." -ForegroundColor Yellow
pip install -r src/requirements.txt --quiet

# Install dev dependencies
Write-Host "`n🛠️  Installing development tools..." -ForegroundColor Yellow
pip install -r requirements-dev.txt --quiet

# Install test dependencies
if (Test-Path "requirements-test.txt") {
    Write-Host "`n🧪 Installing test dependencies..." -ForegroundColor Yellow
    pip install -r requirements-test.txt --quiet
}

Write-Host "`n✅ Setup complete!" -ForegroundColor Green
Write-Host "`nQuick commands:" -ForegroundColor Cyan
Write-Host "  • Run app:      python -m TTS_ka 'Hello' --lang en"
Write-Host "  • Format code:  black src/ tests/"
Write-Host "  • Lint code:    flake8 src/ tests/"
Write-Host "  • Run tests:    pytest"
Write-Host "  • Quick lint:   .\lint.ps1"
Write-Host "`n📖 See DEVELOPMENT.md for full guide"

