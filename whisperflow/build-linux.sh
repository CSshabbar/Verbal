#!/bin/bash
# build-linux.sh - Build script for Linux app

set -e

echo "Building Verbal for Linux..."

PY=".venv/bin/python"

# System prerequisites. PyGObject in particular is NOT pip-installable into a plain venv,
# and without it the built app has no working tray menu and no dashboard.
MISSING_SYS=()
for pkg in python3-gi gir1.2-ayatanaappindicator3-0.1 gir1.2-webkit2-4.1 python3-tk; do
    dpkg -s "$pkg" >/dev/null 2>&1 || MISSING_SYS+=("$pkg")
done
if [ ${#MISSING_SYS[@]} -gt 0 ]; then
    echo "ERROR: missing system packages: ${MISSING_SYS[*]}"
    echo "  sudo apt install -y ${MISSING_SYS[*]} libportaudio2 xdotool xclip wl-clipboard"
    exit 1
fi

# Create venv if it doesn't exist. --system-site-packages is REQUIRED so the build and the
# frozen app can see system PyGObject (gi).
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi

# An existing venv built without it would silently produce a tray-less, dashboard-less app.
if ! grep -q "include-system-site-packages = true" .venv/pyvenv.cfg; then
    echo "ERROR: .venv cannot see system site-packages, so PyGObject (gi) is invisible to it."
    echo "  Fix in place:  sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' .venv/pyvenv.cfg"
    echo "  Or recreate:   rm -rf .venv && python3 -m venv --system-site-packages .venv"
    exit 1
fi

# Use the venv's own interpreter for pip. A uv-created venv has no `pip` executable at all,
# so a bare `pip install` either exits 127 or silently targets system Python.
echo "Installing dependencies..."
"$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements-linux.txt

"$PY" -c "import gi; print('gi OK:', gi.__file__)"
"$PY" -c "import pystray; assert pystray.Icon.HAS_MENU, \
    'pystray backend %s has no menu support' % pystray.Icon.__module__; \
    print('tray backend OK:', pystray.Icon.__module__)"

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist build

# Build the Linux executable
echo "Building Linux executable..."
"$PY" -m PyInstaller verbal-linux.spec --clean --noconfirm

# Show build results
echo "Build completed!"
ls -lh dist/

echo "Build successful! dist/Verbal is ready for distribution."
echo
echo "Next steps:"
echo "  install the desktop entry:  ./packaging/install-desktop.sh"
echo "  bind the dictation hotkey:  ./dist/Verbal --install-hotkey"
