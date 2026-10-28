"""OpenVINO Model Server: version discovery, installation, process control.

Only `python_on` (Python bundled) packages are handled, per project requirement.

- Stable: GitHub releases of openvinotoolkit/model_server
- Weekly: https://storage.openvinotoolkit.org/repositories/openvino_model_server/packages/weekly/
  (directory listing comes from https://storage.openvinotoolkit.org/filetree.json)
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shlex
import socket
import subprocess
import tarfile
import threading
import time
import zipfile
from collections import deque
from pathlib import Path
from urllib.parse import quote

import httpx

from . import tasks
from .config import MODELS_DIR, RUNTIMES_DIR
from .fsutil import extract_zip_safe as _extract_zip_safe
from .fsutil import rmtree as _rmtree
from .fsutil import tar_safe_filter
from .i18n import normalize, tr
from .procutil import bind_to_job, subprocess_flags

GITHUB_RELEASES = "https://api.github.com/repos/openvinotoolkit/model_server/releases"
WEEKLY_BASE = "https://storage.openvinotoolkit.org/repositories/openvino_model_server/packages/weekly/"
FILETREE_URL = "https://storage.openvinotoolkit.org/filetree.json"

IS_WINDOWS = os.name == "nt"
ASSET_RE = re.compile(r"^ovms_(windows|ubuntu24|ubuntu22|redhat)_([0-9][\w.]*)_python_on\.(zip|tar\.gz)$")

ALLOWED_URL_PREFIXES = (
    "https://github.com/openvinotoolkit/model_server/releases/download/",
    "https://storage.openvinotoolkit.org/repositories/openvino_model_server/packages/",
)

_UA = {"User-Agent": "locarc"}
_FILETREE_TTL = 1800
_filetree_cache: dict = {"t": 0.0, "data": None}


def _platform_ok(os_part: str, ext: str) -> bool:
    if IS_WINDOWS:
        return os_part == "windows" and ext == "zip"
    return os_part == "ubuntu24" and ext == "tar.gz"


def is_allowed_url(url: str) -> bool:
    return any(url.startswith(p) for p in ALLOWED_URL_PREFIXES)


def list_versions(channel: str, lang: str | None = None) -> list[dict]:
    if channel == "weekly":
        return _weekly_versions(lang)
    return _stable_versions()


def _stable_versions() -> list[dict]:
    with httpx.Client(timeout=30, headers={**_UA, "Accept": "application/vnd.github+json"}) as c:
        r = c.get(GITHUB_RELEASES, params={"per_page": 15})
        r.raise_for_status()
        out = []
        for rel in r.json():
            if rel.get("draft"):
                continue
            assets = rel.get("assets", [])
            names = {a["name"] for a in assets}
            for a in assets:
                m = ASSET_RE.match(a["name"])
                if not m or not _platform_ok(m.group(1), m.group(3)):
                    continue
                sha = a["name"] + ".sha256"
                out.append({
                    "channel": "stable",
                    "label": f"{rel.get('tag_name')} ({m.group(2)})",
                    "version": m.group(2),
                    "url": a["browser_download_url"],
                    "size": a["size"],
                    "sha256_url": a["browser_download_url"] + ".sha256" if sha in names else None,
                    "published_at": rel.get("published_at"),
                })
        return out


def _filetree() -> dict:
    now = time.time()
    if _filetree_cache["data"] is None or now - _filetree_cache["t"] > _FILETREE_TTL:
        with httpx.Client(timeout=60, headers=_UA) as c:
            r = c.get(FILETREE_URL)
            r.raise_for_status()
            _filetree_cache["data"] = r.json()
            _filetree_cache["t"] = now
    return _filetree_cache["data"]


def _weekly_versions(lang: str | None = None) -> list[dict]:
    node = _filetree()
    for part in ("repositories", "openvino_model_server", "packages", "weekly"):
        node = next((ch for ch in node.get("children", []) if ch.get("name") == part), None)
        if node is None:
            raise RuntimeError(tr(lang, "err.weekly_structure"))
    out = []
    for d in node.get("children", []):
        if d.get("type") != "directory":
            continue
        names = {f["name"] for f in d.get("children", [])}
        for f in d.get("children", []):
            m = ASSET_RE.match(f.get("name", ""))
            if not m or not _platform_ok(m.group(1), m.group(3)):
                continue
            base = WEEKLY_BASE + quote(d["name"]) + "/" + quote(f["name"])
            label = d["name"]
            out.append({
                "channel": "weekly",
                "label": f"{label} -> {m.group(2)}" if d["name"] == "latest" else label,
                "version": m.group(2),
                "url": base,
                "size": f.get("size"),
                "sha256_url": base + ".sha256" if f["name"] + ".sha256" in names else None,
                "published_at": f.get("last modified"),
            })
    out.sort(key=lambda e: e.get("published_at") or "", reverse=True)
    return out


def _exe_name() -> str:
    return "ovms.exe" if IS_WINDOWS else "ovms"


def _find_exe(root: Path) -> Path | None:
    best = None
    for p in root.rglob(_exe_name()):
        if p.is_file() and (best is None or len(p.parts) < len(best.parts)):
            best = p
    return best


def installed() -> list[dict]:
    out = []
    if not RUNTIMES_DIR.exists():
        return out
    for d in sorted(RUNTIMES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith(("tmp", "downloading")):
            continue
        meta = {}
        mj = d / "runtime.json"
        if mj.exists():
            try:
                meta = json.loads(mj.read_text(encoding="utf-8"))
            except Exception:
                pass
        exe = d / meta.get("exe", "") if meta.get("exe") else _find_exe(d)
        out.append({
            "id": d.name,
            "label": meta.get("label", d.name),
            "channel": meta.get("channel", "?"),
            "version": meta.get("version", ""),
            "installed_at": meta.get("installed_at", 0),
            "exe_ok": bool(exe and exe.exists()),
        })
    out.sort(key=lambda e: e.get("installed_at", 0), reverse=True)
    return out


def _probe_flags(exe: Path) -> set[str] | None:
    """Return CLI flags supported by this ovms build (from `--help`), or None on failure."""
    try:
        r = subprocess.run([str(exe), "--help"], capture_output=True, text=True,
                           timeout=60, cwd=str(exe.parent), errors="replace",
                           creationflags=subprocess_flags())
        return set(re.findall(r"--[a-z0-9_]+", (r.stdout or "") + (r.stderr or "")))
    except Exception:
        return None


def _runtime_flags(runtime_id: str, exe: Path) -> set[str] | None:
    """Probe `--help` once per runtime and cache the result in runtime.json."""
    d = RUNTIMES_DIR / runtime_id
    mj = d / "runtime.json"
    if mj.exists():
        try:
            meta = json.loads(mj.read_text(encoding="utf-8"))
            if isinstance(meta.get("flags"), list):
                return set(meta["flags"])
        except Exception:
            pass
    flags = _probe_flags(exe)
    if flags is not None:
        try:
            meta = json.loads(mj.read_text(encoding="utf-8")) if mj.exists() else {}
            meta["flags"] = sorted(flags)
            mj.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return flags


def runtime_python(runtime_id: str, lang: str | None = None) -> Path:
    """Python interpreter bundled with a runtime (used for one-off tooling)."""
    exe = runtime_exe(runtime_id, lang=lang)
    for candidate in (exe.parent / "python" / "python.exe",
                      exe.parent / "python" / "bin" / "python3",
                      exe.parent / "python" / "bin" / "python"):
        if candidate.is_file():
            return candidate
    raise RuntimeError(tr(lang, "err.runtime_python_missing"))


def runtime_exe(runtime_id: str, lang: str | None = None) -> Path:
    d = RUNTIMES_DIR / runtime_id
    if not d.is_dir():
        raise RuntimeError(tr(lang, "err.runtime_not_found_id", runtime_id=runtime_id))
    mj = d / "runtime.json"
    exe = None
    if mj.exists():
        try:
            name = json.loads(mj.read_text(encoding="utf-8")).get("exe", "")
            if name:
                exe = d / name
        except Exception:
            exe = None
    if not exe or not exe.is_file():
        exe = _find_exe(d)
    if not exe or not exe.is_file():
        raise RuntimeError(tr(lang, "err.runtime_exe_missing", runtime_id=runtime_id, exe=_exe_name()))
    return exe


def _verify_sha256(file: Path, sha_url: str, lang: str | None = None) -> None:
    with httpx.Client(timeout=30, headers=_UA, follow_redirects=True) as c:
        text = c.get(sha_url).text
    expected = text.split()[0].strip().lower()
    import hashlib
    h = hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest().lower() != expected:
        raise RuntimeError(tr(lang, "err.sha_mismatch"))


def install_worker(tid: str, channel: str, label: str, url: str, sha_url: str | None) -> None:
    lang = tasks.lang_of(tid)
    try:
        tmp_dir = RUNTIMES_DIR / "downloading"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tasks.set_message(tid, "task.downloading")
        dest_zip = tmp_dir / url.rsplit("/", 1)[-1]
        with httpx.stream("GET", url, headers=_UA, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with dest_zip.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    if not tasks.is_running(tid):
                        raise RuntimeError(tr(lang, "err.cancelled"))
                    f.write(chunk)
                    done += len(chunk)
                    tasks.set_progress(tid, done, total)
        if sha_url:
            tasks.set_message(tid, "task.verifying")
            _verify_sha256(dest_zip, sha_url, lang=lang)

        tasks.set_message(tid, "task.extracting")
        tasks.update(tid, progress=None)
        safe = re.sub(r"[^\w.\-]+", "_", f"{channel}-{label}")[:80]
        dest = RUNTIMES_DIR / safe
        if dest.exists():
            _rmtree(dest, lang=lang)
        extract_tmp = RUNTIMES_DIR / f"tmp-{safe}"
        if extract_tmp.exists():
            _rmtree(extract_tmp, lang=lang)
        extract_tmp.mkdir(parents=True)
        if dest_zip.suffix == ".zip":
            with zipfile.ZipFile(dest_zip) as z:
                _extract_zip_safe(z, extract_tmp, lang=lang)
        else:
            with tarfile.open(dest_zip) as t:
                t.extractall(extract_tmp, filter=tar_safe_filter)

        exe = _find_exe(extract_tmp)
        if not exe:
            try:
                _rmtree(extract_tmp, attempts=2, lang=lang)
            except Exception:
                pass
            raise RuntimeError(tr(lang, "err.exe_not_found", exe=_exe_name()))
        if not IS_WINDOWS:
            exe.chmod(exe.stat().st_mode | 0o111)
        extract_tmp.rename(dest)
        meta = {
            "channel": channel,
            "label": label,
            "version": label,
            "url": url,
            "exe": str(exe.relative_to(extract_tmp)).replace("/", "\\" if IS_WINDOWS else "/"),
            "installed_at": time.time(),
        }
        (dest / "runtime.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        dest_zip.unlink(missing_ok=True)
        tasks.finish(tid, "task.install_done", label=label)
    except Exception as e:
        tasks.fail(tid, e)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
    except Exception:
        return True  # be conservative: assume alive when unsure
    return False


def cleanup_orphans() -> list[int]:
    """Kill leftover ovms.exe processes from a manager that is no longer running.

    A crashed/force-killed older build could leave OVMS behind, holding the REST
    and gRPC ports. Only processes running from our runtimes directory whose
    parent process is gone are touched; OVMS instances owned by a live manager
    are left alone.
    """
    if not IS_WINDOWS:
        return []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='ovms.exe'\" | "
             "Select-Object ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess_flags(), errors="replace",
        )
        entries = json.loads(result.stdout or "null")
    except Exception:
        return []
    if isinstance(entries, dict):
        entries = [entries]
    root = str(RUNTIMES_DIR.resolve()).lower().rstrip("\\/")
    killed: list[int] = []
    for entry in entries or []:
        pid = int(entry.get("ProcessId") or 0)
        parent = int(entry.get("ParentProcessId") or 0)
        path = str(entry.get("ExecutablePath") or "").lower()
        if not pid or not path.startswith(root) or _pid_alive(parent):
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, timeout=15, creationflags=subprocess_flags())
            killed.append(pid)
        except Exception:
            pass
    return killed


def _port_busy(port: int, host: str = "127.0.0.1") -> bool:
    """True when something is already serving on this port.

    A plain bind() test is not enough on Windows: when the existing listener set
    SO_REUSEADDR (drogon — and therefore OVMS — does), bind() succeeds anyway and
    the app starts a second OVMS that never receives a request. The ready probe
    then keeps talking to the other server, so the model loads forever while
    OVMS logs AVAILABLE. Connect first, then fall back to bind for sockets that
    are bound but not listening yet.
    """
    target = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    try:
        with socket.create_connection((target, int(port)), timeout=1.0):
            return True
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((target, int(port)))
        return False
    except OSError:
        return True


def _ovms_models_on_port(port: int) -> list[str]:
    """Model names from ``GET /v1/config`` when an OVMS is listening on this port."""
    try:
        r = httpx.get(f"http://127.0.0.1:{int(port)}/v1/config", timeout=1.5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                return [str(k) for k in data][:8]
    except Exception:
        pass
    return []


def _load_openvino_library(lib_dir: Path):
    """Load the runtime's OpenVINO C API library in-process (no console window)."""
    candidates = ([lib_dir / "openvino_c.dll"] if IS_WINDOWS
                  else sorted(lib_dir.glob("libopenvino_c.so*")))
    lib_path = next((p for p in candidates if p.is_file()), None)
    if lib_path is None:
        return None
    try:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(lib_dir))  # resolve openvino.dll, tbb, ...
    except OSError:
        pass
    try:
        return ctypes.CDLL(str(lib_path))
    except OSError:
        return None


def _devices_from_library(lib_dir: Path) -> list[str]:
    """Ask OpenVINO directly which devices are available ('' on failure)."""
    lib = _load_openvino_library(lib_dir)
    if lib is None:
        return []

    class _AvailableDevices(ctypes.Structure):
        _fields_ = [("devices", ctypes.POINTER(ctypes.c_char_p)), ("size", ctypes.c_size_t)]

    try:
        lib.ov_core_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        lib.ov_core_create.restype = ctypes.c_int
        lib.ov_core_get_available_devices.argtypes = [ctypes.c_void_p,
                                                      ctypes.POINTER(_AvailableDevices)]
        lib.ov_core_get_available_devices.restype = ctypes.c_int
        lib.ov_available_devices_free.argtypes = [ctypes.POINTER(_AvailableDevices)]
        lib.ov_available_devices_free.restype = None
        lib.ov_core_free.argtypes = [ctypes.c_void_p]
        lib.ov_core_free.restype = None

        core = ctypes.c_void_p()
        if lib.ov_core_create(ctypes.byref(core)) != 0:
            return []
        try:
            available = _AvailableDevices()
            if lib.ov_core_get_available_devices(core, ctypes.byref(available)) != 0:
                return []
            try:
                return [available.devices[i].decode("utf-8", "replace")
                        for i in range(available.size) if available.devices[i]]
            finally:
                lib.ov_available_devices_free(ctypes.byref(available))
        finally:
            lib.ov_core_free(core)
    except Exception:
        return []


def normalize_devices(devices: list[str]) -> list[str]:
    """Normalize OpenVINO device names (``GPU.0`` -> ``GPU``), ordered CPU/GPU/NPU."""
    order = ("CPU", "GPU", "NPU")
    seen: list[str] = []
    for name in devices:
        base = str(name).split(".", 1)[0].strip().upper()
        if base and base not in seen:
            seen.append(base)
    return sorted(seen, key=lambda d: (order.index(d) if d in order else len(order), d))


def cached_devices(runtime_id: str) -> list[str] | None:
    """Devices previously discovered for a runtime (no probing, never blocks)."""
    meta_path = RUNTIMES_DIR / runtime_id / "runtime.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta.get("devices"), list):
            return normalize_devices(meta["devices"])
    except Exception:
        pass
    return None


def probe_devices(runtime_id: str, lang: str | None = None,
                  refresh: bool = False) -> list[str] | None:
    """List the OpenVINO devices available to a runtime (cached in runtime.json).

    ``refresh=True`` ignores the cache and re-detects, so a driver installed or
    updated after the first probe (e.g. the Intel NPU driver) shows up.
    """
    exe = runtime_exe(runtime_id, lang=lang)
    meta_path = RUNTIMES_DIR / runtime_id / "runtime.json"
    if not refresh:
        cached = cached_devices(runtime_id)
        if cached is not None:
            return cached
    # The bundled python has no OpenVINO bindings; ask openvino_c.dll directly.
    devices = normalize_devices(_devices_from_library(exe.parent))
    if not devices:
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        meta["devices"] = devices
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return devices


# ---------------------------------------------------------------- server run


# GenAI pull-mode tasks supported by ovms (`--task ...`); classic uses --model_name/--model_path
GENAI_TASKS = ("text_generation", "embeddings", "rerank", "image_generation",
               "text2speech", "speech2text")
VALID_MODES = ("auto", "classic") + GENAI_TASKS


def resolve_mode(model_dir: Path, requested: str) -> str:
    if requested in GENAI_TASKS or requested == "classic":
        return requested
    from .models import detect_kind
    kind = detect_kind(model_dir)
    return kind if kind in (("classic",) + GENAI_TASKS) else "classic"


class OVMServer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.info: dict = {}
        self.logs: deque[str] = deque(maxlen=800)
        self.ready = False
        self.last_exit: int | None = None
        self._api_key: str = ""
        self._lang: str = "en"
        self.load_state = "idle"      # idle / loading / ready / failed
        self.load_error = ""

    def status(self) -> dict:
        with self._lock:
            running = self.proc is not None and self.proc.poll() is None
            return {
                "running": running,
                "ready": bool(running and self.ready),
                "pid": self.proc.pid if running and self.proc else None,
                "exit_code": None if running else self.last_exit,
                "load_state": self.load_state if running or self.load_state == "failed" else ("idle" if self.last_exit is not None else self.load_state),
                "load_error": self.load_error,
                **{k: v for k, v in self.info.items()},
            }

    def start(self, *, runtime_id: str, model: str, mode: str, device: str,
              rest_port: int, grpc_port: int, bind_address: str, extra_args: str,
              api_key: str = "", llm_options: dict | None = None,
              lang: str | None = None) -> dict:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                raise RuntimeError(tr(lang, "err.already_running"))
            for candidate in (rest_port, grpc_port):
                if _port_busy(candidate, bind_address):
                    models = _ovms_models_on_port(candidate)
                    if models:
                        raise RuntimeError(tr(lang, "err.port_busy_ovms",
                                              port=candidate, models=", ".join(models)))
                    raise RuntimeError(tr(lang, "err.port_busy", port=candidate))
            exe = runtime_exe(runtime_id, lang=lang)
            model_dir = MODELS_DIR / model
            if not model_dir.is_dir():
                raise RuntimeError(tr(lang, "err.model_not_found_id", name=model))
            resolved = resolve_mode(model_dir, mode)
            eff_path = _effective_model_path(model_dir)
            supported = _runtime_flags(runtime_id, exe)

            pairs: list[tuple[str, str]] = []
            if resolved in GENAI_TASKS:
                # OVMS joins <model_repository_path>/<source_model>; pull for a local
                # dir used in place (no copy/clone). graph.pbtxt is generated in the
                # model folder on first load.
                pairs += [("--source_model", model),
                          ("--model_repository_path", str(MODELS_DIR)),
                          ("--task", resolved)]
                if resolved == "text_generation":
                    # load-time-only LLM options (text_generation pull-mode flags)
                    for key, flag in (("max_prompt_len", "--max_prompt_len"),
                                      ("cache_size", "--cache_size"),
                                      ("max_num_seqs", "--max_num_seqs"),
                                      ("max_num_batched_tokens", "--max_num_batched_tokens"),
                                      ("kv_cache_precision", "--kv_cache_precision"),
                                      ("enable_prefix_caching", "--enable_prefix_caching"),
                                      ("pipeline_type", "--pipeline_type")):
                        v = (llm_options or {}).get(key)
                        if v not in (None, ""):
                            pairs.append((flag, str(v)))
            else:
                pairs += [("--model_name", model), ("--model_path", str(eff_path))]
            # Newer OVMS builds (2026.x) renamed the gRPC flag from --grpc_port to --port.
            grpc_flag = "--grpc_port"
            if supported is not None and "--grpc_port" not in supported and "--port" in supported:
                grpc_flag = "--port"
            pairs += [("--rest_port", str(rest_port)), (grpc_flag, str(grpc_port)),
                      ("--rest_bind_address", bind_address), ("--grpc_bind_address", bind_address),
                      ("--target_device", device), ("--log_level", "INFO")]

            self.logs.clear()
            cmd = [str(exe)]
            for flag, value in pairs:
                if supported is None or flag in supported:
                    cmd += [flag, value]
                else:
                    self.logs.append(f"[info] {tr(lang, 'log.flag_unsupported', flag=flag)}")
            extra = (extra_args or "").strip()
            if extra:
                cmd += shlex.split(extra, posix=not IS_WINDOWS)

            self.last_exit = None

            self.logs.append(f"> {' '.join(cmd)}")
            env = _runtime_env(exe)
            self._api_key = (api_key or "").strip()
            if self._api_key:
                env["API_KEY"] = self._api_key
                self.logs.append(f"[info] {tr(lang, 'log.api_key_enabled')}")
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1, env=env,
                cwd=str(exe.parent), creationflags=subprocess_flags(),
            )
            bind_to_job(self.proc)  # OVMS dies with us, even on a crash/force kill
            self.ready = False
            self.load_state = "loading"
            self.load_error = ""
            self._lang = normalize(lang)
            self.info = {
                "model": model, "mode": resolved, "device": device,
                "rest_port": rest_port, "grpc_port": grpc_port,
                "bind_address": bind_address,
                "runtime_id": runtime_id, "started_at": time.time(),
            }
            threading.Thread(target=self._reader, daemon=True).start()
            threading.Thread(target=self._ready_probe, daemon=True).start()
            return self.info

    def _reader(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            self.logs.append(line.rstrip("\n"))
        rc = proc.wait()
        self.last_exit = rc
        self.ready = False
        self.logs.append(f"[ovms exited: code={rc}]")

    def _ready_probe(self) -> None:
        try:
            self._ready_probe_impl()
        except Exception as e:
            try:
                self.logs.append(f"[probe crashed] {e!r}")
            except Exception:
                pass

    def _ready_probe_impl(self) -> None:
        """Ready only when the loaded model reports version state AVAILABLE in /v1/config;
        failure (LLM init error etc.) is surfaced via load_state/load_error."""
        self.logs.append("[probe] started")
        info = dict(self.info)
        proc = self.proc
        if not proc:
            return
        model = info.get("model") or ""
        host = "127.0.0.1" if info.get("bind_address") in ("0.0.0.0", "::") else info.get("bind_address")
        url = f"http://{host}:{info.get('rest_port')}/v1/config"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        deadline = time.time() + 300
        foreign_hits = 0  # /v1/config answers that belong to a *different* OVMS
        with httpx.Client(timeout=3) as c:
            while time.time() < deadline:
                if proc.poll() is not None:
                    self.logs.append(f"[probe] ovms exited, state={self.load_state}")
                    if self.load_state == "loading":
                        self.load_state = "failed"
                        if not self.load_error:
                            self.load_error = tr(self._lang, "err.ovms_exited", code=proc.returncode)
                        # surface the actual OVMS error instead of just the exit code
                        detail = next((ln.strip() for ln in reversed(self.logs)
                                       if ln.strip() and not ln.startswith(("[", ">"))), "")
                        if detail:
                            self.load_error = f"{self.load_error} — {detail[:400]}"
                    return
                try:
                    r = c.get(url, headers=headers)
                    if r.status_code == 200:
                        cfg = r.json()
                        if not isinstance(cfg, dict):
                            cfg = {}
                        entry = cfg.get(model) or {}
                        versions = entry.get("model_version_status") or []
                        states = [v.get("state", "") for v in versions]
                        if "AVAILABLE" in states:
                            self.ready = True
                            self.load_state = "ready"
                            return
                        bad = [v for v in versions
                               if v.get("state") in ("LOADING_PRECONDITION_FAILED", "LOADING_FAILED", "END")]
                        if bad:
                            msg = (bad[0].get("status") or {}).get("error_message") or bad[0].get("state")
                            self.load_state = "failed"
                            self.load_error = str(msg)
                            self.logs.append(f"[load failed] {self.load_error}")
                            return
                        # A config that lists other models but not ours twice in a row
                        # cannot be the OVMS we started (it serves exactly one source
                        # model): another server owns the port, so waiting is pointless.
                        if entry:
                            foreign_hits = 0
                        else:
                            others = [str(k) for k in cfg if k != model]
                            if others:
                                foreign_hits += 1
                                if foreign_hits >= 2:
                                    self.load_state = "failed"
                                    self.load_error = tr(self._lang, "err.port_foreign",
                                                         port=info.get("rest_port"),
                                                         models=", ".join(others[:4]))
                                    self.logs.append(f"[load failed] {self.load_error}")
                                    return
                except Exception:
                    pass
                time.sleep(1.5)
        if self.load_state == "loading":
            self.load_state = "failed"
            self.load_error = tr(self._lang, "err.load_timeout")

    def stop(self) -> None:
        with self._lock:
            proc = self.proc
        if not proc or proc.poll() is not None:
            return
        self.logs.append("[stopping...]")
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.ready = False

    def tail(self, n: int = 200) -> list[str]:
        with self._lock:
            lines = list(self.logs)
        return lines[-n:]


def _runtime_env(exe: Path) -> dict:
    """Mirror setupvars: prefer the bundled Python over any system Python.

    OVMS Windows packages ship an embeddable Python whose search path lives in
    ``pythonXY._pth`` (stdlib under ``python\\pythonXY``, not ``python\\Lib``).
    When ``ovms.exe`` initializes the interpreter in-process, that file (next to
    ``python.exe``) is not picked up, so its entries are mirrored through
    ``PYTHONPATH``. Without this the embedded interpreter falls back to the
    classic ``Lib`` layout and fails to import ``encodings`` at startup.
    """
    env = os.environ.copy()
    pkg_dir = exe.parent
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    path_parts = [str(pkg_dir)]
    py_dir = pkg_dir / "python"
    if py_dir.is_dir():
        path_parts += [str(py_dir), str(py_dir / "Scripts")]
        pth = next(iter(sorted(py_dir.glob("python3*._pth"))), None)
        search_entries: list[str] = []
        if pth is not None:
            for line in pth.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.lower() == "import site":
                    continue
                rel = line.replace("\\", os.sep)
                entry = Path(rel)
                search_entries.append(str(entry if entry.is_absolute() else py_dir / rel))
        if search_entries:
            env["PYTHONPATH"] = os.pathsep.join(search_entries)
            env["PYTHONHOME"] = str(py_dir)
        elif (py_dir / "Lib").is_dir():
            env["PYTHONHOME"] = str(py_dir)
    env["PATH"] = os.pathsep.join(path_parts) + os.pathsep + env.get("PATH", "")
    espeak = pkg_dir / "espeak-ng-data"
    if espeak.is_dir():
        env["ESPEAK_DATA_PATH"] = str(espeak)
    return env


def _effective_model_path(model_dir: Path) -> Path:
    """Descend through single-child dirs until model-ish files are found."""
    cur = model_dir
    for _ in range(3):
        try:
            entries = list(cur.iterdir())
        except OSError:
            break
        files = [e for e in entries if e.is_file()]
        if files:
            break
        dirs = [e for e in entries if e.is_dir()]
        if len(dirs) == 1:
            cur = dirs[0]
        else:
            break
    return cur


server = OVMServer()
