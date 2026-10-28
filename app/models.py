"""Model downloads (Hugging Face / direct URL) and library management."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import httpx

from . import tasks
from .config import MODELS_DIR, load_config
from .fsutil import is_within, rmtree
from .i18n import tr
from .procutil import subprocess_flags

_UA = {"User-Agent": "locarc"}
_META = ".ovmsui.json"

HF_API = "https://huggingface.co/api/models"
HF_SEARCH_SORTS = ("downloads", "likes", "lastModified")
HF_SEARCH_LIMIT_MAX = 50

# Weight formats skipped by "IR only" downloads. Configs, tokenizers and chat
# templates are kept so the downloaded folder stays loadable by OVMS.
IR_IGNORE_PATTERNS = (
    "*.safetensors",
    "*.pth",
    "*.pt",
    "*.onnx",
    "*.msgpack",
    "*.h5",
    "*.tflite",
    "*.ot",
    "*.gguf",
    "*.ckpt",
    "*.mlmodel",
    "*pytorch_model*.bin",
    "*tf_model*.h5",
    "*flax_model*.msgpack",
)


# Tokenizer IR alone does not make a loadable model; ignore those pairs when
# checking whether a repo ships model IR.
_IR_NON_MODEL_STEMS = ("openvino_tokenizer", "openvino_detokenizer")


def is_ov_ir(files: list[str]) -> bool:
    """True when a repo contains a loadable OpenVINO IR pair (.xml + .bin).

    The two files must share the same path stem, so a repo with an unrelated
    .xml and .bin does not pass, and tokenizer IR alone is not enough.
    """
    names = [str(f).lower() for f in files]
    xmls = {n[:-4] for n in names if n.endswith(".xml")}
    bins = {n[:-4] for n in names if n.endswith(".bin")}
    return any(Path(stem).name not in _IR_NON_MODEL_STEMS for stem in xmls & bins)


# Best-effort quantization detection from HF repo names / tags (OpenVINO naming
# conventions, e.g. ``Qwen3-8B-int4-cw-ov``). The NPU plugin only supports
# channel-wise (CW) quantized weights, so non-CW INT4/INT8 gets a warning.
_QUANT_PATTERNS = (
    ("int4", re.compile(r"(?<![a-z0-9])(?:int4|4bit|4-bit|w4)(?![a-z0-9])", re.IGNORECASE)),
    ("int8", re.compile(r"(?<![a-z0-9])(?:int8|8bit|8-bit|w8)(?![a-z0-9])", re.IGNORECASE)),
    ("nf4", re.compile(r"(?<![a-z0-9])nf4(?![a-z0-9])", re.IGNORECASE)),
)
_CW_RE = re.compile(r"(?<![a-z0-9])(?:cw|channel[-_]?wise|per[-_]?channel)(?![a-z0-9])",
                    re.IGNORECASE)


def quant_info(repo_id: str, tags: list[str] | None = None) -> dict:
    """Guess the weight quantization from the repo id and hub tags.

    Returns ``{"precision": "int4"|"int8"|"nf4"|"", "cw": bool}`` where ``cw``
    marks channel-wise quantization (required by the NPU plugin).
    """
    text = " ".join([repo_id or "", *[str(t) for t in (tags or [])]])
    precision = ""
    for name, pattern in _QUANT_PATTERNS:
        if pattern.search(text):
            precision = name
            break
    return {"precision": precision, "cw": bool(_CW_RE.search(text))}


def next_cursor_from_link(link_header: str | None) -> str | None:
    """Extract the ``cursor`` value of the ``rel="next"`` Link header entry."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header or "")
    if match is None:
        return None
    values = parse_qs(urlsplit(match.group(1)).query).get("cursor")
    return values[0] if values else None


def _search_entry(model: dict, files: list[str]) -> dict:
    repo_id = model.get("id") or model.get("modelId") or ""
    quant = quant_info(repo_id, model.get("tags"))
    return {
        "repo_id": repo_id,
        "downloads": int(model.get("downloads") or 0),
        "likes": int(model.get("likes") or 0),
        "last_modified": model.get("lastModified") or "",
        "gated": bool(model.get("gated")),
        "pipeline_tag": model.get("pipeline_tag") or "",
        "library_name": model.get("library_name") or "",
        "files": len(files),
        "quant": quant["precision"],
        "cw": quant["cw"],
    }


def _hf_page(params: dict, token: str | None) -> tuple[list[dict], str | None]:
    """One ``/api/models`` page -> ``(models, next_cursor)``."""
    headers = dict(_UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=30, headers=headers) as c:
        r = c.get(HF_API, params=params)
        r.raise_for_status()
        return r.json(), next_cursor_from_link(r.headers.get("link"))


def _ir_entries(models: list[dict]) -> list[dict]:
    """Keep only repos that ship an OpenVINO IR pair."""
    out = []
    for m in models if isinstance(models, list) else []:
        files = [str(s.get("rfilename") or "") for s in (m.get("siblings") or [])]
        if is_ov_ir(files):
            out.append(_search_entry(m, files))
    return out


def _token_score(token: str, groups: set[str], compact: str) -> int:
    """How well one query token matches a repo id (word-ish, not raw substring).

    Exact word (``qwen3`` vs ``Qwen3-8B``) scores highest; a prefix scores for
    partial words (``qwen``); short tokens never match inside longer words, so a
    query like ``llama 3`` does not match ``3layers``.
    """
    if token in groups:
        return 2
    if len(token) >= 3 and any(g.startswith(token) for g in groups):
        return 1
    if len(token) >= 4 and token in compact:
        return 1
    return 0


def _rank_ir_entries(entries: list[dict], query: str, sort: str) -> list[dict]:
    """Relevance-first ordering: query coverage, then official, then popularity.

    The Hub does not rank OpenVINO conversions well for text queries, so results
    are re-ranked here. ``lastModified`` sorting keeps recency first.
    """
    tokens = [re.sub(r"[^a-z0-9]+", "", t) for t in (query or "").lower().split()]
    tokens = [t for t in tokens if t]

    def key(entry: dict):
        repo = entry["repo_id"].lower()
        groups = set(filter(None, re.split(r"[^a-z0-9]+", repo)))
        compact = re.sub(r"[^a-z0-9]+", "", repo)
        coverage = sum(_token_score(t, groups, compact) for t in tokens)
        official = repo.startswith("openvino/")
        if sort == "lastModified":
            return (coverage, official, entry["last_modified"])
        if sort == "likes":
            return (coverage, official, entry["likes"], entry["downloads"])
        return (coverage, official, entry["downloads"], entry["likes"])

    return sorted(entries, key=key, reverse=True)


def search_hf_ir(query: str, limit: int = 30, sort: str = "downloads",
                 token: str | None = None, cursor: str | None = None) -> tuple[list[dict], str | None]:
    """Search Hugging Face for models that actually ship OpenVINO IR files.

    A plain ``search=`` query is dominated by the (far more popular) PyTorch
    repos, so the first page almost never contains IR files. The ``openvino``
    tag is therefore the primary source; the official ``OpenVINO`` org is added
    because a few official conversions are untagged, and the plain search is used
    as a fallback for narrow queries. Every hit is verified with :func:`is_ov_ir`.

    Returns ``(results, next_cursor)`` for cursor-based paging.
    """
    sort_key = sort if sort in HF_SEARCH_SORTS else HF_SEARCH_SORTS[0]
    page_limit = max(1, min(max(int(limit), 1) * 2, HF_SEARCH_LIMIT_MAX))
    base = {"search": query, "sort": sort_key, "direction": -1,
            "limit": page_limit, "full": "true"}

    tagged_params = {**base, "filter": "openvino"}
    if cursor:
        tagged_params["cursor"] = cursor
    models, next_cursor = _hf_page(tagged_params, token)
    entries = _ir_entries(models)

    if not cursor:
        try:  # official conversions that are not tagged "openvino"
            official, _ = _hf_page({**base, "author": "OpenVINO"}, token)
            entries += _ir_entries(official)
        except Exception:
            pass

    seen: set[str] = set()
    merged: list[dict] = []
    for entry in _rank_ir_entries(entries, query, sort_key):
        repo_id = entry["repo_id"]
        if repo_id and repo_id not in seen:
            seen.add(repo_id)
            merged.append(entry)

    if not cursor and len(merged) < limit:
        try:  # narrow query: untagged community conversions may still match
            plain, _ = _hf_page(base, token)
            for entry in _ir_entries(plain):
                if entry["repo_id"] not in seen:
                    seen.add(entry["repo_id"])
                    merged.append(entry)
            merged = _rank_ir_entries(merged, query, sort_key)
        except Exception:
            pass
    return merged, next_cursor


def repo_ir_info(repo_id: str, token: str | None = None) -> dict | None:
    """Look up one repo directly (for 'org/name' queries); None when not OpenVINO IR."""
    headers = dict(_UA)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=30, headers=headers) as c:
            r = c.get(f"{HF_API}/{repo_id}", params={"full": "true"})
            if r.status_code != 200:
                return None
            model = r.json()
    except Exception:
        return None
    files = [str(s.get("rfilename") or "") for s in (model.get("siblings") or [])]
    if not is_ov_ir(files):
        return None
    return _search_entry(model, files)


# One in-flight HF download per repo id (double-clicks / parallel requests would
# otherwise create duplicates like model-1, model-2). Value: task id.
_hf_active: dict[str, str] = {}
_hf_active_lock = threading.Lock()


def claim_hf_download(repo_id: str) -> str:
    """Reserve the download slot for a repo.

    Returns ``""`` when claimed, or ``"active"`` (already downloading) /
    ``"done"`` (already in the library) when it must be rejected. Callers must
    call :func:`release_hf_download` when the download task ends.
    """
    with _hf_active_lock:
        if repo_id in _hf_active:
            return "active"
        for m in scan():
            if m.get("source") == "huggingface" and \
                    (m.get("origin") or "").split("@")[0] == repo_id:
                return "done"
        _hf_active[repo_id] = ""
        return ""


def set_hf_download_task(repo_id: str, tid: str) -> None:
    with _hf_active_lock:
        if repo_id in _hf_active:
            _hf_active[repo_id] = tid


def release_hf_download(repo_id: str) -> None:
    with _hf_active_lock:
        _hf_active.pop(repo_id, None)


def _safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "-", s).strip(". ")
    return s or "model"


def _unique_dir(base: str) -> Path:
    base = _safe_name(base)
    d = MODELS_DIR / base
    n = 1
    while d.exists():
        d = MODELS_DIR / f"{base}-{n}"
        n += 1
    return d


def _dir_size(d: Path) -> int:
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def detect_kind(d: Path) -> str:
    """Heuristic: GenAI task / 'classic' (IR/ONNX single model) / 'unknown'.
    embeddings/rerank/speech can't be told apart from files; user picks manually."""
    try:
        names = {p.name.lower() for p in d.iterdir() if p.is_file()}
    except OSError:
        return "unknown"
    if "model_index.json" in names:
        return "image_generation"  # diffusers-style layout
    llm_markers = {"openvino_tokenizer.xml", "openvino_detokenizer.xml", "tokenizer.json",
                   "generation_config.json", "graph.pbtxt"}
    if names & llm_markers:
        return "text_generation"
    xmls = [n for n in names if n.endswith(".xml") and not n.startswith("openvino_")]
    if xmls or any(n.endswith(".onnx") for n in names):
        return "classic"
    # look one level down (e.g. zip extracted into a subfolder)
    for p in d.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            k = detect_kind(p)
            if k != "unknown":
                return k
    return "unknown"


def model_size_bytes(name: str) -> int:
    d = MODELS_DIR / name
    return _dir_size(d) if d.is_dir() else 0


def scan() -> list[dict]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for d in sorted(MODELS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir():
            continue
        meta = {}
        mj = d / _META
        if mj.exists():
            try:
                meta = json.loads(mj.read_text(encoding="utf-8"))
            except Exception:
                pass
        n_files = sum(1 for p in d.rglob("*") if p.is_file())
        out.append({
            "name": d.name,
            "size": _dir_size(d),
            "files": n_files,
            "kind": detect_kind(d),
            "source": meta.get("source", ""),
            "origin": meta.get("origin", ""),
            "downloaded_at": meta.get("downloaded_at", 0),
        })
    return out


def delete(name: str, lang: str | None = None) -> None:
    d = MODELS_DIR / name
    if not is_within(d, MODELS_DIR) or not d.is_dir():
        raise RuntimeError(tr(lang, "err.model_not_found_id", name=name))
    rmtree(d, lang=lang)


_CONVERT_SCRIPT = """\
from pathlib import Path
from transformers import AutoTokenizer
from openvino_tokenizers import convert_tokenizer
import openvino as ov

model_dir = Path({model_dir!r})
tok_src = model_dir / "tokenizer"
if not (tok_src / "tokenizer_config.json").is_file():
    tok_src = model_dir
target = model_dir / "tokenizer"
if not target.is_dir():
    target = model_dir

tokenizer = AutoTokenizer.from_pretrained(str(tok_src), trust_remote_code=True)
tokenizer_model, detokenizer_model = convert_tokenizer(tokenizer, with_detokenizer=True)
ov.save_model(tokenizer_model, str(target / "openvino_tokenizer.xml"), compress_to_fp16=False)
if detokenizer_model is not None:
    ov.save_model(detokenizer_model, str(target / "openvino_detokenizer.xml"), compress_to_fp16=False)
print("CONVERTED")
"""


def tokenizer_target_dir(model_dir: Path) -> Path:
    """Where OVMS looks for openvino_tokenizer.xml (inside tokenizer/ when present)."""
    sub = model_dir / "tokenizer"
    return sub if sub.is_dir() else model_dir


def convert_tokenizer_worker(tid: str, model: str) -> None:
    """Convert a model's HF tokenizer to OpenVINO IR using the runtime's Python.

    The converter packages (openvino / openvino-tokenizers / transformers) are
    installed into the OVMS runtime on first use, so the app itself stays small.
    """
    lang = tasks.lang_of(tid)
    try:
        from . import ovms as ovmsvc

        model_dir = MODELS_DIR / model
        if not model_dir.is_dir():
            raise RuntimeError(tr(lang, "err.model_not_found_id", name=model))
        runtime_id = str(load_config().get("selected_runtime") or "")
        if not runtime_id:
            raise RuntimeError(tr(lang, "err.no_runtime"))
        exe = ovmsvc.runtime_exe(runtime_id, lang=lang)
        python = ovmsvc.runtime_python(runtime_id, lang=lang)
        env = ovmsvc._runtime_env(exe)
        flags = subprocess_flags()

        tasks.set_message(tid, "task.tokenizer_checking")
        probe = subprocess.run([str(python), "-c", "import openvino_tokenizers, transformers"],
                               capture_output=True, text=True, timeout=180, env=env,
                               cwd=str(exe.parent), creationflags=flags, errors="replace")
        if probe.returncode != 0:
            tasks.set_message(tid, "task.tokenizer_installing")
            install = subprocess.run(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                 "openvino", "openvino-tokenizers", "transformers"],
                capture_output=True, text=True, timeout=3600, env=env,
                cwd=str(exe.parent), creationflags=flags, errors="replace")
            if install.returncode != 0:
                detail = ((install.stderr or "") + (install.stdout or ""))[-300:]
                raise RuntimeError(tr(lang, "err.tokenizer_install_failed", error=detail))

        tasks.set_message(tid, "task.tokenizer_converting")
        script = _CONVERT_SCRIPT.format(model_dir=str(model_dir))
        convert = subprocess.run([str(python), "-c", script], capture_output=True, text=True,
                                 timeout=1800, env=env, cwd=str(exe.parent),
                                 creationflags=flags, errors="replace")
        if convert.returncode != 0 or not (tokenizer_target_dir(model_dir) / "openvino_tokenizer.xml").is_file():
            detail = ((convert.stderr or "") + (convert.stdout or ""))[-300:]
            raise RuntimeError(tr(lang, "err.tokenizer_convert_failed", error=detail))
        tasks.finish(tid, "task.tokenizer_done")
    except Exception as e:
        tasks.fail(tid, e)


def read_meta(d: Path) -> dict:
    """The ``.ovmsui.json`` metadata for a model directory ({} when missing)."""
    try:
        return json.loads((d / _META).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta(d: Path, source: str, origin: str) -> None:
    try:
        (d / _META).write_text(json.dumps(
            {"source": source, "origin": origin, "downloaded_at": time.time()},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _hf_expected_bytes(repo_id: str, revision: str | None,
                       allow_patterns: list[str] | None, token: str | None,
                       ignore_patterns: list[str] | None = None) -> int:
    """Best-effort total size for progress display (0 = unknown)."""
    import fnmatch
    try:
        from huggingface_hub import HfApi
        info = HfApi(token=token).model_info(repo_id, revision=revision or None,
                                             files_metadata=True)
        total = 0
        for f in info.siblings or []:
            name = getattr(f, "rfilename", "") or ""
            size = getattr(f, "size", None) or 0
            if allow_patterns and not any(fnmatch.fnmatch(name, p) for p in allow_patterns):
                continue
            if ignore_patterns and any(fnmatch.fnmatch(name, p) for p in ignore_patterns):
                continue
            if name.endswith((".gitattributes", ".lock")):
                continue
            total += int(size)
        return total
    except Exception:
        return 0


def download_hf_worker(tid: str, repo_id: str, revision: str | None,
                       allow_patterns: list[str] | None, token: str | None,
                       ignore_patterns: list[str] | None = None) -> None:
    lang = tasks.lang_of(tid)
    dest = _unique_dir(repo_id.split("/")[-1])
    dest.mkdir(parents=True, exist_ok=True)
    tasks.set_message(tid, "task.hf_downloading", repo=repo_id)
    try:
        from huggingface_hub import snapshot_download
        from tqdm import tqdm as _tqdm

        expected = _hf_expected_bytes(repo_id, revision, allow_patterns, token, ignore_patterns)
        bars: dict[int, int] = {}
        bars_lock = threading.Lock()

        class _PTqdm(_tqdm):  # hf_hub v1: bar totals are file counts; track bytes per bar
            def update(self, n=1):
                if not tasks.is_running(tid):  # raises inside snapshot_download on cancel
                    raise RuntimeError(tr(lang, "err.cancelled"))
                super().update(n)
                with bars_lock:
                    bars[id(self)] = int(self.n or 0)
                    done = sum(bars.values())
                if expected > 0:
                    tasks.set_progress(tid, min(done, expected), expected)
                else:
                    tasks.update(tid, downloaded_bytes=done)

        kwargs = dict(repo_id=repo_id, revision=revision or None, local_dir=str(dest),
                      allow_patterns=allow_patterns or None,
                      ignore_patterns=list(ignore_patterns) if ignore_patterns else None,
                      token=token or None, max_workers=4)
        try:
            snapshot_download(tqdm_class=_PTqdm, **kwargs)
        except TypeError:  # tqdm_class unsupported in this hf_hub version
            snapshot_download(**kwargs)
        _write_meta(dest, "huggingface",
                    repo_id + (f"@{revision}" if revision else ""))
        tasks.finish(tid, "task.done_name", name=dest.name)
    except Exception as e:
        # remove a partial folder when the download was cancelled or produced nothing
        if not tasks.is_running(tid) or not any(dest.iterdir()):
            try:
                rmtree(dest, attempts=2, lang=lang)
            except Exception:
                pass
        tasks.fail(tid, e)
    finally:
        release_hf_download(repo_id)


def _filename_from_response(r: httpx.Response, url: str) -> str:
    cd = r.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd, re.I)
    if m:
        return _safe_name(unquote(m.group(1)))
    base = urlsplit(url).path.rsplit("/", 1)[-1]
    return _safe_name(unquote(base)) if base else "download.bin"


def download_url_worker(tid: str, url: str, name: str | None, extract: bool) -> None:
    lang = tasks.lang_of(tid)
    folder: Path | None = None
    try:
        tasks.set_message(tid, "task.downloading")
        with httpx.stream("GET", url, headers=_UA, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            fname = _filename_from_response(r, str(r.url))
            total = int(r.headers.get("content-length") or 0)
            folder = _unique_dir(name or Path(fname).stem)
            folder.mkdir(parents=True, exist_ok=True)
            dest_file = folder / fname
            done = 0
            with dest_file.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    if not tasks.is_running(tid):
                        raise RuntimeError(tr(lang, "err.cancelled"))
                    f.write(chunk)
                    done += len(chunk)
                    tasks.set_progress(tid, done, total)
        if extract and re.search(r"\.(zip|tar\.gz|tgz|tar)$", fname, re.I):
            tasks.set_message(tid, "task.extracting")
            tasks.update(tid, progress=None)
            shutil.unpack_archive(str(dest_file), str(folder))
            dest_file.unlink(missing_ok=True)
        _write_meta(folder, "url", url)
        tasks.finish(tid, "task.done_name", name=folder.name)
    except Exception as e:
        if folder is not None and not tasks.is_running(tid):
            try:
                rmtree(folder, attempts=2, lang=lang)
            except Exception:
                pass
        tasks.fail(tid, e)
