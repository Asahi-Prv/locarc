#!/usr/bin/env bash
# Build a distributable Linux app with PyInstaller (see locarc.spec).
#
# The output is dist/LocArc/ (a portable folder with the bundled Python
# runtime) plus the Linux install/uninstall helpers copied in for the release
# tarball. Run scripts/smoke-test.sh afterwards to verify it.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "[setup] creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -r requirements-dev.txt

python -m PyInstaller --noconfirm --clean \
  --workpath build/work --distpath dist \
  locarc.spec

cp packaging/linux/install.sh packaging/linux/uninstall.sh \
   packaging/linux/locarc.desktop.in dist/LocArc/
chmod +x dist/LocArc/LocArc dist/LocArc/install.sh \
         dist/LocArc/uninstall.sh

echo
echo "Done: dist/LocArc/LocArc"
echo "Tip: verify it with  scripts/smoke-test.sh dist/LocArc/LocArc"
echo "Tip: install it with dist/LocArc/install.sh"
