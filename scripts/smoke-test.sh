#!/usr/bin/env bash
# Smoke test a built Intel AI Studio executable: start it with a throwaway data
# directory, wait for the HTTP API and the bundled static UI to answer, then stop it.
set -euo pipefail

EXE="${1:-dist/Intel-AI-Studio/Intel-AI-Studio}"
PORT="${PORT:-8810}"
TIMEOUT="${TIMEOUT:-60}"

if [ ! -x "$EXE" ]; then
  echo "Executable not found or not executable: $EXE (run the build first)" >&2
  exit 1
fi
EXE="$(cd "$(dirname "$EXE")" && pwd)/$(basename "$EXE")"

DATA="$(mktemp -d "${TMPDIR:-/tmp}/ai-studio-smoke.XXXXXX")"
export AI_STUDIO_DATA="$DATA"
LOG="$DATA/app.log"

echo "Starting $EXE ..."
"$EXE" >"$LOG" 2>&1 &
PID=$!

cleanup() {
  kill "$PID" 2>/dev/null || true
  rm -rf "$DATA"
}
trap cleanup EXIT

deadline=$(( $(date +%s) + TIMEOUT ))
ok=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 0.75
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "The executable exited early." >&2
    echo "--- log (tail) ---" >&2
    tail -n 40 "$LOG" >&2 || true
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:$PORT/api/config" >/dev/null 2>&1; then
    if ! curl -fsS "http://127.0.0.1:$PORT/" | grep -q "Intel AI Studio"; then
      echo "Static UI check failed" >&2
      exit 1
    fi
    if ! curl -fsS "http://127.0.0.1:$PORT/i18n.js" | grep -q '"chat.new_title":'; then
      echo "Bundled i18n.js check failed" >&2
      exit 1
    fi
    ok=1
    break
  fi
done

if [ "$ok" -ne 1 ]; then
  echo "Smoke test failed: no HTTP response on 127.0.0.1:$PORT within ${TIMEOUT}s" >&2
  echo "--- log (tail) ---" >&2
  tail -n 40 "$LOG" >&2 || true
  exit 1
fi

echo "Smoke test OK: $EXE"
