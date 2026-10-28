# Security Policy

## Supported versions

Security fixes are provided for the latest release and the `main` branch. Please make sure you
are up to date before reporting an issue.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub Security Advisories:

<https://github.com/Asahi-Prv/locarc/security/advisories/new>

Please include:

- a description of the vulnerability and its impact,
- steps to reproduce or a proof of concept,
- the affected version or commit,
- your environment (OS, how the app is run, whether it is exposed beyond localhost).

You can expect an initial response within about a week. We will coordinate a fix and a disclosure
date with you, and credit you in the release notes unless you prefer otherwise.

## Scope

LocArc is a local-first management UI for OpenVINO Model Server. The most valuable
reports are:

- bypassing the localhost-only binding of the management UI or the OVMS API key,
- path traversal in model/runtime deletion or archive extraction,
- cross-site scripting (XSS) in the UI,
- SSRF or allow-list bypasses in the URL/download/install endpoints,
- leaking secrets (Hugging Face token, OVMS API key) to the UI or logs,
- denial of service that can be triggered remotely when the OVMS API is exposed.

Out of scope:

- vulnerabilities in OVMS, OpenVINO, Hugging Face, Python packages, or downloaded models —
  please report those to the respective project,
- attacks that require an already-compromised local machine or write access to the data directory,
- behavior that only occurs when the OVMS API is intentionally exposed without an API key or
  reverse proxy. Hardening suggestions for that setup are still welcome.

## Hardening notes

- The management UI always binds to `127.0.0.1`. When exposing the OVMS API (bind address
  `0.0.0.0`), always set an OVMS API key and terminate TLS with a reverse proxy.
- The Hugging Face token and OVMS API key are stored in plain text in `config.json`. Protect the
  data directory accordingly.
- Runtime downloads are restricted to official GitHub release / OpenVINO storage URLs and verify
  published SHA-256 checksums. Archive extraction rejects path-traversal entries.
