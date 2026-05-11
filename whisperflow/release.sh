#!/bin/bash
# release.sh — build, upload, and register a new Verbal version
# Usage: ./release.sh <version> <platform> [changelog]
# Example: ./release.sh 1.1.0 mac "- Added Windows support\n- Auto-updates"

set -e

VERSION="$1"
PLATFORM="${2:-mac}"
CHANGELOG="${3:-Release $VERSION}"

if [ -z "$VERSION" ]; then
  echo "Usage: ./release.sh <version> <platform> [changelog]"
  echo "  platform: mac | win"
  exit 1
fi

SUPABASE_URL="https://ovpcthjingugwvpxlsna.supabase.co"
SUPABASE_ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im92cGN0aGppbmd1Z3d2cHhsc25hIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNjQzMDYsImV4cCI6MjA5Mzg0MDMwNn0.XwTBo8L-aEUmmSl6dJXNqA2QXzGFOpIVB5W9eDI8j28"

# For writing versions, you need the service_role key.
# Set SUPABASE_SERVICE_KEY in your .env or environment.
if [ -z "$SUPABASE_SERVICE_KEY" ]; then
  if [ -f .env ]; then
    SUPABASE_SERVICE_KEY=$(grep SUPABASE_SERVICE_KEY .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
  fi
fi

if [ -z "$SUPABASE_SERVICE_KEY" ]; then
  echo "WARNING: SUPABASE_SERVICE_KEY not set."
  echo "  Get it from: Supabase Dashboard -> Settings -> API -> service_role key"
  echo "  Then add to .env: SUPABASE_SERVICE_KEY=eyJ..."
  echo ""
  echo "  Continuing with anon key (may fail on INSERT)..."
  AUTH_KEY="$SUPABASE_ANON_KEY"
else
  AUTH_KEY="$SUPABASE_SERVICE_KEY"
fi

# ── Build ────────────────────────────────────────────────────────────────
echo "Building Verbal $VERSION for $PLATFORM..."

if [ "$PLATFORM" = "mac" ]; then
  chmod +x build.sh
  ./build.sh

  DMG_NAME="Verbal-${VERSION}.dmg"
  DMG_PATH="dist/$DMG_NAME"
  if command -v hdiutil &>/dev/null; then
    echo "Creating DMG..."
    hdiutil create -volname "Verbal $VERSION" -srcfolder dist/Verbal.app -ov "$DMG_PATH"
  else
    echo "hdiutil not found - creating zip instead"
    DMG_PATH="dist/Verbal-${VERSION}.zip"
    if [ ! -f "$DMG_PATH" ]; then
      cd dist && zip -r "Verbal-${VERSION}.zip" Verbal.app && cd ..
    fi
    DMG_NAME="Verbal-${VERSION}.zip"
  fi
  FILE_PATH="$DMG_PATH"
  FILE_NAME="$DMG_NAME"

elif [ "$PLATFORM" = "win" ]; then
  echo "Windows build must be done on a Windows machine."
  echo "Run: pip install pyinstaller && pyinstaller verbal-win.spec --clean"
  echo ""
  echo "Then copy dist/Verbal.exe here and re-run:"
  echo "  ./release.sh $VERSION win"
  FILE_PATH="dist/Verbal.exe"
  FILE_NAME="Verbal-${VERSION}-setup.exe"
  if [ ! -f "$FILE_PATH" ]; then
    echo "ERROR: $FILE_PATH not found. Build on Windows first."
    exit 1
  fi
else
  echo "ERROR: Unknown platform: $PLATFORM"
  exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
  echo "ERROR: Build artifact not found: $FILE_PATH"
  exit 1
fi

# ── Hash ─────────────────────────────────────────────────────────────────
HASH=$(shasum -a 256 "$FILE_PATH" | cut -d' ' -f1)
SIZE=$(stat -f%z "$FILE_PATH" 2>/dev/null || stat -c%s "$FILE_PATH" 2>/dev/null)

echo "File: $FILE_PATH"
echo "Hash: $HASH"
echo "Size: $SIZE bytes"

# ── Upload to Supabase Storage ───────────────────────────────────────────
STORAGE_PATH="$PLATFORM/$FILE_NAME"
echo "Uploading to Supabase Storage: releases/$STORAGE_PATH"

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "${SUPABASE_URL}/storage/v1/object/releases/${STORAGE_PATH}" \
  -H "apikey: ${AUTH_KEY}" \
  -H "Authorization: Bearer ${AUTH_KEY}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@$FILE_PATH")

if [ "$HTTP_STATUS" != "200" ]; then
  echo "Initial upload returned $HTTP_STATUS, trying upsert..."
  curl -s -X POST \
    "${SUPABASE_URL}/storage/v1/object/releases/${STORAGE_PATH}" \
    -H "apikey: ${AUTH_KEY}" \
    -H "Authorization: Bearer ${AUTH_KEY}" \
    -H "Content-Type: application/octet-stream" \
    -H "x-upsert: true" \
    --data-binary "@$FILE_PATH"
fi

FILE_URL="${SUPABASE_URL}/storage/v1/object/public/releases/${STORAGE_PATH}"
echo "File URL: $FILE_URL"

# ── Register version ─────────────────────────────────────────────────────
echo "Registering version $VERSION for $PLATFORM..."

CHANGELOG_JSON=$(echo "$CHANGELOG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")

curl -s -X POST \
  "${SUPABASE_URL}/rest/v1/app_versions" \
  -H "apikey: ${AUTH_KEY}" \
  -H "Authorization: Bearer ${AUTH_KEY}" \
  -H "Content-Type: application/json" \
  -H "Prefer: return=minimal,resolution=merge-duplicates" \
  -d "{
    \"platform\": \"$PLATFORM\",
    \"version\": \"$VERSION\",
    \"changelog\": $CHANGELOG_JSON,
    \"file_url\": \"$FILE_URL\",
    \"file_hash\": \"$HASH\",
    \"file_size\": $SIZE
  }"

echo ""
echo "Done! Released Verbal $VERSION for $PLATFORM"
echo "All installed copies will detect the update on next launch."
