#!/bin/bash
# build-win.sh - Build script for Windows app

set -e

echo "Building Verbal for Windows v1.0.10..."

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    python -m venv .venv
fi

# Use the venv interpreter directly. Native Windows venvs use Scripts/python.exe;
# Unix-like shells use bin/python.
if [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    echo "ERROR: virtual environment Python was not created" >&2
    exit 1
fi

# Upgrade pip
"$PY" -m pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
"$PY" -m pip install pyinstaller
"$PY" -m pip install -r requirements-win.txt

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist build

# Build the Windows executable
echo "Building Windows executable..."
"$PY" -m PyInstaller verbal-win.spec --clean --noconfirm

# Show build results
echo "Build completed!"
ls -lh dist/

echo "Build successful! Verbal.exe is ready for distribution."
