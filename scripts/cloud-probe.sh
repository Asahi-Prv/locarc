#!/usr/bin/env bash
# Headless probe for Intel cloud bare-metal nodes (Nova Lake, Panther Lake,
# Xeon + Arc Pro B, ...): host environment report, OVMS runtime install,
# OpenVINO device probe, then optionally a model download and a load +
# completion round on every detected device. No GUI needed (Ubuntu 24.04).
#
# Usage (from a clone of this repo on the node):
#   bash scripts/cloud-probe.sh                                   # host + device probe
#   bash scripts/cloud-probe.sh --install                         # + latest OVMS runtime
#   bash scripts/cloud-probe.sh --install --channel weekly        # weekly channel
#   bash scripts/cloud-probe.sh --install --model OpenVINO/<repo> # + download + load matrix
#   bash scripts/cloud-probe.sh --install --model ... --devices CPU,GPU,NPU
#
# HF_TOKEN=<token> is stored in the app config for gated repos. To use the UI,
# forward the port from your machine: ssh -L 8810:127.0.0.1:8810 <node>
# Results: .cloud-data/report.md (+ backend.log, load-*.json, complete-*.json)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
DATA="${LOCARC_DATA:-$REPO/.cloud-data}"  # persistent: venv, runtime, models, report
UI_PORT="${UI_PORT:-8810}"
INSTALL=0
CHANNEL="${CHANNEL:-stable}"
MODEL=""
DEVICES=""
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --install) INSTALL=1 ;;
    --channel) CHANNEL="${2:?stable|weekly}"; shift ;;
    --model) MODEL="${2:?repo required}"; shift ;;
    --devices) DEVICES="${2:?comma-separated devices}"; shift ;;
    --keep) KEEP=1 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

API="http://127.0.0.1:$UI_PORT"
REST_PORT="${REST_PORT:-8000}"
mkdir -p "$DATA"
export LOCARC_DATA="$DATA"
REPORT="$DATA/report.md"
: > "$REPORT"

log() { printf '%s\n' "$*" | tee -a "$REPORT"; }

# --- helpers (system python3; independent of the app venv) --------------------
json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$2"; }

wait_task() { # <task_id> <timeout_s> <label>
  local tid="$1" timeout="${2:-1800}" label="$3" st deadline
  deadline=$(( $(date +%s) + timeout ))
  while :; do
    st=$(curl -fsS "$API/api/tasks/$tid" | json_field status)
    case "$st" in
      done) return 0 ;;
      error|cancelled) return 1 ;;
    esac
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "$label: timed out" >&2
      return 1
    fi
    sleep 2
  done
}

# --- venv (persistent, so repeated runs skip the pip install) ------------------
PY="$DATA/.venv/bin/python"
if [ ! -x "$PY" ]; then
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || {
    echo "Python >= 3.12 required (Ubuntu 24.04 default is fine)" >&2; exit 1; }
  python3 -m venv "$DATA/.venv"
  "$DATA/.venv/bin/pip" install -q -r "$REPO/requirements.txt"
fi

# --- start the backend headless -------------------------------------------------
"$PY" -m app.main >"$DATA/backend.log" 2>&1 &
BACKEND=$!
cleanup() { [ "$KEEP" -eq 1 ] || kill "$BACKEND" 2>/dev/null || true; }
trap cleanup EXIT

deadline=$(( $(date +%s) + 60 ))
until curl -fsS "$API/api/config" >/dev/null 2>&1; do
  if ! kill -0 "$BACKEND" 2>/dev/null; then
    echo "Backend exited early:" >&2
    tail -n 40 "$DATA/backend.log" >&2
    exit 1
  fi
  [ "$(date +%s)" -lt "$deadline" ] || { echo "Backend did not come up" >&2; exit 1; }
  sleep 1
done
log "# LocArc cloud probe — $(date -u +%FT%TZ)"

if [ -n "${HF_TOKEN:-}" ]; then
  curl -fsS -X POST "$API/api/config" -H 'Content-Type: application/json' \
    -d "{\"hf_token\":\"$HF_TOKEN\"}" >/dev/null
fi

# --- host environment ------------------------------------------------------------
log
log "## Host"
log "- OS: $(. /etc/os-release && echo "$PRETTY_NAME") / kernel $(uname -r)"
log "- CPU: $(lscpu | awk -F': +' '/Model name/{print $2; exit}') ($(nproc) threads)"
log "- AMX/AVX flags: $(lscpu | grep -oE 'amx_[a-z0-9_]+|avx512[a-z0-9_]*' | sort -u | tr '\n' ' ' || echo none)"
log "- Memory: $(free -h | awk '/^Mem/{print $2}') / disk free on data dir: $(df -h "$DATA" | awk 'NR==2{print $4}')"
log "- PCIe graphics/accelerators:"
lspci -nn 2>/dev/null | grep -Ei 'vga|3d|display|processing accelerator' | sed 's/^/  - /' | tee -a "$REPORT" || log "  - (lspci unavailable)"
log "- NPU device nodes: $(ls /dev/accel* 2>/dev/null | tr '\n' ' ' || echo none)"

# --- runtime ----------------------------------------------------------------------
log
log "## OVMS runtime"
if [ "$INSTALL" -eq 1 ]; then
  log "Installing latest OVMS runtime from the '$CHANNEL' channel ..."
  INST=$(curl -fsS -X POST "$API/api/ovms/install_latest" \
    -H 'Content-Type: application/json' -d "{\"channel\":\"$CHANNEL\"}")
  TID=$(printf '%s' "$INST" | json_field task_id)
  if [ -n "$TID" ] && wait_task "$TID" 1800 "runtime install"; then
    log "- installed: $(printf '%s' "$INST" | json_field label)"
  else
    log "- INSTALL FAILED (see backend.log)"; exit 1
  fi
fi
INSTALLED=$(curl -fsS "$API/api/ovms/installed")
RID=$(printf '%s' "$INSTALLED" | python3 -c '
import json, sys
rows = json.load(sys.stdin)
ok = [r for r in rows if r.get("exe_ok")]
print(ok[0]["id"] if ok else "")')
if [ -z "$RID" ]; then
  log "- no runtime installed; re-run with --install"
  exit 1
fi
curl -fsS -X POST "$API/api/ovms/select" -H 'Content-Type: application/json' \
  -d "{\"id\":\"$RID\"}" >/dev/null
log "- selected runtime: $RID"

# --- OpenVINO device probe (the headline result on new silicon) --------------------
log
log "## OpenVINO devices"
DEVS=$(curl -fsS "$API/api/ovms/devices?refresh=1" | python3 -c '
import json, sys
v = json.load(sys.stdin).get("devices")
print(",".join(v) if isinstance(v, list) else "")')
if [ -z "$DEVS" ]; then
  log "- probe returned NOTHING (driver/OpenVINO support missing? see backend.log)"
  DEVICES="${DEVICES:-CPU}"
else
  log "- $DEVS"
fi

# --- optional: model download + load/completion matrix ------------------------------
if [ -z "$MODEL" ]; then
  log
  log "Model load matrix skipped (pass --model <hf-repo> to run it)."
  log
  log "Backend log: $DATA/backend.log"
  exit 0
fi

NAME=$(printf '%s' "$MODEL" | sed 's#[\\/:*?"<>|]#-#g; s/^[. ]*//; s/[. ]*$//')
if ! curl -fsS "$API/api/models" | grep -q "\"name\":\"$NAME\""; then
  log
  log "## Downloading $MODEL (IR-only)"
  TID=$(curl -fsS -X POST "$API/api/models/download_hf" -H 'Content-Type: application/json' \
    -d "{\"repo_id\":\"$MODEL\",\"ir_only\":true}" | json_field task_id)
  if [ -z "$TID" ] || ! wait_task "$TID" 3600 "model download"; then
    log "- DOWNLOAD FAILED (gated repo? set HF_TOKEN. see backend.log)"; exit 1
  fi
  log "- ok"
fi

IFS=',' read -ra DEVLIST <<< "${DEVICES:-$DEVS}"
# A device expression with ':' (HETERO:GPU.0,GPU.1 / MULTI:GPU,GPU.1) is one target:
if printf '%s' "${DEVICES:-}" | grep -q ':'; then DEVLIST=("${DEVICES}"); fi
log
log "## Load + completion matrix (model: $NAME)"
for DEV in "${DEVLIST[@]}"; do
  DEV="$(echo "$DEV" | tr -d ' ')"
  [ -n "$DEV" ] || continue
  log
  log "### $DEV"
  if ! curl -fsS -X POST "$API/api/model/load" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$NAME\",\"device\":\"$DEV\"}" >"$DATA/load-$DEV.json" 2>&1; then
    log "- load REJECTED: $(head -c 300 "$DATA/load-$DEV.json")"
    continue
  fi
  log "- load accepted, waiting for ready ..."
  sdeadline=$(( $(date +%s) + 900 )); READY=0
  while [ "$(date +%s)" -lt "$sdeadline" ]; do
    ST=$(curl -fsS "$API/api/server/status")
    if printf '%s' "$ST" | grep -q '"ready": *true'; then READY=1; break; fi
    if printf '%s' "$ST" | grep -q '"load_state": *"failed"'; then break; fi
    sleep 3
  done
  if [ "$READY" -ne 1 ]; then
    log "- LOAD FAILED"
    curl -fsS "$API/api/server/logs" | head -c 2000 >> "$REPORT" || true
    log ""
    curl -fsS -X POST "$API/api/model/unload" >/dev/null || true
    sleep 2
    continue
  fi
  METRIC=$(curl -s -o "$DATA/complete-$DEV.json" -w '%{http_code} %{time_total}' -m 180 \
    -X POST "http://127.0.0.1:$REST_PORT/v3/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"$NAME\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}],\"max_tokens\":16}")
  log "- completion: HTTP ${METRIC%% *} in ${METRIC#* }s"
  [ "${METRIC%% *}" = "200" ] || head -c 400 "$DATA/complete-$DEV.json" >> "$REPORT"
  curl -fsS -X POST "$API/api/model/unload" >/dev/null || true
  sleep 3
done

log
log "Backend log: $DATA/backend.log"
log "Done."
