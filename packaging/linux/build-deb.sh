#!/usr/bin/env bash
# Build the LocArc .deb package from a PyInstaller dist folder.
# Run on Debian/Ubuntu (CI runs it on the ubuntu-24.04 runner).
#
#   packaging/linux/build-deb.sh dist/LocArc 1.2.3 LocArc-linux-x64.deb
#
# Layout: the payload goes to /opt/locarc, /usr/bin/locarc is a small launcher
# that points LOCARC_DATA at a per-user folder (the same one the portable
# install.sh uses), so the app never needs write access to /opt.
set -euo pipefail

SRC="${1:?usage: build-deb.sh <app-dir> <version> <output.deb>}"
VERSION="${2:?missing version}"
OUT="${3:?missing output path}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$SRC/LocArc" ]; then
  echo "LocArc executable not found in $SRC (build first)" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/opt/locarc" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications"

cp -a "$SRC"/. "$STAGE/opt/locarc"/

# The portable install/uninstall scripts and the desktop template belong to the
# tarball, not to the package; a stray data folder must never land in /opt.
rm -f "$STAGE/opt/locarc/install.sh" \
      "$STAGE/opt/locarc/uninstall.sh" \
      "$STAGE/opt/locarc/locarc.desktop.in"
rm -rf "$STAGE/opt/locarc/data"

install -m 0755 "$HERE/deb/locarc" "$STAGE/usr/bin/locarc"
install -m 0644 "$HERE/deb/locarc.desktop" "$STAGE/usr/share/applications/locarc.desktop"
install -m 0755 "$HERE/deb/postinst" "$STAGE/DEBIAN/postinst"
install -m 0755 "$HERE/deb/postrm" "$STAGE/DEBIAN/postrm"
sed "s/@VERSION@/$VERSION/g" "$HERE/deb/control.in" > "$STAGE/DEBIAN/control"

dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
echo "Built $OUT (version $VERSION)"
