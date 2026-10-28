# LocArc

[![CI](https://github.com/Asahi-Prv/locarc/actions/workflows/ci.yml/badge.svg)](https://github.com/Asahi-Prv/locarc/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows | Linux](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)](#requirements)

> [!IMPORTANT]
> This is an independent, community-built project. It is **not affiliated with, endorsed by, or
> sponsored by Intel Corporation**. "Intel" and "OpenVINO" are trademarks of Intel Corporation,
> used here only to describe compatibility. This is not an official Intel product.

**LocArc** is a local-first desktop studio for
[OpenVINO Model Server (OVMS)](https://github.com/openvinotoolkit/model_server).
It manages the whole lifecycle in a native WebView2 window:

> [!NOTE]
> **LocArc** was previously called **Intel AI Studio**. Existing `data` folders keep working;
> see [Upgrading from Intel AI Studio](#upgrading-from-intel-ai-studio).

- **Install OVMS runtimes** – stable (GitHub releases) or weekly builds, `python_on` packages only,
  with SHA-256 verification when available.
- **Download models** – from Hugging Face (public or gated with a token) or any direct URL
  (zip/tar auto-extract); downloads can be cancelled from the task panel.
- **Search models** – search Hugging Face for **OpenVINO IR** models only. The `openvino` tag and
  the official `OpenVINO` org are searched first (a plain text search is dominated by the much
  more popular PyTorch repos), hits are verified by a matching `.xml` + `.bin` pair, and results
  are ranked by query relevance, official origin, then popularity. Paging uses infinite scrolling,
  and downloads can skip non-IR weights (PyTorch/ONNX/...) to save disk space. Quantization is
  detected from the repo name/tags: CW (channel-wise) builds are badged, and the load dialog shows
  an NPU tip (or a warning for non-CW models) when NPU is selected.
- **Load / unload models** – device selection (CPU/GPU/NPU/AUTO), serve-mode auto-detection,
  and LLM load options such as KV-cache size, KV precision (u8), context length, and prefix caching.
- **Chat** – streaming chat with Markdown rendering, thinking-content support, auto-generated
  titles, per-chat generation parameters, and persisted chat history.
- **Generate images** – for `image_generation` models.
- **Serve an API** – OVMS itself exposes OpenAI-compatible REST and gRPC endpoints; the UI can
  manage an optional Bearer API key for external clients.
- **Self-update** – packaged builds check GitHub Releases at startup (at most once a day) and can
  update themselves in one click: download, SHA-256 verification, automatic replacement and
  restart, keeping your models and chats.
- **Bilingual UI** – English / Japanese, switchable at runtime.

## Install

Every [release](https://github.com/Asahi-Prv/locarc/releases) publishes Windows and Linux
builds. Each bundles its own Python runtime and stores data (runtimes, models, chats, settings) in a
`data` folder next to the executable.

### Windows

| Build | Download | How it runs |
| --- | --- | --- |
| **Installer** (recommended) | `LocArc-Setup-x64.exe` | Installs per-user (no admin rights), adds Start Menu and optional desktop shortcuts, and opens the UI in a native desktop window (WebView2). |
| **Portable** | `LocArc-windows-x64.zip` | Extract it anywhere and run `LocArc.exe`; the app opens in a native desktop window (no installation required). |

Both builds use the same executable; the installer just adds shortcuts and an uninstaller. Windows
may show a SmartScreen warning because the binaries are unsigned (*More info → Run anyway*).

### Linux (Ubuntu 24.04)

Download `LocArc-linux-x64.tar.gz`. It is a portable folder that also ships a per-user
installer:

```bash
tar -xzf LocArc-linux-x64.tar.gz
cd LocArc
./install.sh          # launcher + application-menu entry, no root required
./LocArc          # or run it directly without installing
```

`install.sh` copies the app into `~/.local/share/locarc`, adds a `locarc`
command in `~/.local/bin`, and registers a `.desktop` entry. `./uninstall.sh` removes the app but
keeps your `data`; add `--purge` to delete the data too.

The Linux build targets the same Ubuntu 24.04 platform as the OVMS `python_on` packages. For a
native window install WebKitGTK with:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1
```

`install.sh` checks for it and prints this command when it is missing. Without WebKitGTK the app
opens in your default browser instead, and everything keeps working.

## Requirements

- Windows 10/11 (x64) or Ubuntu 24.04 — matching OVMS `python_on` packages.
- Microsoft Edge WebView2 Runtime (bundled with Windows 11 and most Windows 10 systems).
- On Linux, WebKitGTK (`python3-gi`, `gir1.2-webkit2-4.1`) for the native window (optional; falls back to the browser).
- Python 3.12+ when running from source. The packaged executable bundles Python.
- Disk space: ~1–2 GB per OVMS runtime plus the size of your models.

## Quick start (source)

Windows:

```bat
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
run.bat
```

Linux:

```bash
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
./run.sh
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

A desktop window opens automatically (the local server listens on `http://127.0.0.1:8810`).

## First steps

1. **Install a runtime** — the *Getting started* card offers "Install the latest Stable".
   Alternatively open **Settings → OpenVINO Model Server runtime**, pick Stable or Weekly,
   fetch the version list, and install a build.
2. **Download a model** — open the **Models** tab and enter a Hugging Face repo id, for example
   `OpenVINO/Qwen3-8B-int4-ov`, or use a direct URL.
3. **Load it** — choose a device and (if needed) a serve mode in the load dialog, then press
   *Load*. The UI waits until OVMS reports the model as `AVAILABLE`.
4. **Chat** — once loaded, type a message. The right sidebar holds per-chat generation parameters
   (temperature, top-p/k, max tokens, system prompt, thinking control).

## Build a standalone executable

Windows:

```bat
build.bat
```

The result is `dist\LocArc\LocArc.exe`, a portable folder with the bundled
Python runtime. Verify it before shipping:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
```

Linux:

```bash
./build.sh
```

The result is `dist/LocArc/LocArc` (plus `install.sh`/`uninstall.sh`), a portable
folder with the bundled Python runtime. Verify it with:

```bash
scripts/smoke-test.sh dist/LocArc/LocArc
```

The app keeps its data in a `data` folder next to the executable. To distribute, package the whole
`dist/LocArc` folder — on Windows as a zip (users extract it and run the exe; SmartScreen
may warn because it is unsigned), on Linux as a `tar.gz` (users extract it and run `./install.sh`
or the executable directly).

Build configuration lives in `locarc.spec` (datas, windowed mode, no UPX). CI builds the
same spec for Windows and Linux on tags matching `v*`, smoke-tests each executable, and attaches
all artifacts to the GitHub release (see `.github/workflows/build.yml`).

## Image generation

Models exported for OVMS's `image_generation` task — for example
[`OpenVINO/stable-diffusion-v1-5-int8-ov`](https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov) —
can be searched, downloaded, loaded and used from the image panel. See the
[OVMS image generation demo](https://docs.openvino.ai/2026/model-server/ovms_demos_image_generation.html)
for background.

Some community repositories ship the pipeline without the converted tokenizer IR
(`openvino_tokenizer.xml`). OVMS loads such a model but fails at generation time, so the load
dialog warns you and offers **Convert tokenizer IR**. The first conversion installs `openvino`,
`openvino-tokenizers`, and `transformers` into the selected OVMS runtime's bundled Python (needs
network access, a few hundred MB, once per runtime) and then converts the tokenizer locally;
later conversions reuse the installed tools.

## Using the model API from other apps

External applications should talk to OVMS directly (the UI only proxies `/proxy/*` to avoid CORS
for its own pages):

| Interface | Endpoint |
| --- | --- |
| Chat completions (OpenAI-compatible) | `POST http://<host>:8000/v3/chat/completions` |
| Embeddings | `POST http://<host>:8000/v3/embeddings` |
| Rerank | `POST http://<host>:8000/v3/rerank` |
| Speech / transcription | `POST http://<host>:8000/v3/audio/speech`, `/v3/audio/transcriptions` |
| Classic IR/ONNX models | KServe / TFS API, e.g. `POST http://<host>:8000/v2/models/<name>/infer` |
| gRPC | port `9000` |

If you set an **OVMS API key** in Settings, clients must send
`Authorization: Bearer <key>`.

## Remote API access

The management UI always listens on `127.0.0.1` and is not exposed to the network. The model API
(OVMS itself) can be exposed independently:

1. **Settings → Advanced (OVMS)** — set the bind address to `0.0.0.0` and, strongly recommended,
   an **OVMS API key**.
2. External clients connect to `http://<host>:<REST port>/v3` with
   `Authorization: Bearer <key>` (or gRPC on the gRPC port).
3. Terminate TLS with a reverse proxy (Caddy, nginx, ...) when leaving localhost.

## Configuration and data

All state lives in one data directory:

- Source checkout: `<project>/data/`
- Packaged exe: `<folder of exe>/data/`
- Override with the `LOCARC_DATA` environment variable (`AI_STUDIO_DATA` is still accepted).

| Path | Contents |
| --- | --- |
| `config.json` | UI/OVMS settings, selection, secrets (HF token, OVMS API key) |
| `load_presets.json` | Per-model load options |
| `models/` | Downloaded models, one folder per model |
| `runtimes/` | Installed OVMS runtimes |
| `chats/` | Chat histories (JSON) |
| `app.log` | Log file for windowed builds |

> Secrets such as the Hugging Face token and the OVMS API key are stored **in plain text** in
> `config.json`. Protect the data directory accordingly.

## Security notes

- The management UI is bound to `127.0.0.1`; only the OVMS model API can be exposed.
- Runtime downloads are restricted to the official GitHub release / OpenVINO storage URLs, and
  SHA-256 checksums are verified when published. Archive extraction rejects path-traversal entries.
- The UI proxy injects the OVMS API key server-side so browsers never see it.
- File operations (model/runtime deletion) are confined to the data directory.

## Troubleshooting

- **Model load fails** — open **Settings → Logs**. LLM memory problems are usually fixed by a
  smaller KV cache, enabling `u8` KV precision, or a smaller context length (the *recommended
  values* button in the load dialog fills in heuristics based on free RAM).
- **`max_prompt_len` is ignored** — that option only applies to NPU; CPU/GPU reject it, so the UI
  omits it automatically.
- **Build fails on OneDrive folders** — `build.bat` builds under `%TEMP%` and copies the result to
  `dist\` to avoid OneDrive sync file locks.
- **Weekly channel shows an unexpected structure error** — the upstream file listing changed;
  please open an issue.

## Project structure

```
locarc.py              Entry point (also used by PyInstaller)
locarc.spec            PyInstaller build configuration (onedir, windowed)
build.bat / build.sh   Build scripts (Windows / Linux)
run.bat / run.sh      Development launchers (Windows / Linux)
app/
  main.py             FastAPI routes, OVMS proxy, static hosting
  ovms.py             Runtime discovery/installation and process control
  models.py           Hugging Face / URL downloads and search, model library
  chats.py            Chat history persistence
  config.py           Paths, configuration, password hashing
  i18n.py             Backend message catalog (en/ja)
  tasks.py            In-memory background task registry
  fsutil.py           Filesystem helpers (safe delete, path containment)
  updater.py          Self-update checks and apply logic (Windows/Linux)
  static/             SPA: index.html, app.js, i18n.js, style.css
scripts/              Helper scripts (smoke-test.ps1 / smoke-test.sh, release notes)
packaging/linux/      Linux install.sh, uninstall.sh and .desktop template
tests/                Backend API tests (pytest)
.github/              Workflows and issue/PR templates
```

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
python -m compileall -q app locarc.py
```

Pull requests run the same checks in CI on Windows and Linux. Windows and Linux executables are
built by the *Build apps* workflow on tags (`v*`) and via manual dispatch.

## Updates

Packaged builds check GitHub Releases on startup (at most once a day) and show an update badge on
the **Settings** tab when a newer version exists. **Settings → Updates** can check manually and
update in one click:

1. The new platform archive (`LocArc-windows-x64.zip` /
   `LocArc-linux-x64.tar.gz`) is downloaded and verified against the release's
   `SHA256SUMS.txt`.
2. The app stages the new build, exits, and a small detached helper replaces the app files
   (`LocArc.exe` / `LocArc` and `_internal`), then restarts the app. The helper
   is PowerShell + robocopy on Windows and a POSIX `sh` script on Linux.

Your `data` folder (runtimes, models, chats, settings) is never touched. The startup check can be
disabled in the same card. When running from source, use `git pull` instead.

> Builds up to **v1.4.0** could fail to apply an update automatically (the helper script was
> started in a way that stopped it from running after the app exited). If an update does not
> restart the app, download the latest release once manually — self-updates work from v1.4.1 on.

## Upgrading from Intel AI Studio

The data layout has not changed: the app still uses the `data` folder next to the executable.
Portable builds keep using it when you extract the new version over the old folder. The Windows
installer keeps the previous installation folder and its `data` when upgrading (the Inno Setup
App ID is unchanged). On Linux, `install.sh` copies `~/.local/share/intel-ai-studio/data` to
`~/.local/share/locarc/data` the first time it runs. The old `AI_STUDIO_DATA` environment
variable is still accepted as an alias for `LOCARC_DATA`.

The first LocArc release also publishes the legacy `Intel-AI-Studio-*` asset names and app layout
so builds from before the rename can update themselves once while the old repository name is
still active. If an older build no longer offers the update after the repository rename, download
v2.0.0 manually once.

## Contributing

Contributions are welcome! [CONTRIBUTING.md](CONTRIBUTING.md) covers the development setup,
coding and localization rules, and the pull request process
([Japanese version](CONTRIBUTING.ja.md)).

- Use the issue forms for bug reports and feature requests.
- Report security issues privately as described in [SECURITY.md](SECURITY.md).
- See [CHANGELOG.md](CHANGELOG.md) for the release history.

## License

[MIT](LICENSE) © 2026 Asahi

Intel and OpenVINO are trademarks of Intel Corporation. This project is not affiliated with,
endorsed by, or sponsored by Intel Corporation.
