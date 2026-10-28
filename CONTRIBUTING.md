# Contributing to LocArc

[日本語版はこちら](CONTRIBUTING.ja.md)

Thanks for your interest in contributing! This guide covers development setup, project
conventions, and the review process.

> **Security issues:** please do not open a public issue. See [SECURITY.md](SECURITY.md).

## Ways to contribute

- Bug reports — use the issue forms and include logs plus your environment.
- Feature requests and UX feedback.
- Pull requests: bug fixes, features, documentation, and localization.
- Testing on different hardware (CPU / GPU / NPU) and operating systems.

## Development setup

Requirements: Python 3.12+, Git, and Windows 10/11 or Ubuntu 24.04.

```bash
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.main        # or run.bat (Windows) / ./run.sh (Linux)
```

The app stores all state in `./data` (override with the `LOCARC_DATA` environment variable).
Test runs use a temporary data directory and never touch your real one.

## Checks before pushing

```bash
ruff check .
pytest -q
python -m compileall -q app tests locarc.py
```

CI runs the same commands on every pull request (Windows and Linux), plus Windows and Linux
executable builds on tags.

## Coding guidelines

- Target Python 3.12 and start modules with `from __future__ import annotations`.
- Add type hints to public helpers; keep functions small and focused.
- Write comments and docstrings in English.
- Never hardcode user-facing strings in `app.js` or backend handlers — route them through i18n.
- Prefer the standard library and the dependencies already listed in `requirements.txt`.
- Keep the app local-first: new features must not open listening sockets by default.

## Localization (i18n)

All user-facing text lives in two catalogs:

| File | Scope | Example |
| --- | --- | --- |
| `app/static/i18n.js` | UI labels, buttons, toasts, dynamic text | `t("models.download")` |
| `app/i18n.py` | API errors and task progress messages | `tr(lang, "err.not_found")` |

Rules:

- Add every new key to **both** `en` and `ja`. Missing keys fall back to English.
- HTML: use `data-i18n`, `data-i18n-html`, `data-i18n-placeholder`, or `data-i18n-title`.
- Translations containing markup must go through `data-i18n-html` (the values are trusted constants).
- Interpolation uses `{name}` placeholders: `t("search.results", { n: 10 })`.

## Testing

- Backend tests live in `tests/test_api.py` and run with `pytest -q`.
- Do not call the network from tests; monkeypatch module functions (see the search endpoint test).
- For UI changes, verify both languages (`#btnLang` in the sidebar) and at least one narrow window size.
- Manual smoke test: runtime install → model download → load → chat.

## Pull requests

1. Fork the repository and create a branch: `fix/...`, `feat/...`, `docs/...`, or `i18n/...`.
2. Keep one logical change per PR so it is easy to review and revert.
3. Fill in the pull request template, link the related issue, and describe how you tested.
4. Make sure CI is green. Maintainers may request changes before merging.

## Commit messages

- Write an imperative, concise subject: `fix: reject path traversal in model delete`.
- Optional prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`, `chore:`.
- Explain the "why" in the body when it is not obvious from the diff.

## Issue guidelines

- Search existing issues first, then use the bug report or feature request form.
- Bug reports should include the app version/commit, OS, how you run the app, OVMS runtime
  version, model, device, and redacted logs (**Settings → Logs**).
- Problems with OVMS itself belong upstream:
  <https://github.com/openvinotoolkit/model_server/issues>.

## Release process (maintainers)

1. Make sure CI is green on `main`.
2. Update `CHANGELOG.md` by moving the relevant `[Unreleased]` entries into a new version
   section.
3. Bump `app/version.py` so local builds report the new version (release builds overwrite it
   from the tag anyway).
4. Tag and push:

   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```

The *Build apps* workflow then:

- stamps the tag version into `app/version.py`,
- builds the Windows and Linux executables and smoke-tests each,
- packages the Windows portable zip, the Inno Setup installer, and the Linux tarball, then writes a
  combined `SHA256SUMS.txt`,
- generates categorized notes from conventional commits (`scripts/release_notes.py`),
- publishes the GitHub release with all files attached.

Notes are grouped by commit type (`feat:`, `fix:`, ...), so keep subjects conventional.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
