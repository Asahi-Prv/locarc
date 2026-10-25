"""Port-conflict handling: another OVMS on our REST port must never look like a stuck load.

On Windows a foreign listener that set SO_REUSEADDR (drogon, and therefore OVMS, does) no
longer blocks ``bind()``, so a bind-only check used to declare the port free: the app started
a second OVMS, the ready probe kept talking to the first server, and the model "loaded
forever" while the new OVMS log said AVAILABLE.
"""
import json
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import ovms


def _listener(reuse_addr: bool = False) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if reuse_addr:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    return s


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _foreign_ovms_server(model: str) -> tuple[ThreadingHTTPServer, int]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server naming)
            if self.path != "/v1/config":
                self.send_error(404)
                return
            body = json.dumps({model: {"model_version_status": [{"state": "AVAILABLE"}]}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the test output quiet
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def test_port_busy_detects_a_listener_with_so_reuseaddr():
    """bind() alone misses this listener on Windows; connecting must catch it."""
    srv = _listener(reuse_addr=True)
    try:
        assert ovms._port_busy(srv.getsockname()[1]) is True
    finally:
        srv.close()


def test_port_busy_is_false_on_a_free_port():
    assert ovms._port_busy(_free_port()) is False


def test_ovms_models_on_port_reads_v1_config():
    httpd, port = _foreign_ovms_server("Qwen2.5-0.5B-Instruct")
    try:
        assert ovms._ovms_models_on_port(port) == ["Qwen2.5-0.5B-Instruct"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ready_probe_fails_when_a_foreign_ovms_owns_the_port():
    """The probe must not wait 300 s for a model another server will never report."""
    httpd, port = _foreign_ovms_server("Qwen2.5-0.5B-Instruct")
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        srv = ovms.OVMServer()
        srv.proc = dummy
        srv.info = {"model": "LFM2.5-1.2B-Instruct-int4-cw-ov", "rest_port": port,
                    "bind_address": "127.0.0.1"}
        srv.load_state = "loading"
        srv._lang = "en"
        srv._ready_probe_impl()
        assert srv.load_state == "failed"
        assert "Qwen2.5-0.5B-Instruct" in srv.load_error
        assert str(port) in srv.load_error
    finally:
        dummy.kill()
        httpd.shutdown()
        httpd.server_close()
