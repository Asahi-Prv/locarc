"""Runtime listing: old ``python_on`` and new unified OVMS asset names.

Since the 2026.5.0.eec7daac4 weekly build (October 2026) upstream publishes one unified
package per platform (Python is optional and detected at runtime), so the file names no
longer contain the version or the ``_python_on`` suffix. The listing code must accept
both layouts, or new weeklies silently stop appearing in the app.
"""

from app import ovms


def _file(name: str, size: int = 1, modified: str = "2026-10-26 22:19") -> dict:
    return {"name": name, "type": "file", "size": size, "last modified": modified}


def _dir(name: str, *files: str) -> dict:
    return {"name": name, "type": "directory", "children": [_file(f) for f in files]}


def _filetree(*weekly_dirs: dict) -> dict:
    return {
        "name": "root",
        "type": "directory",
        "children": [
            {"name": "repositories", "type": "directory", "children": [
                {"name": "openvino_model_server", "type": "directory", "children": [
                    {"name": "packages", "type": "directory", "children": [
                        {"name": "weekly", "type": "directory", "children": list(weekly_dirs)},
                    ]},
                ]},
            ]},
        ],
    }


def _patch_httpx(monkeypatch, payload, urls: list[str]) -> None:
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

        @property
        def text(self):
            return payload

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kw):
            urls.append(url)
            return Resp()

    monkeypatch.setattr(ovms.httpx, "Client", Client)


def test_weekly_listing_supports_old_and_unified_names(monkeypatch):
    monkeypatch.setattr(ovms, "IS_WINDOWS", True)
    tree = _filetree(
        _dir("2026.5.0.6ec5e369", "changelog.txt",
             "ovms_windows_2026.5.0_python_on.zip", "ovms_windows_2026.5.0_python_on.zip.sha256",
             "ovms_ubuntu24_2026.5.0_python_on.tar.gz"),
        _dir("2026.5.0.3b33556ed", "changelog.txt", "version.txt",
             "ovms_windows.zip", "ovms_windows.sha256",
             "ovms_ubuntu24.tar.gz", "ovms_ubuntu24.tar.gz.sha256",
             "ovms_ubuntu26.tar.gz"),
    )
    monkeypatch.setattr(ovms, "_filetree", lambda: tree)
    entries = {e["label"]: e for e in ovms.list_versions("weekly")}

    old = entries["2026.5.0.6ec5e369"]
    assert old["version"] == "2026.5.0"
    assert old["url"].endswith("/weekly/2026.5.0.6ec5e369/ovms_windows_2026.5.0_python_on.zip")
    assert old["sha256_url"].endswith("/ovms_windows_2026.5.0_python_on.zip.sha256")

    new = entries["2026.5.0.3b33556ed"]
    assert new["version"] == "2026.5.0"
    assert new["url"].endswith("/weekly/2026.5.0.3b33556ed/ovms_windows.zip")
    assert new["sha256_url"].endswith("/weekly/2026.5.0.3b33556ed/ovms_windows.sha256")

    # only the host platform shows up (no ubuntu24/ubuntu26 entries on Windows)
    assert all(e["url"].endswith(".zip") for e in entries.values())


def test_weekly_latest_unified_uses_version_txt(monkeypatch):
    monkeypatch.setattr(ovms, "IS_WINDOWS", False)
    tree = _filetree(_dir("latest", "version.txt", "ovms_ubuntu24.tar.gz",
                          "ovms_ubuntu24.tar.gz.sha256", "ovms_windows.zip"))
    monkeypatch.setattr(ovms, "_filetree", lambda: tree)
    monkeypatch.setattr(ovms, "_latest_version", lambda: "2026.5.0")
    entries = ovms.list_versions("weekly")
    assert len(entries) == 1
    e = entries[0]
    assert e["label"] == "latest -> 2026.5.0"
    assert e["version"] == "2026.5.0"
    assert e["url"].endswith("/weekly/latest/ovms_ubuntu24.tar.gz")
    assert e["sha256_url"].endswith("/weekly/latest/ovms_ubuntu24.tar.gz.sha256")


def test_latest_version_reads_version_txt(monkeypatch):
    urls: list[str] = []
    text = ("OpenVINO Model Server 2026.5.0.3b33556ed\r\n"
            "OpenVINO backend 2026.5.0-23594-7e507a4ca9a\r\n")
    _patch_httpx(monkeypatch, text, urls)
    monkeypatch.setitem(ovms._latest_version_cache, "t", 0.0)
    monkeypatch.setitem(ovms._latest_version_cache, "value", None)
    assert ovms._latest_version() == "2026.5.0"
    assert urls and urls[-1].endswith("/weekly/latest/version.txt")


def test_stable_listing_keeps_python_on_names(monkeypatch):
    monkeypatch.setattr(ovms, "IS_WINDOWS", True)
    base = "https://github.com/openvinotoolkit/model_server/releases/download/v2026.4.1/"
    rel = {
        "tag_name": "v2026.4.1",
        "draft": False,
        "published_at": "2026-10-06T21:12:46Z",
        "assets": [
            {"name": "ovms_windows_2026.4.1_python_on.zip", "size": 10,
             "browser_download_url": base + "ovms_windows_2026.4.1_python_on.zip"},
            {"name": "ovms_windows_2026.4.1_python_on.zip.sha256", "size": 1,
             "browser_download_url": base + "ovms_windows_2026.4.1_python_on.zip.sha256"},
            {"name": "ovms_windows_2026.4.1_python_off.zip", "size": 10,
             "browser_download_url": base + "ovms_windows_2026.4.1_python_off.zip"},
        ],
    }
    _patch_httpx(monkeypatch, [rel], [])
    entries = ovms.list_versions("stable")
    assert len(entries) == 1  # python_off is skipped
    assert entries[0]["sha256_url"] == base + "ovms_windows_2026.4.1_python_on.zip.sha256"


def test_stable_listing_accepts_unified_assets(monkeypatch):
    monkeypatch.setattr(ovms, "IS_WINDOWS", True)
    base = "https://github.com/openvinotoolkit/model_server/releases/download/v2026.5.0/"
    rel = {
        "tag_name": "v2026.5.0",
        "draft": False,
        "published_at": "2026-10-27T00:00:00Z",
        "assets": [
            {"name": "ovms_windows.zip", "size": 10, "browser_download_url": base + "ovms_windows.zip"},
            {"name": "ovms_windows.sha256", "size": 1, "browser_download_url": base + "ovms_windows.sha256"},
            {"name": "ovms_ubuntu24.tar.gz", "size": 10, "browser_download_url": base + "ovms_ubuntu24.tar.gz"},
        ],
    }
    _patch_httpx(monkeypatch, [rel], [])
    entries = ovms.list_versions("stable")
    assert len(entries) == 1
    e = entries[0]
    assert e["version"] == "2026.5.0"
    assert e["label"] == "v2026.5.0 (2026.5.0)"
    assert e["sha256_url"] == base + "ovms_windows.sha256"
