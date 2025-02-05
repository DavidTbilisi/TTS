#!/bin/bash

set -e  # Exit on error

# Check and install dependencies
for package in bumpversion twine build; do
    if ! py -m pip show $package &> /dev/null; then
        echo "$package not found, installing..."
        py -m pip install $package
    fi
done

# Check if a version bump type is provided
if [ -z "$1" ]; then
    echo "Usage: $0 [major|minor|patch]"
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
