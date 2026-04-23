#!/bin/bash

set -e  # Exit on error

# Local editable install (no version bump, no PyPI, no auto-commit).
if [ "${1:-}" = "local" ] || [ "${1:-}" = "install" ]; then
    echo "Installing TTS_ka in editable mode from $(pwd) ..."
    py -m pip install -e ".[test]"
    echo "Done. Try: py -m TTS_ka --version"
    exit 0
fi

if ! git diff-index --quiet HEAD --; then
    # On Windows, files named 'nul' (reserved device name) can cause
    # "invalid path 'nul'" errors when adding to git. Detect and remove
    # any untracked entries named 'nul' before staging.
    if git ls-files --others --exclude-standard | grep -E '(^|/|\\)nul$' >/dev/null 2>&1; then
        echo "Found reserved filename 'nul' in working tree; removing to avoid git errors."
        git ls-files --others --exclude-standard | grep -E '(^|/|\\)nul$' | while read -r f; do
            echo "Removing untracked file: $f"
            rm -f -- "$f" || true
        done
    fi

    git add .
    git commit -m "Upgrade package"
fi

# Check and install dependencies
for package in bumpversion twine build; do
    if ! py -m pip show $package &> /dev/null; then
        echo "$package not found, installing..."
        py -m pip install $package
    fi
done

# Check if a version bump type is provided
if [ -z "$1" ]; then
    echo "Usage:"
    echo "  $0 local|install     # editable install for development (pip install -e .[test])"
    echo "  $0 major|minor|patch # bump version, build, upload to PyPI, pip upgrade TTS_ka"
    exit 1
fi

# Bump the version
py -m bumpversion "$1"

# Remove old distribution files if they exist
if [ -d "dist" ]; then
    rm -rf dist/*
fi

# Create new distribution files
py -m build

# Upload to PyPI
py -m twine upload dist/*

echo "Package updated and uploaded to PyPI successfully."

# Upgrade the installed package
py -m pip install --upgrade TTS_ka
