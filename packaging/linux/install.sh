#!/bin/sh
# Per-user installer for LocArc (no root required).
#
# Copies the packaged app into ~/.local/share/locarc, adds a launcher in
# ~/.local/bin and an application-menu entry, so it behaves like an installed app.
# Mirrors the Windows installer; runs on any distro (portable tarball, not a
# system package).
#
#   ./install.sh            install (or update in place)
#   ./uninstall.sh          remove the app, keeping user data
#   ./uninstall.sh --purge  remove the app and all user data
set -eu

APP_ID="locarc"
APP_NAME="LocArc"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/$APP_ID"
LEGACY_DIR="$DATA_HOME/intel-ai-studio"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$DATA_HOME/applications"

if [ ! -x "$SRC_DIR/LocArc" ]; then
  echo "LocArc executable not found in $SRC_DIR" >&2
  echo "Run install.sh from the extracted release folder." >&2
  exit 1
fi

echo "Installing $APP_NAME to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp -a "$SRC_DIR"/. "$INSTALL_DIR"/

# Carry over data from a pre-rename Intel AI Studio installation. The old
# folder is left untouched so users can verify the migration before deleting it.
if [ -d "$LEGACY_DIR/data" ] && [ ! -e "$INSTALL_DIR/data" ]; then
  cp -a "$LEGACY_DIR/data" "$INSTALL_DIR/data"
  echo "  Migrated data from $LEGACY_DIR/data"
fi

# Command-line launcher.
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/LocArc" "$BIN_DIR/$APP_ID"

# Application-menu entry (absolute Exec path baked in at install time).
mkdir -p "$APPS_DIR"
sed "s|@INSTALL_DIR@|$INSTALL_DIR|g" \
  "$INSTALL_DIR/locarc.desktop.in" > "$APPS_DIR/$APP_ID.desktop"
chmod +x "$APPS_DIR/$APP_ID.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

if command -v python3 >/dev/null 2>&1 && \
   python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('WebKit2','4.1')" >/dev/null 2>&1; then
  :
else
  echo "  Note: for a native window install WebKitGTK:"
  echo "        sudo apt install python3-gi gir1.2-webkit2-4.1"
  echo "        (without it the app opens in your browser)"
fi

if [ -d "$LEGACY_DIR" ]; then
  echo "  Note: the previous Intel AI Studio install is still in $LEGACY_DIR."
  echo "        Its data was copied to $INSTALL_DIR/data; remove the old folder when ready."
fi

echo "Done."
echo "  Launch from the app menu, or run: $APP_ID"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "  Note: add $BIN_DIR to your PATH to use the '$APP_ID' command." ;;
esac
