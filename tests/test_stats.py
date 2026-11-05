"""Usage statistics: local JSONL store, SSE probe, proxy instrumentation, API."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import stats
from app.config import CONFIG_PATH
from app.main import _stats_ctx, app

client = TestClient(app)


@pytest.fixture()
def clean_stats():
    stats.clear()
    yield
    stats.clear()


@pytest.fixture()
def clean_config():
    CONFIG_PATH.unlink(missing_ok=True)
    yield
    CONFIG_PATH.unlink(missing_ok=True)


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> None:
        self.t += dt


# ------------------------------------------------------------------ stream probe


def test_stream_probe_extracts_usage_and_timings():
    clock = FakeClock()
    probe = stats.StreamProbe(clock=clock)
    clock.tick(0.2)
    probe.feed(b'data: {"choices":[{"delta":{"role":"assistant","content":null},"finish_reason":null}]}\n\n')
    clock.tick(0.1)  # t=0.3: first token
    probe.feed(b'data: {"choices":[{"delta":{"content":"He"}}]}\n\n')
    clock.tick(2.0)  # t=2.3: second token
    # split mid-JSON and mid-event across chunk boundaries
    probe.feed(b'data: {"choices":[{"delta":{"cont')
    probe.feed(b'ent":"llo"}}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    clock.tick(0.05)  # t=2.35: usage chunk (smoke test; no content)
    probe.feed(b'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}\n\n')
    clock.tick(0.05)  # t=2.4: [DONE]
    probe.feed(b"data: [DONE]\n\n")
    r = probe.result()
    assert r["ttft_ms"] == 300
    assert r["gen_ms"] == 2000
    assert r["total_ms"] == 2400
    assert r["prompt_tokens"] == 5
    assert r["completion_tokens"] == 3
    assert r["tokens_approx"] is False
    assert r["tps"] == 1.5
    assert r["finish_reason"] == "stop"
    assert r["done"] is True


def test_stream_probe_falls_back_to_approximate_tokens():
    probe = stats.StreamProbe()
    probe.feed(b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n')
    probe.feed(b'data: {"choices":[{"delta":{"reasoning_content":"b"}}]}\n\n')
    probe.feed(b"data: [DONE]\n\n")
    r = probe.result()
    assert r["completion_tokens"] == 2
    assert r["tokens_approx"] is True
    assert "prompt_tokens" not in r


# ------------------------------------------------------------------ store


def test_record_and_summary(clean_stats):
    now = time.time()
    stats.record({"ts": now - 100, "kind": "chat", "model": "org/m1", "device": "GPU",
                  "prompt_tokens": 10, "completion_tokens": 100, "gen_ms": 2000,
                  "ttft_ms": 100, "tps": 50.0, "ok": True})
    stats.record({"ts": now - 50, "kind": "chat", "model": "org/m1", "device": "GPU",
                  "completion_tokens": 30, "gen_ms": 1000, "ttft_ms": 200, "tps": 30.0,
                  "ok": False, "cancelled": True})
    stats.record({"ts": now - 400 * 86400, "kind": "chat", "model": "org/old",
                  "completion_tokens": 999, "ok": True})  # outside the 30-day window
    s = stats.summary(days=30)
    assert s["totals"]["runs"] == 2
    assert s["totals"]["ok"] == 1
    assert s["totals"]["cancelled"] == 1
    assert s["totals"]["failed"] == 0
    assert s["totals"]["tokens_in"] == 10
    assert s["totals"]["tokens_out"] == 130
    assert s["totals"]["avg_tps"] == 40.0
    assert s["totals"]["avg_ttft_ms"] == 150
    assert [m["model"] for m in s["models"]] == ["org/m1"]
    assert s["models"][0]["runs"] == 2 and s["models"][0]["device"] == "GPU"
    assert s["models"][0]["avg_tps"] == 40.0
    assert [r["ts"] for r in s["recent"]] == [round(now - 50, 3), round(now - 100, 3)]
    assert len(s["series"]) == 30
    assert s["series"][-1]["runs"] == 2


def test_record_sanitizes_and_never_raises(clean_stats):
    stats.record({"kind": "chat", "model": "x" * 500, "tps": float("nan"),
                  "completion_tokens": -5, "ok": True})
    (run,) = stats.load_runs()
    assert len(run["model"]) == 200
    assert "tps" not in run and "completion_tokens" not in run
    assert run["ok"] is True
    stats.record({})  # no-op, no exception
    stats.record(None)  # type: ignore[arg-type]


def test_malformed_lines_are_ignored(clean_stats):
    stats.record({"kind": "chat", "model": "m", "ok": True})
    with stats.RUNS_PATH.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
        fh.write('{"ts": "not-a-number"}\n')
    assert len(stats.load_runs()) == 1
    assert stats.summary()["totals"]["runs"] == 1


# ------------------------------------------------------------------ API


def test_stats_api(clean_stats):
    assert client.get("/api/stats/summary").json()["totals"]["runs"] == 0
    stats.record({"kind": "chat", "model": "m", "ok": True,
                  "completion_tokens": 3, "tps": 9.0})
    got = client.get("/api/stats/summary?days=7").json()
    assert got["totals"]["runs"] == 1
    assert got["recent"][0]["model"] == "m"
    assert client.get("/api/stats/summary?days=0").json()["days"] == 1  # clamped
    assert client.delete("/api/stats").json()["ok"] is True
    assert client.get("/api/stats/summary").json()["totals"]["runs"] == 0


def test_stats_enabled_config(clean_config):
    assert client.get("/api/config").json()["stats_enabled"] is True
    client.post("/api/config", json={"stats_enabled": False})
    assert client.get("/api/config").json()["stats_enabled"] is False


# ------------------------------------------------------------------ proxy hooks


def test_proxy_injects_usage_and_captures_context():
    body = json.dumps({"model": "m", "stream": True, "messages": []}).encode()
    st = {"mode": "text_generation", "device": "GPU", "runtime_id": "ovms_x", "model": "m"}
    new, cap = _stats_ctx("v3/chat/completions", body, st, {})
    assert cap == {"kind": "chat", "model": "m", "mode": "text_generation",
                   "device": "GPU", "runtime": "ovms_x", "stream": True}
    assert json.loads(new)["stream_options"]["include_usage"] is True


def test_proxy_skips_helper_calls_and_disabled_stats():
    body = json.dumps({"model": "m", "stream": True}).encode()
    # stream=false (auto titles) is left untouched and not recorded
    one_shot = json.dumps({"model": "m", "stream": False}).encode()
    new, cap = _stats_ctx("v3/chat/completions", one_shot, {"mode": "text_generation"}, {})
    assert cap is None and new == one_shot
    # stats disabled -> pure passthrough
    new, cap = _stats_ctx("v3/chat/completions", body, {"mode": "text_generation"},
                          {"stats_enabled": False})
    assert cap is None and new == body
    # non-chat, non-image paths are untouched
    new, cap = _stats_ctx("v2/models/m/infer", body, {}, {})
    assert cap is None and new == body
    # malformed body never raises
    new, cap = _stats_ctx("v3/chat/completions", b"{not json", {}, {})
    assert cap is None and new == b"{not json"


def test_proxy_captures_images_without_rewriting():
    body = json.dumps({"model": "m", "prompt": "x"}).encode()
    new, cap = _stats_ctx("v3/images/generations", body, {"device": "GPU"}, {})
    assert cap == {"kind": "image", "model": "m", "mode": "", "device": "GPU", "runtime": ""}
    assert new == body


def test_proxy_streams_and_records_end_to_end(monkeypatch, clean_stats, clean_config):
    import httpx

    from app import main as mainmod

    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        sse = (
            b'data: {"choices":[{"delta":{"role":"assistant","content":null}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            b'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":1,"total_tokens":5}}\n\n'
            b"data: [DONE]\n\n"
        )
        return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(mainmod, "_client", lambda: httpx.AsyncClient(transport=transport))
    monkeypatch.setattr(mainmod.ovms.server, "status", lambda: {
        "running": True, "ready": True, "mode": "text_generation",
        "device": "GPU", "runtime_id": "r1", "model": "m"})

    r = client.post("/proxy/v3/chat/completions",
                    json={"model": "m", "stream": True,
                          "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and "OK" in r.text
    assert seen["body"]["stream_options"]["include_usage"] is True
    runs = stats.load_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run["ok"] is True and run["done"] is True and run["stream"] is True
    assert run["cancelled"] is False
    assert run["model"] == "m" and run["device"] == "GPU" and run["runtime"] == "r1"
    assert run["prompt_tokens"] == 4 and run["completion_tokens"] == 1
    assert run["tokens_approx"] is False and run["finish_reason"] == "stop"
