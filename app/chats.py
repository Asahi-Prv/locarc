"""Chat session persistence (JSON files under data/chats)."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from .config import DATA_DIR
from .i18n import tr

CHATS_DIR = DATA_DIR / "chats"
_ID_RE = re.compile(r"^[0-9a-f]{12}$")

# per-chat generation params; max_tokens defaults big enough for thinking models
DEFAULT_PARAMS: dict = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_tokens": 4096,
    "repetition_penalty": 1.0,
    "system_prompt": "",
    "suppress_thinking": False,  # -> chat_template_kwargs.enable_thinking=false (supported models)
    # extra chat_template_kwargs (JSON object text); the parameter names come
    # from the model's own chat template (see models.chat_template_vars)
    "template_kwargs": "",
}
_PARAM_FLOAT = ("temperature", "top_p", "repetition_penalty")
_PARAM_INT = ("top_k", "max_tokens")
_PARAM_STR = ("system_prompt", "template_kwargs")
_PARAM_BOOL = ("suppress_thinking",)


def _ensure() -> None:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)


def _check_id(cid: str, lang: str | None = None) -> None:
    if not _ID_RE.match(cid or ""):
        raise RuntimeError(tr(lang, "err.bad_chat_id"))


def _path(cid: str, lang: str | None = None) -> Path:
    _check_id(cid, lang)
    return CHATS_DIR / f"{cid}.json"


def list_chats(lang: str | None = None) -> list[dict]:
    _ensure()
    out = []
    for p in CHATS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "id": d["id"],
                "title": d.get("title") or tr(lang, "chat.untitled"),
                "model": d.get("model", ""),
                "updated_at": d.get("updated_at", 0),
            })
        except Exception:
            continue
    out.sort(key=lambda c: c.get("updated_at", 0), reverse=True)
    return out


def create(lang: str | None = None) -> dict:
    _ensure()
    now = time.time()
    cid = uuid.uuid4().hex[:12]
    chat = {
        "id": cid,
        "title": tr(lang, "chat.new_title"),
        "model": "",
        "params": dict(DEFAULT_PARAMS),
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    _path(cid).write_text(json.dumps(chat, ensure_ascii=False, indent=1), encoding="utf-8")
    return chat


def get(cid: str, lang: str | None = None) -> dict:
    p = _path(cid, lang)
    if not p.exists():
        raise RuntimeError(tr(lang, "err.chat_not_found"))
    return json.loads(p.read_text(encoding="utf-8"))


def _clean_params(src) -> dict:
    merged = dict(DEFAULT_PARAMS)
    if not isinstance(src, dict):
        return merged
    for k in DEFAULT_PARAMS:
        if k not in src:
            continue
        try:
            if k in _PARAM_FLOAT:
                merged[k] = float(src[k])
            elif k in _PARAM_INT:
                merged[k] = int(float(src[k]))
            elif k in _PARAM_STR:
                merged[k] = str(src.get(k, ""))[:4000]
            elif k in _PARAM_BOOL:
                merged[k] = bool(src[k])
        except (TypeError, ValueError):
            pass
    return merged


def _clean_messages(src) -> list[dict]:
    msgs = []
    if not isinstance(src, list):
        return msgs
    for m in src:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("system", "user", "assistant"):
            continue
        msg = {"role": role, "content": str(m.get("content", ""))}
        think = str(m.get("think") or "")
        if think:
            msg["think"] = think[:20000]
        att = _clean_attachments(m.get("attachments"))
        if att:
            msg["attachments"] = att
        stats = m.get("stats")
        if isinstance(stats, dict):
            clean = {}
            for key in ("sec", "tokens", "tps"):
                value = stats.get(key)
                if isinstance(value, (int, float)):
                    clean[key] = round(float(value), 2)
            if clean:
                msg["stats"] = clean
        msgs.append(msg)
    return msgs


# per-attachment cap on the stored base64 payload (data URL text, ~6 MB binary)
_MAX_ATTACHMENT_CHARS = 8 * 1024 * 1024


def _clean_attachments(src) -> list[dict]:
    """User-message attachments: text file contents and image data URLs.

    The chat UI keeps them so later turns still show the file to the model
    (text is re-inlined, images are sent as image_url parts) and so the bubble
    can render a thumbnail/chip after a reload.
    """
    out = []
    if not isinstance(src, list):
        return out
    for a in src:
        if not isinstance(a, dict):
            continue
        kind = a.get("kind")
        if kind not in ("text", "image"):
            continue
        data = a.get("data")
        if not isinstance(data, str) or not data or len(data) > _MAX_ATTACHMENT_CHARS:
            continue
        out.append({
            "kind": kind,
            "name": str(a.get("name") or "")[:200],
            "mime": str(a.get("mime") or "")[:100],
            "data": data,
        })
        if len(out) >= 8:
            break
    return out


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def save(cid: str, data: dict, lang: str | None = None) -> dict:
    chat = get(cid, lang)
    if "title" in data:
        chat["title"] = str(data["title"])[:120] or tr(lang, "chat.untitled")
    if "model" in data:
        chat["model"] = str(data["model"])
    if "params" in data and isinstance(data["params"], dict):
        chat["params"] = _clean_params(data["params"])
    if "messages" in data and isinstance(data["messages"], list):
        chat["messages"] = _clean_messages(data["messages"])
    chat["updated_at"] = time.time()
    _path(cid).write_text(json.dumps(chat, ensure_ascii=False, indent=1), encoding="utf-8")
    return chat


def export_all() -> list[dict]:
    """Every stored chat as-is, oldest first (backup / migration bundle)."""
    _ensure()
    out = []
    for p in CHATS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and _ID_RE.match(str(d.get("id") or "")):
            out.append(d)
    out.sort(key=lambda c: c.get("updated_at", 0))
    return out


def import_many(items: list, lang: str | None = None) -> dict:
    """Merge exported chats: existing ids are overwritten, new ids are added."""
    _ensure()
    result = {"imported": 0, "replaced": 0, "skipped": 0}
    for raw in items or []:
        if not isinstance(raw, dict):
            result["skipped"] += 1
            continue
        cid = str(raw.get("id") or "")
        if not _ID_RE.match(cid):
            result["skipped"] += 1
            continue
        now = time.time()
        path = CHATS_DIR / f"{cid}.json"
        is_new = not path.exists()
        chat = {
            "id": cid,
            "title": str(raw.get("title") or tr(lang, "chat.untitled"))[:120],
            "model": str(raw.get("model") or ""),
            "params": _clean_params(raw.get("params")),
            "messages": _clean_messages(raw.get("messages")),
            "created_at": _as_float(raw.get("created_at"), now),
            "updated_at": _as_float(raw.get("updated_at"), now),
        }
        path.write_text(json.dumps(chat, ensure_ascii=False, indent=1), encoding="utf-8")
        result["imported" if is_new else "replaced"] += 1
    return result


def delete(cid: str, lang: str | None = None) -> None:
    p = _path(cid, lang)
    if p.exists():
        p.unlink()


def delete_all() -> int:
    """Remove every stored chat; returns how many files were deleted."""
    _ensure()
    deleted = 0
    for p in CHATS_DIR.glob("*.json"):
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted
