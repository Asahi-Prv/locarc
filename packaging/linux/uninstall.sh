#!/bin/sh
# Remove a per-user LocArc installation created by install.sh.
#
#   ./uninstall.sh          remove the app, keep user data (models, chats, settings)
#   ./uninstall.sh --purge  remove the app and all user data
set -eu

APP_ID="locarc"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/$APP_ID"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$DATA_HOME/applications"

PURGE=0
for arg in "$@"; do
  [ "$arg" = "--purge" ] && PURGE=1
done

rm -f "$BIN_DIR/$APP_ID"
rm -f "$APPS_DIR/$APP_ID.desktop"

if [ ! -d "$INSTALL_DIR" ]; then
  echo "$APP_ID is not installed in $INSTALL_DIR"
  exit 0
fi

if [ "$PURGE" -eq 1 ]; then
  rm -rf "$INSTALL_DIR"
  echo "Removed $APP_ID and its data."
else
  # Keep the 'data' folder (models, chats, settings) unless --purge was given.
  find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf {} +
  echo "Removed the $APP_ID app. Your data is kept in $INSTALL_DIR/data"
  echo "Re-run with --purge to delete it as well."
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
