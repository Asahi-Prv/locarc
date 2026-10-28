"""Path and configuration handling for LocArc."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .version import __version__

APP_NAME = "LocArc"
APP_VERSION = __version__


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller bundle: keep user data next to the executable.
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
# ``AI_STUDIO_DATA`` is the pre-rename name; keep accepting it so existing
# installations and scripts keep working.
DATA_DIR = Path(os.environ.get("LOCARC_DATA") or os.environ.get("AI_STUDIO_DATA")
                or str(BASE_DIR / "data")).resolve()
MODELS_DIR = DATA_DIR / "models"        # downloaded models (one folder per model)
RUNTIMES_DIR = DATA_DIR / "runtimes"    # installed ovms builds
CONFIG_PATH = DATA_DIR / "config.json"
PRESETS_PATH = DATA_DIR / "load_presets.json"  # per-model load options

# load-time-only options (text_generation pull-mode flags validated against ovms --help)
LOAD_OPTION_KEYS = ("device", "mode", "max_prompt_len", "cache_size", "max_num_seqs",
                    "max_num_batched_tokens", "kv_cache_precision", "enable_prefix_caching",
                    "pipeline_type")


def load_presets() -> dict:
    try:
        return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_preset(model: str, opts: dict) -> None:
    ensure_dirs()
    presets = load_presets()
    presets[model] = {k: v for k, v in opts.items() if k in LOAD_OPTION_KEYS and v not in (None, "")}
    PRESETS_PATH.write_text(json.dumps(presets, ensure_ascii=False, indent=1), encoding="utf-8")


def get_preset(model: str) -> dict:
    return load_presets().get(model, {})


def _static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "static"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "static"


STATIC_DIR = _static_dir()

DEFAULTS = {
    "ui_port": 8810,
    "rest_port": 8000,
    "grpc_port": 9000,
    "bind_address": "127.0.0.1",
    "target_device": "AUTO",
    "serve_mode": "auto",          # auto / classic / text_generation
    "extra_args": "",
    "selected_runtime": None,      # dirname under data/runtimes
    "selected_model": None,        # dirname under data/models
    "hf_token": "",
    "ovms_api_key": "",            # Bearer key required by OVMS itself (API_KEY env)
    # self-update (packaged builds only); cached release info lives in config.json
    "update_check_enabled": True,
    "update_repo": "Asahi-Prv/locarc",
    "last_update_check": 0.0,
    "update_latest": None,
}


_config_lock = threading.Lock()
_config_cache: dict = {"stamp": None, "cfg": None}
_dirs_ready = False


def ensure_dirs() -> None:
    global _dirs_ready
    if _dirs_ready:
        return
    for d in (DATA_DIR, MODELS_DIR, RUNTIMES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _dirs_ready = True


def _config_stamp() -> tuple[int, int] | None:
    try:
        st = CONFIG_PATH.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def load_config() -> dict:
    ensure_dirs()
    stamp = _config_stamp()
    with _config_lock:
        if stamp is not None and _config_cache["stamp"] == stamp and _config_cache["cfg"] is not None:
            return dict(_config_cache["cfg"])  # hot path: no disk I/O
    cfg = dict(DEFAULTS)
    if stamp is not None:
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))  # tolerate BOM
        except Exception:
            pass
    with _config_lock:
        _config_cache["stamp"] = stamp
        _config_cache["cfg"] = dict(cfg)
    return cfg


def save_config(updates: dict) -> dict:
    cfg = load_config()
    cfg.update({k: v for k, v in updates.items() if k in DEFAULTS})
    ensure_dirs()
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    with _config_lock:
        _config_cache["stamp"] = _config_stamp()
        _config_cache["cfg"] = dict(cfg)
    return cfg
