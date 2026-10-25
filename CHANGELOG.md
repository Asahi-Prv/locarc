# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Model loads no longer hang forever when another application already serves the REST port:
  on Windows a foreign listener that set `SO_REUSEADDR` (OVMS does) does not block `bind()`, so
  the port check passed, a second OVMS started, and the ready probe kept querying the other
  server — the UI stayed on "Loading..." while OVMS logged AVAILABLE. The check now connects to
  the port first and names the other OVMS and its models in the error; the ready probe also
  fails fast with that message when a different server answers on the port (instead of waiting
  for the 300 s timeout).

## [1.14.1] - 2026-10-26

### Fixed

- Automatic chat titles work again: the UI catalog never defined `chat.new_title`, so
  `isDefaultTitle()` compared against `undefined` and always failed — the provisional
  40-character title was never set, titling was never scheduled, and chats kept the
  "新しいチャット"/"New chat" title.

### Changed

- Automatic titling runs as soon as the first reply finishes instead of after 5 seconds of idle,
  and the in-flight title request is cancelled when a new message is sent, so it never competes
  with prompts for OVMS's single inference slot. Chats still on the default title are titled when
  they are opened.

## [1.14.0] - 2026-10-24

### Changed

- UI redesign: the app now uses a monochrome "wireframe" theme on a white background.
  The former blue/green/pink palette is replaced by a single grayscale ramp, and structure
  is expressed with hairline outlines instead of filled panels and shadows. Primary
  actions — and loaded/selected states — are the only solid-black elements; warnings and
  provisional states use dashed borders, and focus rings are dashed outlines.
- The chat composer is now a single outlined rounded box containing the message input, the
  parameter toggle and the send button, in the style of ChatGPT. User messages get a
  solid-black avatar while the assistant keeps an outlined one, so the roles stay
  distinguishable without color.
- Native controls (select dropdowns, checkboxes, scrollbars) render light via
  `color-scheme: light`, matching the new palette.

## [1.13.3] - 2026-10-19

### Fixed

- Model search quality: a plain Hugging Face query is dominated by the far more popular PyTorch
  repos, so the first page rarely contained IR files (0 hits for `qwen3`, `llama 3`, `whisper`).
  Search now uses the `openvino` tag and the official `OpenVINO` org as primary sources (with the
  plain search as a fallback for narrow queries), verifies a matching `.xml`/`.bin` pair, and
  re-ranks by query relevance, official origin, then popularity.

## [1.13.2] - 2026-10-19

### Fixed

- Device detection is cached per runtime but was never refreshed, so an NPU (or GPU) that became
  available after the first probe — for example after installing the Intel NPU driver — stayed
  invisible. Opening the load dialog now re-detects, and a new **Re-detect** button forces a
  refresh.

## [1.13.1] - 2026-10-11

### Fixed

- Linux: installing an OVMS runtime failed with "'…/libopenvino_tokenizers.so' is a link to an
  absolute path". The official packages ship absolute symlinks (Docker `/ovms` layout); they are
  now rewritten to equivalent relative links, while extraction still rejects paths that escape the
  destination.
- Linux: the app opened in the browser instead of a native window. It now uses the distribution's
  Python + WebKitGTK for a real window (install `python3-gi` and `gir1.2-webkit2-4.1`), falling
  back to the browser only when WebKitGTK is missing.

## [1.13.0] - 2026-10-11

### Added

- Linux support: releases now include a portable `Intel-AI-Studio-linux-x64.tar.gz` (Ubuntu 24.04)
  with a per-user `install.sh`/`uninstall.sh` and an application-menu entry.
- One-click self-update now works on Linux via a detached POSIX `sh` helper, in addition to the
  Windows PowerShell helper.

### Changed

- CI runs the test suite on Windows and Linux; the *Build apps* workflow builds, smoke-tests and
  publishes both platforms with a combined `SHA256SUMS.txt`.
- Free-RAM detection for the load-option recommendation works on Linux (`os.sysconf`).
- Docs: Linux install/build/update instructions; release notes cover both platforms.

## [1.12.2] - 2026-10-10

### Fixed

- Model search: double-clicking Download no longer starts duplicate downloads. Buttons are
  greyed out (“Downloaded” / “Downloading…”) for models already in the library or with a
  download in flight, and the API rejects parallel downloads of the same repo and repos that
  are already in the library (HTTP 409).

## [1.12.1] - 2026-10-10

### Changed

- The NPU / channel-wise advice moved from the download flow to the load dialog: selecting NPU
  shows a CW tip, or a specific warning when the model is detected as non-CW quantized (from its
  name and saved origin). The download-time confirmation and the per-result warning line were
  removed; search results keep the INT4/CW badges and the card note is softer.

### Added

- `GET /api/model/load_options` now returns the detected quantization (`quant`, `cw`).

## [1.12.0] - 2026-10-10

### Added

- Model search detects the weight quantization (INT4 / INT8 / NF4) and channel-wise (CW)
  builds from the Hugging Face repo name and tags; results show badges (e.g. `INT4` `CW`).
- Non-CW quantized models get an “NPU recommends channel-wise (CW)” hint, and on machines
  with an NPU the download asks for confirmation first. The search card explains the
  `-int4-cw-ov` naming convention.
- Devices are fetched at startup so device-aware hints work before the load dialog opens.

## [1.11.0] - 2026-10-10

### Added

- Chat message actions (appear on hover): copy any message, regenerate the last answer, and edit
  a sent prompt to run it again — editing drops the later messages, a simple form of branching.
  A confirmation warns that the previous branch is not kept.

### Changed

- The confirmation dialog only uses the red “delete” styling when no custom confirm label is set.

## [1.10.1] - 2026-10-10

### Changed

- Tokenizer conversion now shows its progress inside the load dialog (spinner + status text)
  instead of in the task panel behind the overlay; the task only appears in the panel when the
  dialog is closed.

## [1.10.0] - 2026-10-10

### Added

- One-click tokenizer IR conversion for image-generation models that lack
  `openvino_tokenizer.xml` (many community repos, e.g. Z-Image). The load dialog warns and offers
  the conversion; the first run installs `openvino` / `openvino-tokenizers` / `transformers` into
  the selected OVMS runtime's Python (network, a few hundred MB, once per runtime) and the app
  stays small.
- Image-generation guidance: the load dialog marks `image_generation` models and explains the
  image panel, which now has an empty-state hint.

## [1.9.1] - 2026-10-10

### Fixed

- Image generation works through the UI again: OVMS gzip-compresses large JSON replies (the
  base64 image), and the proxy forwarded the raw compressed bytes without the encoding header,
  so the UI saw unparsable data and showed a garbled error. The proxy now asks OVMS for identity
  encoding and forwards the decoded body.
- Settings is back to a single-column layout: the masonry columns could move the tall log card
  out of view in WebView2.

## [1.9.0] - 2026-10-10

### Added

- Model search no longer requires the `openvino` tag and accepts a pasted repo id (`org/name`),
  so official models like `OpenVINO/stable-diffusion-v1-5-int8-ov` (which is not tagged) are
  found.

### Fixed

- Image-generation errors are shown as readable text (JSON error messages are unwrapped)
  instead of `Unexpected token ... is not valid JSON` when a response is not JSON.
- Chat title generation retries with a larger token budget, so thinking models that ignore the
  thinking-off hint still produce a title.

### Changed

- The "Generate title" button moved to the chat header (the parameters panel starts collapsed).
- Settings uses a masonry-style two-column layout, removing the empty gaps left behind after the
  WebUI cards were removed.

## [1.8.1] - 2026-10-10

### Fixed

- Leftover OVMS processes from a force-killed older build are now cleaned up at startup (only
  when their owning manager is gone), so they can no longer hold the REST/gRPC ports and make
  model loads fail.
- Starting a model now reports "<port> is already in use" instead of a raw OVMS exit, so port
  conflicts (for example from a stale process) are obvious.

## [1.8.0] - 2026-10-09

### Changed

- Removed the remaining WebUI-era features now that the app is desktop-only:
  the management-UI login/session/logout, the quit-app API and card (close the window instead),
  and the remote-access UI card. The management UI has always been bound to `127.0.0.1`; remote
  model-API access is still available through OVMS with the API key.

### Fixed

- OVMS is no longer left running when the app exits or restarts: it is stopped explicitly on
  window close and before an update, and a Windows job object kills it even if the manager
  crashes or is force-killed (so its RAM/VRAM is released).
- Image-generation models without a converted tokenizer (`openvino_tokenizer.xml`) now show a
  warning in the load dialog instead of failing silently at generation time.

## [1.7.0] - 2026-10-08

### Added

- Tokens-per-second profiling: live tokens/sec, elapsed time, and token count under each reply,
  both while streaming and when a chat is re-opened.
- Reasoning ("think") blocks are stored with the chat and shown collapsed in history (click to
  expand); they no longer disappear when you revisit a chat.
- Copy button for the OVMS log in Settings (with a WebView2-safe clipboard fallback).
- "Generate title" button in the parameters panel; automatic titling retries without the
  thinking-off hint if a model rejects it.
- Spinner while a model is loading and while the prompt is being evaluated; the image-generation
  button also shows a spinner.

### Changed

- The send button is now an icon (paper plane).
- When OVMS exits during loading, the failure message now includes the last log line, so the
  cause is visible without opening the log tab.

## [1.6.0] - 2026-10-08

### Changed

- Simpler, calmer UI: flatter surfaces (no card/item borders), softer buttons, accent-tinted
  active chat, and model/mode/device details moved into the status-badge tooltip.
- The generation-parameters panel now starts collapsed (the choice is remembered), giving the
  chat more room.
- Chat bubbles no longer repeat a "You/AI" label above every message.
- Typography refresh: Segoe UI Variable / system-ui stack with a Yu Gothic UI fallback, Cascadia
  Mono for code and logs, and a slightly roomier line height.

## [1.5.0] - 2026-10-08

### Changed

- The app now always runs in the native desktop window (WebView2). The browser-based UI mode has
  been removed: both the portable zip and the installer launch the same desktop app, and a
  self-update restarts the desktop window instead of opening a browser tab.
- Installer shortcuts, release notes, and the README no longer mention `--desktop` or a browser UI.

### Removed

- The sidebar "Quit app" shortcut. Closing the window quits the app, and the Settings card still
  has an explicit quit button.

## [1.4.2] - 2026-10-08

### Fixed

- Starting a model no longer opens a command-prompt window. OVMS and the update helper are
  launched with `CREATE_NO_WINDOW`, so console-less windowed/desktop builds no longer get a
  console window per child process.
- Device detection actually works now. OVMS's bundled Python ships no OpenVINO bindings, so the
  previous probe always came back empty (the device list silently fell back to CPU/GPU). The app
  now queries the runtime's `openvino_c.dll` directly, in-process, and only offers the devices the
  machine really reports (NPU appears when present).

## [1.4.1] - 2026-10-08

### Fixed

- Self-update actually applies on Windows now: the updater script was launched with
  `DETACHED_PROCESS`, which stopped PowerShell from running once the app exited. It now uses
  `CREATE_NO_WINDOW`. Builds up to v1.4.0 need one manual update to get this fix.

### Changed

- Desktop (installed) builds hide the browser-only "Quit app" shortcut and use
  window-appropriate wording for the shutdown/update overlays.

## [1.4.0] - 2026-10-08

### Changed

- Configuration and app state are cached by file timestamp, so API calls no longer re-read
  `config.json` on every request (including the auth middleware).
- The load dialog opens immediately: it shows the last known devices and fills in the real
  OpenVINO device list asynchronously, so the first probe no longer blocks it.
- Downloads and installs show up in the task panel immediately instead of after the next poll.
- Deleting models and chats updates the list optimistically and rolls back on failure
  (removing multi-GB model folders no longer freezes the list).
- Refreshed UI: design tokens, animated overlays/toasts/task panel, custom scrollbars,
  focus-visible rings, hover/active feedback, SVG icons, and a responsive two-column Settings
  layout.

## [1.3.0] - 2026-10-06

### Changed

- Smoother UI: the status and task panels only re-render when something actually changed, task
  rows are updated in place (progress bars animate instead of resetting every poll), and polling
  pauses while the tab is hidden.
- Streaming chat repaints on animation frames, auto-scrolls only while you are near the bottom,
  and streams very long answers as plain text before rendering Markdown at the end.
- Auto-generated chat titles now wait for 8 seconds of idle time (and abort after 20 seconds), so
  they no longer occupy the model while you type your next message.
- The model dropdown is only rebuilt when the model list actually changes.

### Added

- JavaScript syntax checks and Markdown renderer tests (QuickJS) in the test suite.

## [1.2.0] - 2026-10-06

### Added

- Native desktop mode: `--desktop` opens the UI in a WebView2 window instead of the browser.
- Windows installer (`Intel-AI-Studio-Setup-x64.exe`, Inno Setup): per-user install with Start
  Menu and optional desktop shortcuts. The portable zip remains available.
- The NPU device option is now only offered when the installed runtime reports an NPU.
- Releases now ship the installer alongside the portable zip, and checksums cover both.

### Fixed

- Self-update no longer hangs when Windows reuses the old process id: the updater waits for the
  executable lock to be released instead of polling a PID.

## [1.1.1] - 2026-10-05

### Changed

- Documented the self-update flow in the README (English/Japanese).

## [1.1.0] - 2026-10-05

### Added

- Self-update for packaged builds: a startup check (at most once a day) plus a one-click update
  that downloads the new release, verifies its SHA-256, replaces the app and restarts it while
  keeping the `data` folder. Source runs show a `git pull` hint instead.
- Update notification: a red dot on the Settings tab and an Updates card in Settings.
- Escape-first ZIP extraction helper shared by runtime installs and updates.

## [1.0.3] - 2026-10-05

### Added

- Markdown rendering for model responses (headings, lists, tables, code blocks, links, emphasis).
- Automatic chat titles: the loaded model suggests a short title after the first exchange.
- Cancellable downloads and runtime installs (cancel button in the task panel).
- Paged OpenVINO IR model search with infinite scrolling and a "Load more" fallback.

### Changed

- The **New Chat** button no longer creates an empty chat immediately; the chat is created when
  the first prompt is sent.
- Enter sends a chat message and Shift+Enter inserts a newline (IME-safe while converting).

## [1.0.2] - 2026-10-05

### Added

- Show the application version in **Settings → Info**.
- Curated release notes generated from conventional commits, with SHA-256 checksums attached
  to each release (`SHA256SUMS.txt`).
- `.github/release.yml` so GitHub's built-in release-note generator groups PRs by label.

### Changed

- Release builds take their version from the git tag (`app/version.py` is rewritten in CI).

## [1.0.1] - 2026-10-05

### Fixed

- Packaged executable: bundled OVMS runtimes now start correctly. OVMS ships an embeddable
  Python whose search paths live in `pythonXY._pth` (stdlib under `python\pythonXY`); those
  entries are now mirrored through `PYTHONPATH`, fixing
  `ModuleNotFoundError: No module named 'encodings'`.
- The configured gRPC port is now applied on OVMS builds that renamed `--grpc_port` to `--port`
  (previously the flag was silently dropped and gRPC stayed disabled).

## [1.0] - 2026-10-05

### Added

- Initial public release.
- OVMS runtime installer: stable (GitHub releases) and weekly builds, `python_on` packages only,
  SHA-256 verification when available.
- Model downloads from Hugging Face (public and gated) and direct URLs (zip/tar auto-extract).
- OpenVINO IR-only model search on Hugging Face (`.xml` + `.bin` pair required), with optional
  downloads that skip non-IR weights.
- Model load/unload with device selection (CPU/GPU/NPU/AUTO), serve-mode auto-detection, and
  LLM load options (KV cache size/precision, context length, prefix caching, ...).
- Streaming chat (thinking content, per-chat generation parameters, persisted history) and
  image generation.
- English / Japanese UI with a runtime language switch.
- Optional management-UI login (PBKDF2, session cookie, rate limiting) and OVMS API key,
  local-first defaults.
- One-click Windows build (PyInstaller spec) with CI lint/tests, executable smoke test, and
  automatic GitHub releases.

[Unreleased]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.12.2...HEAD
[1.12.2]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.12.1...v1.12.2
[1.12.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.12.0...v1.12.1
[1.12.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.11.0...v1.12.0
[1.11.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.10.1...v1.11.0
[1.10.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.10.0...v1.10.1
[1.10.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.9.1...v1.10.0
[1.9.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.4.2...v1.5.0
[1.4.2]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.0.3...v1.1.0
[1.0.3]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/Asahi-Prv/i-AI-Studio/compare/v1.0...v1.0.1
[1.0]: https://github.com/Asahi-Prv/i-AI-Studio/releases/tag/v1.0
