"""FastAPI backend for the LocArc UI."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import chats as chatsvc
from . import models as modelsvc
from . import ovms, updater
from . import tasks as taskmod
from .config import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    MODELS_DIR,
    RUNTIMES_DIR,
    STATIC_DIR,
    get_preset,
    load_config,
    save_config,
    save_preset,
)
from .fsutil import is_within, rmtree
from .i18n import normalize, tr

app = FastAPI(title=APP_NAME, version=APP_VERSION)


def _lang(request: Request | None) -> str:
    if request is None:
        return "en"
    return normalize(request.headers.get("accept-language"))

# ------------------------------------------------------------------ config / tasks


SECRET_KEYS = ("hf_token", "ovms_api_key")


@app.get("/api/config")
def api_get_config():
    cfg = load_config()
    masked = {k: ("" if k in SECRET_KEYS else v) for k, v in cfg.items()}
    return {**masked,
            "app_version": APP_VERSION,
            "data_dir": str(DATA_DIR), "models_dir": str(MODELS_DIR),
            "hf_token_set": bool(cfg.get("hf_token")),
            "ovms_api_key_set": bool(cfg.get("ovms_api_key"))}


def _validated_port(value, key: str, lang: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as e:
        raise HTTPException(400, tr(lang, "err.bad_port", key=key)) from e
    if not 1 <= port <= 65535:
        raise HTTPException(400, tr(lang, "err.bad_port", key=key))
    return port


@app.post("/api/config")
def api_post_config(body: dict, request: Request):
    lang = _lang(request)
    body = dict(body or {})
    for key in ("ui_port", "rest_port", "grpc_port"):
        if key in body:
            body[key] = _validated_port(body[key], key, lang)
    # secrets: keep existing value when the field is omitted entirely
    cfg = load_config()
    for k in SECRET_KEYS:
        if k not in body:
            body[k] = cfg.get(k, "")
    return save_config(body)


@app.get("/api/tasks")
def api_tasks():
    return taskmod.list_all()


@app.post("/api/tasks/{tid}/cancel")
def api_task_cancel(tid: str):
    return {"cancelled": taskmod.cancel(tid)}


# ------------------------------------------------------------------ self-update


@app.get("/api/update/check")
def api_update_check(request: Request, force: int = 0):
    lang = _lang(request)
    try:
        info = updater.check_for_update(force=bool(force), lang=lang)
    except Exception as e:
        raise HTTPException(502, tr(lang, "err.update_failed", error=e)) from e
    return {**info, "frozen": bool(getattr(sys, "frozen", False))}


@app.post("/api/update/run")
def api_update_run(body: dict, request: Request):
    lang = _lang(request)
    if not getattr(sys, "frozen", False):
        raise HTTPException(400, tr(lang, "err.update_source_mode"))
    try:
        info = updater.check_for_update(force=False, lang=lang)
    except Exception as e:
        raise HTTPException(502, tr(lang, "err.update_failed", error=e)) from e
    tag = str((body or {}).get("tag") or "")
    if not info.get("available") or (tag and tag != info.get("tag")):
        raise HTTPException(400, tr(lang, "err.update_not_available"))
    tid = taskmod.create("update", tr(lang, "task.update_title", version=info.get("latest", "")), lang)
    threading.Thread(target=updater.update_worker, args=(tid, info), daemon=True).start()
    return {"task_id": tid}


# ------------------------------------------------------------------ ovms runtime


@app.get("/api/ovms/versions")
def api_ovms_versions(request: Request, channel: str = "stable"):
    lang = _lang(request)
    if channel not in ("stable", "weekly"):
        raise HTTPException(400, tr(lang, "err.bad_channel"))
    try:
        return ovms.list_versions(channel, lang=lang)
    except Exception as e:
        raise HTTPException(502, tr(lang, "err.versions_failed", error=e)) from e


@app.get("/api/ovms/installed")
def api_ovms_installed():
    return ovms.installed()


@app.get("/api/ovms/devices")
def api_ovms_devices(refresh: int = 0):
    """Devices available to the selected runtime (first call probes OpenVINO).

    ``?refresh=1`` forces a re-detect: cached lists go stale when a GPU/NPU
    driver is installed or updated after the first probe.
    """
    cfg = load_config()
    runtime_id = cfg.get("selected_runtime") or ""
    if not runtime_id:
        return {"devices": None}
    try:
        return {"devices": ovms.probe_devices(runtime_id, refresh=bool(refresh))}
    except Exception:
        return {"devices": None}


@app.post("/api/ovms/install")
def api_ovms_install(body: dict, request: Request):
    lang = _lang(request)
    url = (body.get("url") or "").strip()
    label = (body.get("label") or "").strip() or "unknown"
    channel = body.get("channel") or "stable"
    sha = body.get("sha256_url") or None
    if not ovms.is_allowed_url(url):
        raise HTTPException(400, tr(lang, "err.url_not_allowed"))
    tid = taskmod.create("ovms", tr(lang, "task.ovms_install", label=label), lang)
    threading.Thread(target=ovms.install_worker, args=(tid, channel, label, url, sha), daemon=True).start()
    return {"task_id": tid}


@app.post("/api/ovms/install_latest")
def api_ovms_install_latest(body: dict, request: Request):
    lang = _lang(request)
    channel = (body or {}).get("channel") or "stable"
    try:
        vers = ovms.list_versions(channel, lang=lang)
    except Exception as e:
        raise HTTPException(502, tr(lang, "err.versions_failed", error=e)) from e
    if not vers:
        raise HTTPException(404, tr(lang, "err.no_versions"))
    v = vers[0]
    tid = taskmod.create("ovms", tr(lang, "task.ovms_install", label=v["label"]), lang)
    threading.Thread(target=ovms.install_worker,
                     args=(tid, channel, v["label"], v["url"], v.get("sha256_url")),
                     daemon=True).start()
    return {"task_id": tid, "label": v["label"], "version": v["version"]}


@app.post("/api/ovms/select")
def api_ovms_select(body: dict, request: Request):
    lang = _lang(request)
    rid = body.get("id")
    if rid is not None and not any(e["id"] == rid and e["exe_ok"] for e in ovms.installed()):
        raise HTTPException(404, tr(lang, "err.runtime_not_found"))
    return save_config({"selected_runtime": rid})


@app.delete("/api/ovms/runtime/{rid}")
def api_ovms_delete(rid: str, request: Request):
    lang = _lang(request)
    d = RUNTIMES_DIR / rid
    if not is_within(d, RUNTIMES_DIR) or not d.is_dir():
        raise HTTPException(404, tr(lang, "err.not_found"))
    rmtree(d, lang=lang)
    cfg = load_config()
    if cfg.get("selected_runtime") == rid:
        save_config({"selected_runtime": None})
    return {"ok": True}


# ------------------------------------------------------------------ models


@app.get("/api/models")
def api_models():
    return modelsvc.scan()


@app.get("/api/models/search")
def api_models_search(request: Request, q: str = "", limit: int = 20,
                      sort: str = "downloads", cursor: str = ""):
    """Search Hugging Face for OpenVINO IR models (requires the .xml + .bin pair)."""
    lang = _lang(request)
    query = (q or "").strip()
    if not query:
        raise HTTPException(400, tr(lang, "err.search_query_required"))
    if len(query) > 120:
        query = query[:120]
    token = load_config().get("hf_token") or None
    try:
        results, next_cursor = modelsvc.search_hf_ir(query, limit=limit, sort=sort,
                                                     token=token, cursor=cursor or None)
        # Typing/pasting a full repo id should always find the repo, even when the
        # text search would rank it poorly.
        if "/" in query and " " not in query and not cursor:
            exact = modelsvc.repo_ir_info(query, token)
            if exact and not any(item["repo_id"] == exact["repo_id"] for item in results):
                results.insert(0, exact)
    except Exception as e:
        raise HTTPException(502, tr(lang, "err.search_failed", error=e)) from e
    return {"query": query, "results": results, "next": next_cursor}


@app.delete("/api/models/{name}")
def api_model_delete(name: str, request: Request):
    lang = _lang(request)
    try:
        modelsvc.delete(name, lang=lang)
    except Exception as e:
        raise HTTPException(404, str(e)) from e
    cfg = load_config()
    if cfg.get("selected_model") == name:
        save_config({"selected_model": None})
    return {"ok": True}


@app.post("/api/models/{name}/convert_tokenizer")
def api_convert_tokenizer(name: str, request: Request):
    """Create the tokenizer IR for an image-generation model (installs tools on first use)."""
    lang = _lang(request)
    model_dir = MODELS_DIR / name
    if not is_within(model_dir, MODELS_DIR) or not model_dir.is_dir():
        raise HTTPException(404, tr(lang, "err.model_not_found_id", name=name))
    if not (load_config().get("selected_runtime") or ""):
        raise HTTPException(400, tr(lang, "err.no_runtime"))
    tid = taskmod.create("tokenizer", tr(lang, "task.tokenizer_title", name=name), lang)
    threading.Thread(target=modelsvc.convert_tokenizer_worker, args=(tid, name), daemon=True).start()
    return {"task_id": tid}


@app.post("/api/models/download_hf")
def api_dl_hf(body: dict, request: Request):
    lang = _lang(request)
    repo = (body.get("repo_id") or "").strip().strip("/")
    if not repo or "/" not in repo or " " in repo:
        raise HTTPException(400, tr(lang, "err.bad_repo_id"))
    patterns = body.get("allow_patterns")
    if isinstance(patterns, str):
        patterns = [p.strip() for p in patterns.split(",") if p.strip()] or None
    ignore_patterns = list(modelsvc.IR_IGNORE_PATTERNS) if body.get("ir_only") else None
    token = load_config().get("hf_token") or None
    # Reject duplicates: the same repo must not be downloaded twice in parallel
    # (double-click) or again while it is already in the library.
    err_state = modelsvc.claim_hf_download(repo)
    if err_state:
        raise HTTPException(409, tr(lang, f"err.hf_download_{err_state}"))
    tid = taskmod.create("model", tr(lang, "task.hf_download", repo=repo), lang)
    taskmod.update(tid, repo=repo)
    modelsvc.set_hf_download_task(repo, tid)
    try:
        threading.Thread(target=modelsvc.download_hf_worker,
                         args=(tid, repo, body.get("revision") or None, patterns, token,
                               ignore_patterns),
                         daemon=True).start()
    except Exception:
        modelsvc.release_hf_download(repo)
        raise
    return {"task_id": tid}


@app.post("/api/models/download_url")
def api_dl_url(body: dict, request: Request):
    lang = _lang(request)
    url = (body.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, tr(lang, "err.bad_url"))
    tid = taskmod.create("model", tr(lang, "task.url_download", url=url[:70]), lang)
    threading.Thread(target=modelsvc.download_url_worker,
                     args=(tid, url, (body.get("name") or "").strip() or None,
                           bool(body.get("extract", True))),
                     daemon=True).start()
    return {"task_id": tid}


# ------------------------------------------------------------------ model load (LM Studio style)
# Detailed OVMS settings live only in the Settings tab; the load dialog stays minimal.


@app.get("/api/server/status")
def api_status():
    return ovms.server.status()


@app.get("/api/model/load_options")
def api_load_options(model: str):
    """Defaults for the load dialog: saved per-model preset over global config."""
    cfg = load_config()
    p = get_preset(model)
    runtime_id = cfg.get("selected_runtime") or ""
    # Cached only: probing here would make the load dialog wait for OpenVINO.
    # The UI fills in the full list asynchronously via /api/ovms/devices.
    devices = ovms.cached_devices(runtime_id) if runtime_id else None
    warnings: list[str] = []
    model_dir = MODELS_DIR / model
    meta = modelsvc.read_meta(model_dir)
    quant = modelsvc.quant_info(f"{model} {meta.get('origin', '')}")
    kind = modelsvc.detect_kind(model_dir) if model else "unknown"
    if kind == "image_generation":
        # OVMS loads the pipeline but then fails at generation time without the
        # tokenizer IR, which many community repos do not ship.
        candidates = [model_dir / "openvino_tokenizer.xml"]
        try:
            candidates += [sub / "openvino_tokenizer.xml" for sub in model_dir.iterdir() if sub.is_dir()]
        except OSError:
            pass
        if not any(path.is_file() for path in candidates):
            warnings.append("image_tokenizer_missing")
    return {
        "devices": devices,
        "kind": kind,
        "warnings": warnings,
        "quant": quant["precision"],
        "cw": quant["cw"],
        "device": p.get("device") or cfg.get("target_device") or "AUTO",
        "mode": p.get("mode") or cfg.get("serve_mode") or "auto",
        "max_prompt_len": p.get("max_prompt_len"),
        "cache_size": p.get("cache_size"),
        "max_num_seqs": p.get("max_num_seqs"),
        "max_num_batched_tokens": p.get("max_num_batched_tokens"),
        "kv_cache_precision": p.get("kv_cache_precision"),
        "enable_prefix_caching": p.get("enable_prefix_caching"),
        "pipeline_type": p.get("pipeline_type"),
    }


def _free_ram_gb() -> float:
    """Available physical RAM in GiB (best effort; 8.0 when it cannot be read)."""
    if os.name == "nt":
        try:
            import ctypes

            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _MEM()
            st.dwLength = ctypes.sizeof(_MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.ullAvailPhys / (1024 ** 3)
        except Exception:
            return 8.0
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return 8.0


@app.get("/api/model/recommend")
def api_recommend(model: str, request: Request):
    """Heuristic LLM load options from model size and free RAM.
    OVMS has no CPU-memory-offload flag; u8 KV precision + bounded cache is the lever."""
    lang = _lang(request)
    size_bytes = modelsvc.model_size_bytes(model)
    if size_bytes <= 0:
        raise HTTPException(404, tr(lang, "err.model_not_found"))
    size_gb = max(0.5, size_bytes / (1024 ** 3))
    free_gb = _free_ram_gb()
    cache = min(16, max(2, round(size_gb / 2)))
    # keep total (weights + kv) under ~80% of free RAM
    budget = max(1, int(free_gb * 0.8 - size_gb * 1.2))
    cache = int(max(1, min(cache, budget)))
    return {
        "cache_size": cache,
        "kv_cache_precision": "u8" if size_gb >= 4 else "",
        "max_num_seqs": 1,
        "model_size_gb": round(size_gb, 1),
        "free_ram_gb": round(free_gb, 1),
    }


@app.post("/api/model/load")
def api_load(body: dict, request: Request):
    lang = _lang(request)
    cfg = load_config()
    model = (body.get("model") or cfg.get("selected_model") or "").strip()
    runtime_id = cfg.get("selected_runtime") or ""
    if not model:
        raise HTTPException(400, tr(lang, "err.no_model_selected"))
    if not runtime_id:
        raise HTTPException(400, tr(lang, "err.no_runtime"))

    preset = get_preset(model)
    device = (body.get("device") or preset.get("device") or cfg.get("target_device") or "AUTO").strip()
    mode = (body.get("mode") or preset.get("mode") or cfg.get("serve_mode") or "auto").strip()
    if mode not in ovms.VALID_MODES:
        raise HTTPException(400, tr(lang, "err.bad_mode", allowed=" / ".join(ovms.VALID_MODES)))
    INT_KEYS = ("max_prompt_len", "cache_size", "max_num_seqs", "max_num_batched_tokens")
    STR_KEYS = ("kv_cache_precision", "pipeline_type")
    llm_options = {}
    for k in INT_KEYS + STR_KEYS + ("enable_prefix_caching",):
        v = body.get(k, preset.get(k))
        if v in (None, ""):
            continue
        if k == "enable_prefix_caching":  # pass only explicit choice (true/false)
            llm_options[k] = "true" if v in (True, "true", "1", 1) else "false"
            continue
        # max_prompt_len is only accepted by the NPU plugin (CPU/GPU reject it at init)
        if k == "max_prompt_len" and "NPU" not in device.upper():
            continue
        if k in STR_KEYS:
            vv = str(v).strip()
            allowed = {"kv_cache_precision": ("u8",), "pipeline_type": ("LM", "LM_CB", "VLM", "VLM_CB", "AUTO")}[k]
            if vv and vv not in allowed:
                raise HTTPException(400, tr(lang, "err.bad_option_value",
                                            key=k, allowed=" / ".join(allowed)))
            if vv:
                llm_options[k] = vv
            continue
        try:
            llm_options[k] = int(float(v))  # OVMS parses these as integers
        except (TypeError, ValueError) as e:
            raise HTTPException(400, tr(lang, "err.bad_option_number", key=k)) from e

    try:
        info = ovms.server.start(
            runtime_id=runtime_id,
            model=model,
            mode=mode,
            device=device,
            rest_port=int(cfg.get("rest_port") or 8000),
            grpc_port=int(cfg.get("grpc_port") or 9000),
            bind_address=(cfg.get("bind_address") or "127.0.0.1").strip(),
            extra_args=str(cfg.get("extra_args") or ""),
            api_key=str(cfg.get("ovms_api_key") or ""),
            llm_options=llm_options,
            lang=lang,
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    save_preset(model, {"device": device, "mode": mode, **llm_options})
    save_config({"selected_model": model, "selected_runtime": runtime_id})
    return {"ok": True, **info}


@app.post("/api/model/unload")
def api_unload():
    ovms.server.stop()
    return {"ok": True}


@app.get("/api/server/logs")
def api_logs(tail: int = 200):
    return {"lines": ovms.server.tail(max(1, min(tail, 800)))}


# ------------------------------------------------------------------ chat sessions


@app.get("/api/chats")
def api_chats(request: Request):
    return chatsvc.list_chats(lang=_lang(request))


@app.post("/api/chats")
def api_chat_create(request: Request):
    return chatsvc.create(lang=_lang(request))


@app.get("/api/chats/{cid}")
def api_chat_get(cid: str, request: Request):
    lang = _lang(request)
    try:
        return chatsvc.get(cid, lang=lang)
    except Exception as e:
        raise HTTPException(404, str(e)) from e


@app.put("/api/chats/{cid}")
def api_chat_save(cid: str, body: dict, request: Request):
    lang = _lang(request)
    try:
        return chatsvc.save(cid, body or {}, lang=lang)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/chats/{cid}")
def api_chat_delete(cid: str, request: Request):
    lang = _lang(request)
    try:
        chatsvc.delete(cid, lang=lang)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


# ------------------------------------------------------------------ proxy to OVMS (avoids CORS)

_proxy_client: httpx.AsyncClient | None = None
_HOP_BY_HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive",
               "authorization",       # browser auth must not leak to OVMS
               "accept-encoding"}     # keep identity: we stream raw bytes through


def _client() -> httpx.AsyncClient:
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
    return _proxy_client


@app.api_route("/proxy/{path:path}", methods=["GET", "POST"])
async def api_proxy(path: str, request: Request):
    st = ovms.server.status()
    if not st.get("running"):
        raise HTTPException(503, tr(_lang(request), "err.ovms_not_running"))
    cfg = load_config()
    host = cfg.get("bind_address") or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    url = f"http://{host}:{cfg.get('rest_port', 8000)}/{path}"
    if request.url.query:
        url += "?" + request.url.query
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
    headers["accept-encoding"] = "identity"  # ask OVMS for plain bytes; we stream them through
    api_key = cfg.get("ovms_api_key") or ""
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"  # inject; browsers never see the key
    body = await request.body()
    req = _client().build_request(request.method, url, headers=headers, content=body)
    r = await _client().send(req, stream=True)

    async def gen():
        try:
            # aiter_bytes, not aiter_raw: decode content-encoding so the UI never
            # receives compressed bytes (we do not forward the encoding header).
            async for chunk in r.aiter_bytes():
                yield chunk
        finally:
            await r.aclose()

    out_headers = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "cache-control")}
    return StreamingResponse(gen(), status_code=r.status_code, headers=out_headers)


# ------------------------------------------------------------------ static UI

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def _linux_window_helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "linux_window.py"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "linux_window.py"


def _system_python_with_webkit() -> str | None:
    """Return a system Python that can import GTK3 + WebKit2 4.1, if any."""
    import shutil

    probe = ("import gi; gi.require_version('Gtk', '3.0'); "
             "gi.require_version('WebKit2', '4.1'); from gi.repository import Gtk, WebKit2")
    candidates = ["/usr/bin/python3", shutil.which("python3")]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            result = subprocess.run([candidate, "-c", probe], capture_output=True, timeout=20)
        except Exception:
            continue
        if result.returncode == 0:
            return candidate
    return None


def _run_linux_webkit_window(url: str) -> bool:
    """Show the UI in a native window via the system Python + WebKitGTK.

    The packaged app bundles its own Python, which has no PyGObject/WebKit2, so
    on Linux the helper script runs under the distribution's Python. Returns
    False (so the caller can fall back) when the helper cannot start.
    """
    python = _system_python_with_webkit()
    helper = _linux_window_helper_path()
    if not python or not helper.is_file():
        print("[desktop] WebKitGTK backend not available on this system")
        return False
    try:
        proc = subprocess.Popen(
            [python, str(helper), url],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
        )
    except Exception as e:
        print(f"[desktop] the WebKitGTK helper did not start ({e})")
        return False
    lines: queue.Queue[bytes | None] = queue.Queue()

    def _pump() -> None:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, b""):
                lines.put(line)
        lines.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    ready = False
    output = b""
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            if proc.poll() is not None:
                break
            continue
        if line is None:
            break
        output += line
        if line.strip() == b"READY":
            ready = True
            break
    if not ready:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        detail = output.decode("utf-8", "replace").strip()
        print(f"[desktop] the WebKitGTK window could not start ({detail[:400]})")
        return False
    print("[desktop] window shown via system WebKitGTK")
    proc.wait()  # returns when the user closes the window
    return True


def _wait_for_server(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                if client.get(f"{url}/api/config").status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _run_desktop(url: str, port: int, log_config) -> None:
    """Show the UI in a native window (WebView2 on Windows, WebKitGTK on Linux)."""
    print("[desktop] starting the local server")
    uvi_config = uvicorn.Config(app, host="127.0.0.1", port=port,
                                log_level="warning", log_config=log_config)
    server = uvicorn.Server(uvi_config)
    threading.Thread(target=server.run, daemon=True).start()
    if not _wait_for_server(url):
        print("[desktop] the local server did not start")
    else:
        print("[desktop] server ready")

    window_shown = False
    if sys.platform.startswith("linux"):
        # Prefer the system Python + WebKitGTK: the bundled Python has no GUI stack.
        window_shown = _run_linux_webkit_window(url)
    if not window_shown:
        print("[desktop] importing pywebview")
        try:
            import webview  # bundled fallback backend (WebView2 on Windows)
        except Exception as e:
            print(f"[desktop] pywebview is unavailable ({e})")
        else:
            print("[desktop] creating the window")
            try:
                webview.create_window(APP_NAME, url, width=1280, height=860, min_size=(960, 640))
                webview.start()
                window_shown = True
            except Exception as e:
                print(f"[desktop] the window could not be created ({e})")
    if not window_shown:
        print("[desktop] opening the UI in the browser instead")
        webbrowser.open(url)
        while True:
            time.sleep(3600)  # keep the server alive; quit from the app UI
    try:
        ovms.server.stop()  # never leave OVMS (and its RAM/VRAM) behind
    except Exception:
        pass
    server.should_exit = True
    time.sleep(0.5)
    os._exit(0)


def main():
    cfg = load_config()  # also ensures data dirs exist
    if getattr(sys, "frozen", False) and sys.stdout is None:
        # windowed PyInstaller exe has no console; uvicorn's logging setup probes
        # sys.stdout.isatty() and crashes. Log to a file instead.
        log_file = open(DATA_DIR / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log_file
        log_config = None  # no tty formatters
    else:
        from uvicorn.config import LOGGING_CONFIG
        log_config = LOGGING_CONFIG

    try:  # leftovers from a force-killed older build would hold the OVMS ports
        killed = ovms.cleanup_orphans()
        if killed:
            print(f"[ovms] cleaned up orphaned processes from a previous run: {killed}")
    except Exception:
        pass

    port = int(cfg.get("ui_port") or 8810)
    url = f"http://127.0.0.1:{port}"
    print(f"{APP_NAME}: {url}")
    _run_desktop(url, port, log_config)


if __name__ == "__main__":
    main()
