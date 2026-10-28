"""API smoke tests. They run against a temporary data directory (see conftest)."""
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import i18n
from app.config import CONFIG_PATH, load_config, save_config
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def reset_config() -> None:
    CONFIG_PATH.unlink(missing_ok=True)


def test_static_ui_is_served():
    assert client.get("/").status_code == 200
    assert "LocArc" in client.get("/").text
    # the key must be defined (not just referenced by isDefaultTitle), or the
    # frontend never recognizes the default chat title
    assert '"chat.new_title":' in client.get("/i18n.js").text
    assert "applyI18n" in client.get("/app.js").text
    assert "renderMarkdown" in client.get("/markdown.js").text


def test_config_defaults_and_port_validation():
    reset_config()
    cfg = client.get("/api/config").json()
    assert cfg["ui_port"] == 8810
    r = client.post("/api/config", json={"rest_port": 99999})
    assert r.status_code == 400
    assert "65535" in r.json()["detail"]


def test_errors_are_localized():
    r = client.get("/api/ovms/versions?channel=bogus", headers={"Accept-Language": "en"})
    assert r.status_code == 400 and "stable" in r.json()["detail"]
    r = client.get("/api/ovms/versions?channel=bogus", headers={"Accept-Language": "ja"})
    assert r.status_code == 400 and "いずれか" in r.json()["detail"]


def test_chats_use_request_language():
    reset_config()
    r = client.post("/api/chats", headers={"Accept-Language": "ja"})
    assert r.status_code == 200 and r.json()["title"] == "新しいチャット"
    cid = r.json()["id"]
    assert client.get(f"/api/chats/{cid}").json()["params"]["max_tokens"] == 4096
    assert client.post("/api/chats", headers={"Accept-Language": "en"}).json()["title"] == "New chat"


def test_chats_keep_think_and_stats():
    reset_config()
    cid = client.post("/api/chats").json()["id"]
    body = {"messages": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo", "think": "chain of thought",
         "stats": {"sec": 1.5, "tokens": 10, "tps": 6.7}, "junk": 1},
    ]}
    saved = client.put(f"/api/chats/{cid}", json=body).json()
    message = saved["messages"][1]
    assert message["think"] == "chain of thought"
    assert message["stats"] == {"sec": 1.5, "tokens": 10, "tps": 6.7}
    assert "junk" not in message
    reloaded = client.get(f"/api/chats/{cid}").json()
    assert reloaded["messages"][1]["think"] == "chain of thought"
    reset_config()


def test_path_traversal_is_rejected():
    reset_config()
    assert client.delete("/api/ovms/runtime/..%5C..%5CWindows").status_code == 404
    assert client.delete("/api/models/..%5Cconfig.json").status_code == 404


def test_load_options_warns_missing_image_tokenizer():
    reset_config()
    from app.config import MODELS_DIR
    model = MODELS_DIR / "imgmodel"
    model.mkdir(parents=True, exist_ok=True)
    (model / "model_index.json").write_text("{}", encoding="utf-8")
    r = client.get("/api/model/load_options?model=imgmodel")
    assert r.json()["kind"] == "image_generation"
    assert "image_tokenizer_missing" in r.json()["warnings"]
    (model / "openvino_tokenizer.xml").write_text("<net/>", encoding="utf-8")
    r = client.get("/api/model/load_options?model=imgmodel")
    assert r.json()["warnings"] == []
    reset_config()


def test_hf_download_claim():
    reset_config()
    from app import models as modelsvc
    from app.config import MODELS_DIR
    repo = "OpenVINO/claim-test-ov"
    assert modelsvc.claim_hf_download(repo) == ""
    assert modelsvc.claim_hf_download(repo) == "active"  # slot is reserved
    modelsvc.release_hf_download(repo)
    assert modelsvc.claim_hf_download(repo) == ""
    modelsvc.release_hf_download(repo)
    d = MODELS_DIR / "claim-test-ov"
    d.mkdir(parents=True, exist_ok=True)
    (d / ".ovmsui.json").write_text(
        '{"source": "huggingface", "origin": "OpenVINO/claim-test-ov@main"}', encoding="utf-8")
    assert modelsvc.claim_hf_download(repo) == "done"
    reset_config()


def test_duplicate_download_is_rejected(monkeypatch):
    reset_config()
    import threading

    from app import models as modelsvc

    gate = threading.Event()

    def fake_worker(tid, repo, *_args, **_kwargs):
        try:
            gate.wait(5)
        finally:
            modelsvc.release_hf_download(repo)

    monkeypatch.setattr(modelsvc, "download_hf_worker", fake_worker)
    try:
        body = {"repo_id": "OpenVINO/dupe-test-ov"}
        assert client.post("/api/models/download_hf", json=body).status_code == 200
        r = client.post("/api/models/download_hf", json=body,
                        headers={"Accept-Language": "ja"})
        assert r.status_code == 409 and "ダウンロード中" in r.json()["detail"]
    finally:
        gate.set()
        reset_config()


def test_load_options_reports_quantization():
    reset_config()
    from app.config import MODELS_DIR
    model = MODELS_DIR / "Qwen3-8B-int4-ov"
    model.mkdir(parents=True, exist_ok=True)
    r = client.get("/api/model/load_options?model=Qwen3-8B-int4-ov")
    assert r.json()["quant"] == "int4" and r.json()["cw"] is False
    reset_config()


def test_tokenizer_target_dir(tmp_path):
    from app.models import tokenizer_target_dir
    plain = tmp_path / "plain"
    plain.mkdir()
    assert tokenizer_target_dir(plain) == plain
    nested = tmp_path / "nested"
    (nested / "tokenizer").mkdir(parents=True)
    assert tokenizer_target_dir(nested) == nested / "tokenizer"


def test_convert_tokenizer_endpoint(monkeypatch):
    reset_config()
    from app import models as modelsvc
    from app.config import MODELS_DIR
    model = MODELS_DIR / "imgmodel2"
    model.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(modelsvc, "convert_tokenizer_worker", lambda tid, name: None)
    client.post("/api/config", json={"selected_runtime": "r1"})
    r = client.post("/api/models/imgmodel2/convert_tokenizer")
    assert r.status_code == 200
    assert any(t["kind"] == "tokenizer" for t in client.get("/api/tasks").json())
    assert client.post("/api/models/nope/convert_tokenizer").status_code == 404
    reset_config()


def test_port_busy_detection():
    import socket

    from app.ovms import _port_busy
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    assert _port_busy(port) is True
    server.close()
    assert _port_busy(port) is False


def test_cleanup_orphans_non_windows():
    from app import ovms
    if os.name != "nt":
        assert ovms.cleanup_orphans() == []


def test_bind_to_job_does_not_raise():
    from app import procutil
    if os.name == "nt":
        import subprocess as sp
        child = sp.Popen(["cmd", "/c", "exit", "0"], creationflags=sp.CREATE_NO_WINDOW)
        assert procutil.bind_to_job(child) in (True, False)
        child.wait()
    else:
        assert procutil.bind_to_job(None) is False


def test_ov_ir_detection():
    from app.models import is_ov_ir
    assert is_ov_ir(["openvino_model.xml", "openvino_model.bin", "config.json"])
    assert is_ov_ir(["sub/model.xml", "sub/model.bin"])
    assert not is_ov_ir(["model.onnx", "config.json"])
    assert not is_ov_ir(["openvino_model.xml", "config.json"])
    assert not is_ov_ir([])
    # stems must match, and tokenizer IR alone is not a model
    assert not is_ov_ir(["openvino_model.xml", "weights.bin"])
    assert not is_ov_ir(["sub/a.xml", "other/a.bin"])
    assert not is_ov_ir(["openvino_tokenizer.xml", "openvino_tokenizer.bin"])


def test_quant_info_detection():
    from app.models import quant_info
    assert quant_info("OpenVINO/Qwen3-8B-int4-cw-ov") == {"precision": "int4", "cw": True}
    assert quant_info("OpenVINO/Qwen3-8B-int4-ov") == {"precision": "int4", "cw": False}
    assert quant_info("OpenVINO/Llama-3.2-1B-int8-ov") == {"precision": "int8", "cw": False}
    assert quant_info("org/model", ["openvino", "4-bit", "channel-wise"]) == \
        {"precision": "int4", "cw": True}
    assert quant_info("org/model", ["nf4"]) == {"precision": "nf4", "cw": False}
    # word boundaries: "print8" / "kcw" must not match
    assert quant_info("org/model") == {"precision": "", "cw": False}
    assert quant_info("org/kcw-model")["cw"] is False


def test_search_endpoint(monkeypatch):
    reset_config()
    from app import models as modelsvc

    captured = {}

    def fake_search(query, limit=30, sort="downloads", token=None, cursor=None):
        captured.update(query=query, limit=limit, sort=sort, cursor=cursor)
        results = [{"repo_id": "OpenVINO/test-ov", "downloads": 1, "likes": 0,
                    "last_modified": "2026-01-01T00:00:00.000Z", "gated": False,
                    "pipeline_tag": "text-generation", "library_name": "openvino", "files": 3}]
        return results, "CURSOR2"

    monkeypatch.setattr(modelsvc, "search_hf_ir", fake_search)
    r = client.get("/api/models/search?q=qwen&sort=likes&limit=5")
    assert r.status_code == 200
    assert r.json()["results"][0]["repo_id"] == "OpenVINO/test-ov"
    assert r.json()["next"] == "CURSOR2"
    assert captured == {"query": "qwen", "limit": 5, "sort": "likes", "cursor": None}

    r = client.get("/api/models/search?q=qwen&cursor=CURSOR2")
    assert r.status_code == 200 and captured["cursor"] == "CURSOR2"

    r = client.get("/api/models/search")
    assert r.status_code == 400

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(modelsvc, "search_hf_ir", boom)
    r = client.get("/api/models/search?q=x", headers={"Accept-Language": "ja"})
    assert r.status_code == 502 and "モデル検索に失敗" in r.json()["detail"]


def test_search_exact_repo_lookup(monkeypatch):
    reset_config()
    from app import models as modelsvc
    monkeypatch.setattr(modelsvc, "search_hf_ir", lambda *a, **k: ([], None))
    monkeypatch.setattr(modelsvc, "repo_ir_info", lambda repo_id, token=None: {
        "repo_id": repo_id, "downloads": 0, "likes": 0, "last_modified": "",
        "gated": False, "pipeline_tag": "", "library_name": "", "files": 24})
    r = client.get("/api/models/search?q=OpenVINO/stable-diffusion-v1-5-int8-ov")
    assert r.status_code == 200
    assert r.json()["results"][0]["repo_id"] == "OpenVINO/stable-diffusion-v1-5-int8-ov"
    reset_config()


def test_search_cursor_parsing():
    from app.models import next_cursor_from_link
    header = ('<https://huggingface.co/api/models?search=q&limit=5&cursor=abc123>; rel="next"')
    assert next_cursor_from_link(header) == "abc123"
    assert next_cursor_from_link(None) is None
    assert next_cursor_from_link('<https://example.com/x>; rel="prev"') is None


def test_token_score_word_matching():
    from app.models import _token_score
    assert _token_score("qwen3", {"qwen3", "8b"}, "qwen38b") == 2
    assert _token_score("qwen", {"qwen3", "8b"}, "qwen38b") == 1   # prefix
    assert _token_score("3", {"llama", "3layers"}, "llama3layers") == 0  # not inside a word
    assert _token_score("llama3", {"llama", "3"}, "llama3") == 1   # compact form


def test_rank_prefers_relevant_official_repos():
    from app.models import _rank_ir_entries

    def entry(repo, downloads):
        return {"repo_id": repo, "downloads": downloads, "likes": 0, "last_modified": ""}

    entries = [
        entry("yujiepan/llama-2-tiny-3layers-random", 1717),
        entry("blaj/Llama-3.1-8B-Lexi-Uncensored-V2-fp16-ov", 475),
        entry("OpenVINO/Llama-3.1-8B-Instruct-FastDraft-150M-int8-ov", 162),
    ]
    ranked = [e["repo_id"] for e in _rank_ir_entries(entries, "llama 3", "downloads")]
    assert ranked[0] == "OpenVINO/Llama-3.1-8B-Instruct-FastDraft-150M-int8-ov"
    assert ranked[-1] == "yujiepan/llama-2-tiny-3layers-random"


def test_search_hf_ir_uses_openvino_tag_and_ranks(monkeypatch):
    from app import models as modelsvc

    calls = []

    def fake_page(params, token):
        calls.append(dict(params))
        if params.get("filter") == "openvino":
            return ([{"id": "someone/my-qwen3-8b-int4-ov", "downloads": 10, "likes": 1,
                      "lastModified": "2026-01-01T00:00:00.000Z", "tags": ["openvino"],
                      "siblings": [{"rfilename": "openvino_model.xml"},
                                   {"rfilename": "openvino_model.bin"}]}], "CUR2")
        if params.get("author") == "OpenVINO":
            return ([{"id": "OpenVINO/Qwen3-8B-int4-ov", "downloads": 5, "likes": 2,
                      "lastModified": "2026-01-02T00:00:00.000Z", "tags": ["openvino"],
                      "siblings": [{"rfilename": "openvino_model.xml"},
                                   {"rfilename": "openvino_model.bin"}]}], None)
        return ([], None)  # plain fallback

    monkeypatch.setattr(modelsvc, "_hf_page", fake_page)
    results, nxt = modelsvc.search_hf_ir("qwen3 8b int4", limit=20)
    assert nxt == "CUR2"
    # official first (same query coverage), then the community repo
    assert [r["repo_id"] for r in results] == ["OpenVINO/Qwen3-8B-int4-ov",
                                               "someone/my-qwen3-8b-int4-ov"]
    assert any(p.get("filter") == "openvino" for p in calls)
    assert any(p.get("author") == "OpenVINO" for p in calls)


def test_search_hf_ir_cursor_skips_supplements(monkeypatch):
    from app import models as modelsvc

    calls = []

    def fake_page(params, token):
        calls.append(dict(params))
        return ([], "NEXT")

    monkeypatch.setattr(modelsvc, "_hf_page", fake_page)
    results, nxt = modelsvc.search_hf_ir("qwen3", limit=5, cursor="CUR1")
    assert results == [] and nxt == "NEXT"
    assert len(calls) == 1  # no official / plain supplement while paging
    assert calls[0].get("filter") == "openvino"
    assert calls[0].get("cursor") == "CUR1"


def test_task_cancel():
    from app import tasks
    tid = tasks.create("model", "test task", "en")
    assert tasks.is_running(tid)
    assert tasks.cancel(tid) is True
    assert not tasks.is_running(tid)
    assert tasks.cancel(tid) is False
    tasks.finish(tid)  # must not overwrite the cancelled state
    task = next(x for x in tasks.list_all() if x["id"] == tid)
    assert task["status"] == "cancelled"
    assert task["message"] == "Cancelled"


def test_task_cancel_endpoint():
    from app import tasks
    tid = tasks.create("ovms", "install task", "ja")
    r = client.post(f"/api/tasks/{tid}/cancel")
    assert r.status_code == 200 and r.json()["cancelled"] is True
    assert client.post("/api/tasks/does-not-exist/cancel").json()["cancelled"] is False


def test_safe_zip_extraction(tmp_path):
    from app.fsutil import extract_zip_safe
    archive_path = tmp_path / "a.zip"
    with zipfile.ZipFile(archive_path, "w") as z:
        z.writestr("ok.txt", "hi")
        z.writestr("../evil.txt", "no")
    with zipfile.ZipFile(archive_path) as z, pytest.raises(RuntimeError):
        extract_zip_safe(z, tmp_path / "out", lang="en")


def test_tar_filter_rewrites_absolute_symlink(tmp_path):
    import tarfile

    from app.fsutil import tar_safe_filter
    member = tarfile.TarInfo(
        "ovms/lib/python/openvino_tokenizers/lib/libopenvino_tokenizers.so")
    member.type = tarfile.SYMTYPE
    member.linkname = "/ovms/lib/libopenvino_tokenizers.so"
    tar_safe_filter(member, str(tmp_path))
    assert member.linkname == "../../../libopenvino_tokenizers.so"


def test_tar_filter_rejects_escaping_symlink(tmp_path):
    import tarfile

    from app.fsutil import tar_safe_filter
    member = tarfile.TarInfo("pkg/evil")
    member.type = tarfile.SYMTYPE
    member.linkname = "/../../etc/passwd"
    with pytest.raises(tarfile.LinkOutsideDestinationError):
        tar_safe_filter(member, str(tmp_path))


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_tar_absolute_symlink_extracts_relative(tmp_path):
    import io
    import tarfile

    from app.fsutil import tar_safe_filter
    archive_path = tmp_path / "ovms.tar.gz"
    with tarfile.open(archive_path, "w:gz") as t:
        data = b"tokenizers"
        info = tarfile.TarInfo("ovms/lib/libopenvino_tokenizers.so")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(
            "ovms/lib/python/openvino_tokenizers/lib/libopenvino_tokenizers.so")
        link.type = tarfile.SYMTYPE
        link.linkname = "/ovms/lib/libopenvino_tokenizers.so"
        t.addfile(link)

    dest = tmp_path / "out"
    dest.mkdir()
    with tarfile.open(archive_path) as t:
        t.extractall(dest, filter=tar_safe_filter)

    extracted = dest / "ovms/lib/python/openvino_tokenizers/lib/libopenvino_tokenizers.so"
    assert extracted.is_symlink()
    assert os.readlink(extracted) == "../../../libopenvino_tokenizers.so"
    assert extracted.resolve() == (dest / "ovms/lib/libopenvino_tokenizers.so").resolve()


def test_version_comparison():
    from app.updater import is_newer, parse_version
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.0") == (1, 0)
    assert parse_version("nonsense") == ()
    assert is_newer("1.0.4", "1.0.3")
    assert is_newer("1.1", "1.0.9")
    assert is_newer("2.0.0", "1.9.9")
    assert not is_newer("1.0.3", "1.0.3")
    assert not is_newer("0.9", "1.0")


def test_update_checksum_parsing():
    from app.updater import checksum_for
    digest = "a" * 64
    text = f"{digest}  LocArc-windows-x64.zip\n{'b' * 64}  other.zip\n"
    assert checksum_for(text, "LocArc-windows-x64.zip") == digest
    assert checksum_for(text, "missing.zip") is None
    assert checksum_for("garbage", "x") is None


def test_update_url_allowlist(monkeypatch):
    from app import updater
    # An existing config may still point at the pre-rename repository.
    monkeypatch.setattr(updater, "repo", lambda: "Asahi-Prv/i-AI-Studio")
    assert updater.is_allowed_url(
        "https://github.com/Asahi-Prv/locarc/releases/download/v2.0.0/LocArc-windows-x64.zip")
    assert updater.is_allowed_url(
        "https://github.com/Asahi-Prv/i-AI-Studio/releases/download/v1.14.2/Intel-AI-Studio-windows-x64.zip")
    assert not updater.is_allowed_url("https://evil.example.com/x.zip")
    assert not updater.is_allowed_url("")


def test_update_repo_migrates_legacy_config(monkeypatch):
    from app import updater
    # config.json written before the rename contains the old repository name.
    monkeypatch.setattr(updater, "load_config",
                        lambda: {"update_repo": "Asahi-Prv/i-AI-Studio"})
    assert updater.repo() == "Asahi-Prv/locarc"
    # Other custom repositories are left alone.
    monkeypatch.setattr(updater, "load_config",
                        lambda: {"update_repo": "someone/fork"})
    assert updater.repo() == "someone/fork"
    monkeypatch.setattr(updater, "load_config", lambda: {})
    assert updater.repo() == "Asahi-Prv/locarc"


def test_update_check_endpoint(monkeypatch):
    from app import updater
    payload = {"current": "1.0.3", "latest": "1.1.0", "tag": "v1.1.0", "available": True,
               "html_url": "https://github.com/Asahi-Prv/locarc/releases/tag/v1.1.0",
               "asset_url": "", "checksums_url": ""}
    monkeypatch.setattr(updater, "check_for_update", lambda force=False, lang=None: dict(payload))
    r = client.get("/api/update/check")
    assert r.status_code == 200
    assert r.json()["latest"] == "1.1.0" and r.json()["available"] is True
    assert r.json()["frozen"] is False  # tests run unfrozen

    def boom(*_a, **_k):
        raise RuntimeError("offline")

    monkeypatch.setattr(updater, "check_for_update", boom)
    r = client.get("/api/update/check", headers={"Accept-Language": "ja"})
    assert r.status_code == 502 and "更新の確認に失敗" in r.json()["detail"]


def test_update_run_requires_frozen():
    r = client.post("/api/update/run", json={"tag": "v1.1.0"})
    assert r.status_code == 400


def test_apply_update_requires_frozen(tmp_path):
    from app import updater
    with pytest.raises(RuntimeError):
        updater.apply_update(tmp_path)


def test_config_cache_invalidates_on_change():
    reset_config()
    assert load_config() == load_config()          # cached
    save_config({"ui_port": 8999})
    assert load_config()["ui_port"] == 8999
    reset_config()                                  # deletion must be noticed
    assert load_config()["ui_port"] == 8810


def test_normalize_devices():
    from app.ovms import normalize_devices
    assert normalize_devices(["GPU.0", "GPU.1", "CPU", "NPU", "cpu"]) == ["CPU", "GPU", "NPU"]
    assert normalize_devices([]) == []


def test_devices_from_library_missing(tmp_path):
    from app.ovms import _devices_from_library
    assert _devices_from_library(tmp_path) == []


def test_load_options_uses_cached_devices(monkeypatch):
    reset_config()
    from app import ovms
    monkeypatch.setattr(ovms, "cached_devices", lambda runtime_id: ["CPU", "NPU"])
    client.post("/api/config", json={"selected_runtime": "some-runtime"})
    r = client.get("/api/model/load_options?model=anything")
    assert r.status_code == 200 and r.json()["devices"] == ["CPU", "NPU"]
    reset_config()


def test_devices_endpoint(monkeypatch):
    reset_config()
    from app import ovms
    client.post("/api/config", json={"selected_runtime": "some-runtime"})
    monkeypatch.setattr(ovms, "probe_devices",
                        lambda runtime_id, lang=None, refresh=False: ["CPU", "NPU"])
    r = client.get("/api/ovms/devices")
    assert r.status_code == 200 and r.json()["devices"] == ["CPU", "NPU"]
    monkeypatch.setattr(ovms, "probe_devices",
                        lambda runtime_id, lang=None, refresh=False: None)
    assert client.get("/api/ovms/devices").json()["devices"] is None
    # ?refresh=1 must be forwarded (re-detect after a driver install)
    monkeypatch.setattr(ovms, "probe_devices",
                        lambda runtime_id, lang=None, refresh=False:
                        ["CPU", "GPU", "NPU"] if refresh else ["CPU", "GPU"])
    assert client.get("/api/ovms/devices").json()["devices"] == ["CPU", "GPU"]
    assert client.get("/api/ovms/devices?refresh=1").json()["devices"] == ["CPU", "GPU", "NPU"]
    reset_config()


def test_probe_devices_refresh_bypasses_cache(monkeypatch):
    from app import ovms
    from app.config import RUNTIMES_DIR
    runtime = RUNTIMES_DIR / "rt-refresh-test"
    (runtime / "ovms").mkdir(parents=True, exist_ok=True)
    exe = runtime / "ovms" / ("ovms.exe" if os.name == "nt" else "ovms")
    exe.write_text("", encoding="utf-8")
    (runtime / "runtime.json").write_text('{"devices": ["CPU", "GPU"]}', encoding="utf-8")

    calls = {"n": 0}

    def fake_library(_dir):
        calls["n"] += 1
        return ["CPU", "GPU", "NPU"]

    monkeypatch.setattr(ovms, "_devices_from_library", fake_library)
    assert ovms.probe_devices("rt-refresh-test") == ["CPU", "GPU"]  # cached
    assert calls["n"] == 0
    assert ovms.probe_devices("rt-refresh-test", refresh=True) == ["CPU", "GPU", "NPU"]
    assert calls["n"] == 1
    assert ovms.probe_devices("rt-refresh-test") == ["CPU", "GPU", "NPU"]  # cache rewritten


def test_update_script_is_pid_reuse_safe(tmp_path):
    from app.updater import write_update_script
    script = tmp_path / "apply.ps1"
    write_update_script(tmp_path / "staged", tmp_path / "app", "LocArc.exe",
                        tmp_path / "updates" / "v1", script)
    text = script.read_text(encoding="utf-8")
    assert "[System.IO.File]::Open" in text  # waits for the exe lock, not a PID
    assert "Get-Process -Id" not in text
    assert "robocopy" in text and "Start-Process" in text


def test_update_asset_names_by_platform():
    from app import updater
    if os.name == "nt":
        assert updater.asset_name() == "LocArc-windows-x64.zip"
        assert updater.exe_name() == "LocArc.exe"
        assert updater.legacy_asset_name() == "Intel-AI-Studio-windows-x64.zip"
        assert updater.legacy_exe_name() == "Intel-AI-Studio.exe"
    else:
        assert updater.asset_name() == "LocArc-linux-x64.tar.gz"
        assert updater.exe_name() == "LocArc"
        assert updater.legacy_asset_name() == "Intel-AI-Studio-linux-x64.tar.gz"
        assert updater.legacy_exe_name() == "Intel-AI-Studio"


def test_update_staging_accepts_legacy_layout(tmp_path):
    from app import updater
    legacy = tmp_path / "Intel-AI-Studio"
    legacy.mkdir()
    (legacy / updater.legacy_exe_name()).write_bytes(b"")
    assert updater.find_staged_app(tmp_path) == legacy
    assert updater.find_staged_exe(legacy).name == updater.legacy_exe_name()

    current = tmp_path / "LocArc"
    current.mkdir()
    (current / updater.exe_name()).write_bytes(b"")
    assert updater.find_staged_app(tmp_path) == current
    assert updater.find_staged_exe(current).name == updater.exe_name()


def test_update_script_posix(tmp_path):
    import stat

    from app.updater import write_update_script_posix
    script = tmp_path / "apply.sh"
    write_update_script_posix(tmp_path / "staged", tmp_path / "app", "LocArc",
                              tmp_path / "updates" / "v1", script, 4321)
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    assert "kill -0" in text          # waits for the running app to exit
    assert "cp -a" in text and "setsid" in text
    if os.name != "nt":
        assert script.stat().st_mode & stat.S_IXUSR  # executable


def test_free_ram_detection_is_positive():
    from app.main import _free_ram_gb
    assert _free_ram_gb() > 0



def test_subprocess_flags_hide_console():
    from app import procutil
    if os.name == "nt":
        import subprocess as sp
        flags = procutil.subprocess_flags()
        assert flags & sp.CREATE_NO_WINDOW
        assert flags & sp.CREATE_NEW_PROCESS_GROUP
    else:
        assert procutil.subprocess_flags() == 0


def test_static_js_syntax():
    quickjs = pytest.importorskip("quickjs")
    ctx = quickjs.Context()
    for name in ("app.js", "i18n.js", "markdown.js"):
        source = (ROOT / "app" / "static" / name).read_text(encoding="utf-8")
        ctx.eval("(function(){\n" + source + "\n})")  # compiles only; never executes


def test_markdown_renderer():
    quickjs = pytest.importorskip("quickjs")
    ctx = quickjs.Context()
    ctx.eval((ROOT / "app" / "static" / "markdown.js").read_text(encoding="utf-8"))
    assert "<strong>bold</strong>" in ctx.eval("renderMarkdown('**bold** and `code`')")
    assert "<code>code</code>" in ctx.eval("renderMarkdown('**bold** and `code`')")
    escaped = ctx.eval("renderMarkdown('<img src=x onerror=alert(1)>')")
    assert "&lt;img" in escaped and "<img" not in escaped
    table = ctx.eval("renderMarkdown('| a | b |\\n|---|---|\\n| 1 | 2 |')")
    assert "<table>" in table and "<td>1</td>" in table
    assert "<pre><code" in ctx.eval("renderMarkdown('```python\\nprint(1)\\n```')")


def test_release_notes_parsing():
    from scripts.release_notes import parse_subject
    assert parse_subject("feat: add model search") == ("feat", "add model search")
    assert parse_subject("fix(ui): align button") == ("fix", "**ui**: align button")
    assert parse_subject("chore!: drop old layout") == ("chore", "drop old layout")
    assert parse_subject("plain commit message") is None


def test_runtime_env_embeddable_layout(tmp_path):
    from app.ovms import _runtime_env
    pkg = tmp_path / "ovms"
    pydir = pkg / "python"
    pydir.mkdir(parents=True)
    (pydir / "python312._pth").write_text(
        "python312\r\n.\r\nScripts\r\nLib\\site-packages\r\nimport site\r\n", encoding="utf-8")
    (pkg / "ovms.exe").write_text("")
    env = _runtime_env(pkg / "ovms.exe")
    assert env["PYTHONHOME"] == str(pydir)
    entries = env["PYTHONPATH"].split(os.pathsep)
    assert entries[0] == str(pydir / "python312")
    assert str(pydir) in entries
    assert str(pydir / "Lib" / "site-packages") in entries


def test_runtime_env_classic_layout(tmp_path):
    from app.ovms import _runtime_env
    pkg = tmp_path / "ovms"
    (pkg / "python" / "Lib").mkdir(parents=True)
    (pkg / "ovms.exe").write_text("")
    env = _runtime_env(pkg / "ovms.exe")
    assert env["PYTHONHOME"] == str(pkg / "python")
    assert "PYTHONPATH" not in env


def test_i18n_fallback():
    assert i18n.tr("xx", "err.not_found") == "Not found"
    assert i18n.tr("ja", "err.not_found") == "見つかりません"
    assert i18n.tr("ja", "err.bad_port", key="ui_port") == "ui_port は 1〜65535 の整数で指定してください"


def test_removed_webui_endpoints_are_gone():
    reset_config()
    for path in ("/api/login", "/api/logout", "/api/auth/state", "/api/shutdown"):
        assert client.get(path).status_code == 404, path
