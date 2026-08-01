#!/bin/bash
# install-desktop.sh — install Verbal's desktop entry, icon, launcher shim and (optionally)
# autostart, per-user. No root required; everything lands under ~/.local.
#
# Usage:
#   ./packaging/install-desktop.sh [--binary /path/to/Verbal] [--autostart]
#   ./packaging/install-desktop.sh --uninstall

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/48x48/apps"
AUTOSTART_DIR="$HOME/.config/autostart"

BINARY=""
AUTOSTART=0
UNINSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --binary)    BINARY="$2"; shift 2 ;;
        --autostart) AUTOSTART=1; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ "$UNINSTALL" = "1" ]; then
    rm -f "$BIN_DIR/verbal" "$APP_DIR/verbal.desktop" "$ICON_DIR/verbal.png" \
          "$AUTOSTART_DIR/verbal.desktop"
    update-desktop-database "$APP_DIR" 2>/dev/null || true
    echo "Removed Verbal desktop integration."
    echo "The dictation hotkey is separate — remove it with: verbal --uninstall-hotkey"
    exit 0
fi

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Resolve what `verbal` should run: the frozen binary if we have one, else the repo checkout.
if [ -z "$BINARY" ] && [ -x "$REPO/dist/Verbal" ]; then
    BINARY="$REPO/dist/Verbal"
fi

if [ -n "$BINARY" ]; then
    cat > "$BIN_DIR/verbal" <<EOF
#!/bin/sh
exec "$BINARY" "\$@"
EOF
    echo "Launcher -> $BINARY"
else
    # Source checkout: run the module through the project venv.
    if [ ! -x "$REPO/.venv/bin/python" ]; then
        echo "ERROR: no dist/Verbal and no .venv — build first, or pass --binary PATH" >&2
        exit 1
    fi
    cat > "$BIN_DIR/verbal" <<EOF
#!/bin/sh
cd "$REPO" || exit 1
exec "$REPO/.venv/bin/python" -m app.linux_main "\$@"
EOF
    echo "Launcher -> $REPO (source checkout via .venv)"
fi
chmod 755 "$BIN_DIR/verbal"

# NOTE: assets/icon.png is only 44x44, so it is installed into the 48x48 hicolor bucket.
# A proper packaging pass wants 128x128 and 256x256 source art.
cp "$REPO/assets/icon.png" "$ICON_DIR/verbal.png"
cp "$HERE/verbal.desktop" "$APP_DIR/verbal.desktop"
update-desktop-database "$APP_DIR" 2>/dev/null || true
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

if [ "$AUTOSTART" = "1" ]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$HERE/verbal.desktop" "$AUTOSTART_DIR/verbal.desktop"
    echo "X-GNOME-Autostart-enabled=true" >> "$AUTOSTART_DIR/verbal.desktop"
    echo "Autostart enabled."
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "NOTE: $BIN_DIR is not on your PATH; add it so \`verbal\` resolves." ;;
esac

echo "Installed. Now bind the hotkey:  verbal --install-hotkey"
