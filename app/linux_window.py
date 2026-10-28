"""Open the LocArc UI in a native WebKitGTK window.

The packaged app bundles its own Python, which does not provide PyGObject or
WebKit2. On Linux the app therefore runs this helper with the distribution's
Python 3 (``/usr/bin/python3``), which does. It prints ``READY`` once the window
is shown so the caller can fall back to a browser when GTK/WebKit is missing.

Requirements (Ubuntu/Debian):

    sudo apt install python3-gi gir1.2-webkit2-4.1
"""
from __future__ import annotations

import ctypes
import os
import sys

PR_SET_PDEATHSIG = 1
SIGTERM = 15


def _die_with_parent() -> None:
    """Ask the kernel to SIGTERM this helper when the app process exits."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, SIGTERM, 0, 0, 0)
    except Exception:
        pass


def main(url: str) -> int:
    _die_with_parent()
    if os.getppid() == 1:  # the app already exited before prctl took effect
        return 0
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gtk, WebKit2
    except (ImportError, ValueError) as e:
        print(f"WebKitGTK backend unavailable: {e}", file=sys.stderr)
        return 2

    window = Gtk.Window(title="LocArc")
    window.set_default_size(1280, 860)
    window.set_size_request(960, 640)
    webview = WebKit2.WebView()
    webview.load_uri(url)
    window.add(webview)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    print("READY", flush=True)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8810"))
