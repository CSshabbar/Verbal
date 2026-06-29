#!/bin/bash
# build-win.sh - Build script for Windows app

set -e

echo "Building Verbal for Windows v1.0.9..."

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    python -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install pyinstaller
pip install -r requirements-win.txt

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist build

# Build the Windows executable
echo "Building Windows executable..."
pyinstaller verbal-win.spec --clean --noconfirm

# Show build results
echo "Build completed!"
ls -lh dist/

echo "Build successful! Verbal.exe is ready for distribution."