#!/usr/bin/env python3
"""Generate categorized Markdown release notes from conventional commits.

Usage examples:
    python scripts/release_notes.py --from v1.0 --to v1.0.1 --repo Asahi-Prv/locarc
    python scripts/release_notes.py --to HEAD --install
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SECTIONS: tuple[tuple[str, str], ...] = (
    ("feat", "Features"),
    ("fix", "Bug Fixes"),
    ("perf", "Performance"),
    ("docs", "Documentation"),
    ("refactor", "Refactoring"),
    ("test", "Tests"),
    ("build", "Build"),
    ("ci", "CI"),
    ("i18n", "Localization"),
    ("chore", "Chores"),
)

_COMMIT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<subject>.+)$", re.I)

INSTALL_SECTION = """\
## Installation

### Windows

**Installer (recommended)** — run `LocArc-Setup-x64.exe`. It installs per-user (no admin
rights), adds Start Menu and optional desktop shortcuts, and opens the app in a native desktop
window.

**Portable** — download `LocArc-windows-x64.zip`, extract it anywhere and run
`LocArc.exe`; the app opens in a native desktop window (no installation required).

Windows may show a SmartScreen warning because the executables are unsigned — choose
**More info → Run anyway**.

### Linux (Ubuntu 24.04)

Download `LocArc-linux-x64.tar.gz`, then either run it from anywhere or install it per-user:

```bash
tar -xzf LocArc-linux-x64.tar.gz
cd LocArc
./install.sh        # adds a launcher and an application-menu entry (no root needed)
```

Run `./uninstall.sh` to remove it (add `--purge` to delete user data too). A native window needs
WebKitGTK (`sudo apt install python3-gi gir1.2-webkit2-4.1`); without it the app opens in your
browser instead.

All data (runtimes, models, chats, settings) is stored in a `data` folder next to the executable
and is preserved across upgrades.
"""


def parse_subject(subject: str) -> tuple[str, str] | None:
    """Return ``(type, formatted text)`` for a conventional commit subject, else ``None``."""
    match = _COMMIT_RE.match(subject.strip())
    if match is None:
        return None
    text = match.group("subject").strip()
    if match.group("scope"):
        text = f"**{match.group('scope')}**: {text}"
    return match.group("type").lower(), text


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def collect(from_ref: str, to_ref: str) -> str:
    """Return a Markdown section list of commits between the two refs."""
    revision_range = f"{from_ref}..{to_ref}" if from_ref else to_ref
    log = _git("log", revision_range, "--no-merges", "--pretty=format:%h\t%s")
    buckets: dict[str, list[tuple[str, str]]] = {key: [] for key, _ in SECTIONS}
    other: list[tuple[str, str]] = []
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        if not subject:
            continue
        parsed = parse_subject(subject)
        if parsed is None:
            other.append((sha, subject))
            continue
        commit_type, text = parsed
        if commit_type in buckets:
            buckets[commit_type].append((sha, text))
        else:
            other.append((sha, subject))

    lines: list[str] = []
    for key, title in SECTIONS:
        items = buckets[key]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.extend(f"- {text} ({sha})" for sha, text in items)
        lines.append("")
    if other:
        lines.append("### Other Changes")
        lines.extend(f"- {text} ({sha})" for sha, text in other)
        lines.append("")
    if not lines:
        lines.append("No changes.")
    return "\n".join(lines).rstrip() + "\n"


def build_notes(from_ref: str, to_ref: str, repo: str | None = None,
                checksums: str | None = None, install: bool = False) -> str:
    parts = ["## What's Changed", "", collect(from_ref, to_ref).rstrip(), ""]
    if install:
        parts += [INSTALL_SECTION.rstrip(), ""]
    if checksums:
        text = Path(checksums).read_text(encoding="utf-8").strip()
        parts += ["## Checksums", "", "```", text, "```", ""]
    if repo:
        if from_ref:
            compare = f"https://github.com/{repo}/compare/{from_ref}...{to_ref}"
        else:
            compare = f"https://github.com/{repo}/releases/tag/{to_ref}"
        parts += [f"**Full Changelog**: {compare}"]
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate release notes from conventional commits.")
    parser.add_argument("--from", dest="from_ref", default="", help="previous tag (empty for the first release)")
    parser.add_argument("--to", dest="to_ref", default="HEAD", help="target ref (default: HEAD)")
    parser.add_argument("--repo", help="owner/name, used for the compare link")
    parser.add_argument("--checksums", help="path to a SHA256SUMS file to embed")
    parser.add_argument("--install", action="store_true", help="append installation instructions")
    parser.add_argument("--output", default="-", help="output file ('-' for stdout)")
    args = parser.parse_args(argv)

    notes = build_notes(args.from_ref, args.to_ref, repo=args.repo,
                        checksums=args.checksums, install=args.install)
    if args.output == "-":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.write(notes)
    else:
        Path(args.output).write_text(notes, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
