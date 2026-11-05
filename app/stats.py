"""Local usage statistics — recorded on this machine only, never sent anywhere.

Every chat / image-generation request served through the UI proxy becomes one
JSON line in ``data/stats/runs.jsonl``. The Statistics tab reads the file back
and aggregates on demand; ``config.stats_enabled`` turns recording off entirely.

Timings and token counts come from :class:`StreamProbe`, which parses the
chat-completions SSE stream while it is relayed to the browser. When the server
reports exact usage (the proxy asks for it via ``stream_options.include_usage``)
those counts are stored as-is; otherwise content chunks are counted and the
record is flagged with ``tokens_approx``.
"""
from __future__ import annotations

import codecs
import json
import os
import threading
import time

from .config import DATA_DIR

STATS_DIR = DATA_DIR / "stats"
RUNS_PATH = STATS_DIR / "runs.jsonl"

# Keep the store small: trim it once it grows past this, keeping the newest runs.
MAX_BYTES = 4_000_000
KEEP_RUNS = 15_000

MAX_DAYS = 365
MAX_MODELS = 50
MAX_RECENT = 100

_TEXT_LIMITS = {"kind": 32, "model": 200, "mode": 32, "device": 40,
                "runtime": 160, "finish_reason": 32, "error": 200}
_NUM_KEYS = ("prompt_tokens", "completion_tokens", "ttft_ms", "gen_ms", "total_ms", "tps")
_BOOL_KEYS = ("stream", "tokens_approx", "done", "ok", "cancelled")

_lock = threading.Lock()


def _ensure() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)


class StreamProbe:
    """Timings + token usage from a chat-completions SSE byte stream.

    ``feed()`` is called with the raw bytes of each relayed chunk; ``result()``
    returns the record fields once the stream ends (also on aborts, with the
    partial information gathered so far).
    """

    def __init__(self, t0: float | None = None, clock=time.perf_counter) -> None:
        self._clock = clock
        self.t0 = self._clock() if t0 is None else t0
        self.first_at: float | None = None   # first content-bearing chunk
        self.last_at: float | None = None    # last content-bearing chunk
        self.end_at: float | None = None     # [DONE]
        self.done = False
        self.chunks = 0                      # content deltas (token fallback)
        self.usage: dict | None = None
        self.finish_reason: str | None = None
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buf = ""

    def feed(self, chunk: bytes) -> None:
        self._buf += self._dec.decode(chunk)
        while "\n\n" in self._buf:
            event, self._buf = self._buf.split("\n\n", 1)
            self._event(event)

    def _event(self, event: str) -> None:
        for line in event.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                self.done = True
                self.end_at = self._clock()
                continue
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            usage = obj.get("usage")
            if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                self.usage = usage
            choices = obj.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            if choice.get("finish_reason"):
                self.finish_reason = str(choice["finish_reason"])
            delta = choice.get("delta") or {}
            if delta.get("content") is not None or delta.get("reasoning_content") is not None:
                now = self._clock()
                if self.first_at is None:
                    self.first_at = now
                self.last_at = now
                self.chunks += 1

    def result(self) -> dict:
        out: dict = {}
        if self.first_at is not None:
            out["ttft_ms"] = max(0, round((self.first_at - self.t0) * 1000))
        if self.first_at is not None and self.last_at is not None:
            out["gen_ms"] = max(0, round((self.last_at - self.first_at) * 1000))
        out["total_ms"] = max(0, round(((self.end_at or self._clock()) - self.t0) * 1000))
        if self.usage:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = self.usage.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    out[key] = int(value)
            out["tokens_approx"] = False
        elif self.chunks:
            out["completion_tokens"] = self.chunks
            out["tokens_approx"] = True
        if self.finish_reason:
            out["finish_reason"] = self.finish_reason
        out["done"] = self.done
        tokens, gen_ms = out.get("completion_tokens"), out.get("gen_ms")
        if tokens and gen_ms and gen_ms > 0:
            out["tps"] = round(tokens / (gen_ms / 1000.0), 1)
        return out


def record(run: dict) -> None:
    """Append one sanitized run to the store.

    Statistics must never break proxying, so any malformed input is dropped
    and all I/O errors are swallowed.
    """
    try:
        if not run:
            return
        ts = run.get("ts")
        ev: dict = {"ts": round(float(ts), 3) if isinstance(ts, (int, float)) else round(time.time(), 3)}
        for key, limit in _TEXT_LIMITS.items():
            value = run.get(key)
            if value not in (None, ""):
                ev[key] = str(value)[:limit]
        for key in _NUM_KEYS:
            value = run.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
                continue
            ev[key] = round(float(value), 1) if key == "tps" else int(value)
        for key in _BOOL_KEYS:
            if run.get(key) is not None:
                ev[key] = bool(run[key])
        line = json.dumps(ev, ensure_ascii=False, separators=(",", ":"))
        _ensure()
        with _lock:
            with RUNS_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            _maybe_trim()
    except Exception:
        pass


def _maybe_trim() -> None:
    """Rewrite the store keeping only the newest runs (called under ``_lock``)."""
    try:
        if RUNS_PATH.stat().st_size <= MAX_BYTES:
            return
        lines = RUNS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        tmp = RUNS_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(line + "\n" for line in lines[-KEEP_RUNS:]), encoding="utf-8")
        os.replace(tmp, RUNS_PATH)
    except OSError:
        pass


def load_runs() -> list[dict]:
    try:
        text = RUNS_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    runs: list[dict] = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and isinstance(ev.get("ts"), (int, float)):
            runs.append(ev)
    return runs


def _avg(total: float, count: int, digits: int = 1) -> float | None:
    return round(total / count, digits) if count else None


def summary(days: int = 30, recent: int = 25) -> dict:
    """Aggregate the stored runs for the Statistics tab."""
    days = max(1, min(int(days), MAX_DAYS))
    recent = max(0, min(int(recent), MAX_RECENT))
    now = time.time()
    cutoff = now - days * 86400
    runs = [r for r in load_runs() if float(r.get("ts") or 0) >= cutoff]

    totals = {"runs": len(runs), "ok": 0, "cancelled": 0, "failed": 0,
              "tokens_in": 0, "tokens_out": 0, "approx_runs": 0}
    tps_values: list[float] = []
    ttft_values: list[float] = []
    models: dict[tuple[str, str], dict] = {}
    by_day: dict[str, dict] = {}

    for r in runs:
        ok = bool(r.get("ok"))
        if ok:
            totals["ok"] += 1
        elif r.get("cancelled"):
            totals["cancelled"] += 1
        else:
            totals["failed"] += 1
        if r.get("tokens_approx"):
            totals["approx_runs"] += 1
        totals["tokens_in"] += int(r.get("prompt_tokens") or 0)
        totals["tokens_out"] += int(r.get("completion_tokens") or 0)
        if isinstance(r.get("tps"), (int, float)):
            tps_values.append(float(r["tps"]))
        if isinstance(r.get("ttft_ms"), (int, float)):
            ttft_values.append(float(r["ttft_ms"]))

        key = (str(r.get("model") or "?"), str(r.get("device") or ""))
        m = models.setdefault(key, {"model": key[0], "device": key[1], "runs": 0, "ok": 0,
                                    "tokens_out": 0, "tps_sum": 0.0, "tps_n": 0,
                                    "ttft_sum": 0.0, "ttft_n": 0, "last_ts": 0.0})
        m["runs"] += 1
        m["ok"] += 1 if ok else 0
        m["tokens_out"] += int(r.get("completion_tokens") or 0)
        if isinstance(r.get("tps"), (int, float)):
            m["tps_sum"] += float(r["tps"])
            m["tps_n"] += 1
        if isinstance(r.get("ttft_ms"), (int, float)):
            m["ttft_sum"] += float(r["ttft_ms"])
            m["ttft_n"] += 1
        m["last_ts"] = max(m["last_ts"], float(r.get("ts") or 0))

        day = time.strftime("%Y-%m-%d", time.localtime(float(r.get("ts") or 0)))
        d = by_day.setdefault(day, {"runs": 0, "tokens_out": 0, "tps_sum": 0.0, "tps_n": 0})
        d["runs"] += 1
        d["tokens_out"] += int(r.get("completion_tokens") or 0)
        if isinstance(r.get("tps"), (int, float)):
            d["tps_sum"] += float(r["tps"])
            d["tps_n"] += 1

    totals["avg_tps"] = _avg(sum(tps_values), len(tps_values))
    totals["avg_ttft_ms"] = _avg(sum(ttft_values), len(ttft_values), 0)
    if totals["avg_ttft_ms"] is not None:
        totals["avg_ttft_ms"] = int(totals["avg_ttft_ms"])

    model_rows = []
    for m in models.values():
        model_rows.append({
            "model": m["model"], "device": m["device"], "runs": m["runs"], "ok": m["ok"],
            "tokens_out": m["tokens_out"],
            "avg_tps": _avg(m["tps_sum"], m["tps_n"]),
            "avg_ttft_ms": int(_avg(m["ttft_sum"], m["ttft_n"], 0)) if m["ttft_n"] else None,
            "last_ts": round(m["last_ts"], 3),
        })
    model_rows.sort(key=lambda m: (m["runs"], m["tokens_out"]), reverse=True)

    series = []
    for i in range(days - 1, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
        d = by_day.get(day, {})
        series.append({"date": day, "runs": d.get("runs", 0),
                       "tokens_out": d.get("tokens_out", 0),
                       "avg_tps": _avg(d.get("tps_sum", 0.0), d.get("tps_n", 0))})

    recent_rows = sorted(runs, key=lambda r: float(r.get("ts") or 0), reverse=True)[:recent]
    return {"days": days, "totals": totals, "models": model_rows[:MAX_MODELS],
            "series": series, "recent": recent_rows, "generated_at": now}


def clear() -> None:
    with _lock:
        try:
            RUNS_PATH.unlink()
        except OSError:
            pass
