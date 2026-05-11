#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Building Verbal..."

# 1. Create venv
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Install deps
pip install --upgrade pip
pip install "setuptools<75" wheel
pip install -r requirements.txt
pip install pyinstaller

# 3. Download whisper small model if not cached
python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

# 4. Generate icons
python3 scripts/generate_icons.py

# 5. Convert icon.png to .icns
mkdir -p assets/icon.iconset
sips -z 16 16 assets/icon.png --out assets/icon.iconset/icon_16x16.png
sips -z 32 32 assets/icon.png --out assets/icon.iconset/icon_16x16@2x.png
sips -z 32 32 assets/icon.png --out assets/icon.iconset/icon_32x32.png
sips -z 64 64 assets/icon.png --out assets/icon.iconset/icon_32x32@2x.png
sips -z 128 128 assets/icon.png --out assets/icon.iconset/icon_128x128.png
sips -z 256 256 assets/icon.png --out assets/icon.iconset/icon_128x128@2x.png
sips -z 256 256 assets/icon.png --out assets/icon.iconset/icon_256x256.png
sips -z 512 512 assets/icon.png --out assets/icon.iconset/icon_256x256@2x.png
sips -z 512 512 assets/icon.png --out assets/icon.iconset/icon_512x512.png
iconutil -c icns assets/icon.iconset -o assets/Verbal.icns

# 6. Build .app
pyinstaller verbal.spec --clean --noconfirm

# 7. Ad-hoc code sign
codesign --sign - --force --deep dist/Verbal.app

echo ""
echo "Build complete: dist/Verbal.app"
echo "Drag to /Applications and launch"
