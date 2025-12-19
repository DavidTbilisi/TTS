.PHONY: help install test lint format clean build run-example

help:  ## Show this help message
	@echo "TTS_ka Development Makefile"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies in development mode
	pip install -e .
	pip install -r requirements-dev.txt
	pip install -r requirements-test.txt

test:  ## Run test suite
	pytest -v

test-quick:  ## Run tests without slow integration tests
	pytest -v -m "not integration"

test-coverage:  ## Run tests with coverage report
	pytest --cov=src/TTS_ka --cov-report=html --cov-report=term

lint:  ## Run linters (black, isort, flake8, mypy)
	bash lint.sh

format:  ## Format code with black and isort
	black src/ tests/ --line-length 100
	isort src/ tests/ --profile black

clean:  ## Remove build artifacts, cache, and temporary files
	rm -rf dist/ build/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .tox htmlcov
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -f .ff_concat.txt .part_*.mp3 data.mp3 data_temp.mp3 example_out.mp3

build:  ## Build distribution packages
	python -m build

run-example:  ## Run the example API script
	python examples/example_api.py

# Usage examples
example-short:  ## Generate short text example (direct)
	python -m TTS_ka "Hello world! This is a quick test." --lang en --no-play

example-long:  ## Generate long text example (streaming)
	python -m TTS_ka "This is a longer example text that will be chunked and processed in parallel for maximum speed." --lang en --stream --no-play

example-georgian:  ## Generate Georgian text example
	python -m TTS_ka "გამარჯობა მსოფლიო" --lang ka --no-play

setup-dev:  ## Complete development environment setup
	python -m venv .venv
	. .venv/bin/activate && make install

verify:  ## Run all checks (format, lint, test)
	make format
	make lint
	make test

