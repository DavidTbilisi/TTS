# PowerShell script for formatting and linting on Windows

Write-Host "🎨 Running Black formatter..." -ForegroundColor Cyan
python -m black src/ tests/ --line-length 100

Write-Host "`n📦 Running isort..." -ForegroundColor Cyan
python -m isort src/ tests/ --profile black

Write-Host "`n🔍 Running flake8..." -ForegroundColor Cyan
python -m flake8 src/ tests/

Write-Host "`n🔎 Running mypy..." -ForegroundColor Cyan
python -m mypy src/TTS_ka/ --ignore-missing-imports

Write-Host "`n✅ All checks passed!" -ForegroundColor Green

