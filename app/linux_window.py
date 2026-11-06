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
        from gi.repository import GLib, GObject, Gtk, WebKit2
    except (ImportError, ValueError) as e:
        print(f"WebKitGTK backend unavailable: {e}", file=sys.stderr)
        return 2

    def on_download_started(_source, download):
        """Save downloads (e.g. the chat-history export) via a Save-as dialog."""

        def decide(_download, suggested_filename):
            dialog = Gtk.FileChooserDialog(
                title="Save",
                action=Gtk.FileChooserAction.SAVE,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_SAVE, Gtk.ResponseType.ACCEPT),
            )
            folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
            if folder:
                dialog.set_current_folder(folder)
            if suggested_filename:
                dialog.set_current_name(suggested_filename)
            dialog.set_do_overwrite_confirmation(True)
            try:
                response = dialog.run()
                path = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
            finally:
                dialog.destroy()
            if path:
                download.set_destination(GLib.filename_to_uri(path))
                return True
            download.cancel()
            return False

        download.connect("decide-destination", decide)

    window = Gtk.Window(title="LocArc")
    window.set_default_size(1280, 860)
    window.set_size_request(960, 640)
    webview = WebKit2.WebView()
    # WebKitGTK drops downloads the app does not handle. Prefer the network
    # session (WebKitGTK >= 2.40), fall back to the deprecated context signal.
    sources = []
    session_getter = getattr(webview, "get_network_session", None)
    if session_getter is not None:
        sources.append(session_getter())
    sources.append(webview.get_context())
    for source in sources:
        try:
            if source is not None and GObject.signal_lookup("download-started", source.__gtype__):
                source.connect("download-started", on_download_started)
                break
        except Exception as e:  # never take the window down over a download hook
            print(f"[desktop] download handling unavailable ({e})", file=sys.stderr)
            break
    webview.load_uri(url)
    window.add(webview)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    print("READY", flush=True)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8810"))
