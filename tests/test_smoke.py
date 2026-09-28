"""Exercise tests/smoke.py against local stand-ins for claims-api.

There is no real deployment in this exercise, so these tests start a tiny HTTP server on
localhost that behaves like the application contract (and a broken variant), and check
that the smoke test passes and fails for the right reasons.
"""

from __future__ import annotations

import contextlib
import io
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import smoke  # noqa: E402

METRICS = "# HELP http_requests_total Requests.\n# TYPE http_requests_total counter\nhttp_requests_total 1\n"


def make_handler(ready: bool = True, admin: bool = False, metrics_type: str = "text/plain; version=0.0.4"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            if self.path == "/healthz":
                self.reply(200, "text/plain", "ok")
            elif self.path == "/readyz":
                self.reply(200 if ready else 503, "text/plain", "ready" if ready else "database unreachable")
            elif self.path == "/metrics":
                self.reply(200, metrics_type, METRICS)
            elif admin and self.path.startswith("/admin"):
                self.reply(200, "text/html", "admin console")
            else:
                self.reply(404, "text/plain", "not found")

        def reply(self, status: int, content_type: str, body: str) -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:  # keep test output clean
            pass

    return Handler


class StandIn:
    def __init__(self, **behaviour) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(**behaviour))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()


def failed_checks(url: str) -> list[str]:
    return [name for name, passed, _ in smoke.run(url, timeout=2) if not passed]


class SmokeTest(unittest.TestCase):
    def test_healthy_service_passes(self) -> None:
        with StandIn() as url:
            self.assertEqual(failed_checks(url), [])

    def test_database_outage_fails_readiness_only(self) -> None:
        with StandIn(ready=False) as url:
            self.assertEqual(failed_checks(url), ["readyz returns 200"])

    def test_exposed_admin_endpoint_fails(self) -> None:
        with StandIn(admin=True) as url:
            self.assertEqual(failed_checks(url), ["no admin endpoint answers"])

    def test_metrics_must_be_prometheus_text(self) -> None:
        with StandIn(metrics_type="application/json") as url:
            self.assertEqual(failed_checks(url), ["metrics is Prometheus text"])

    def test_unreachable_service_fails_every_http_check(self) -> None:
        with StandIn() as url:
            pass  # server is shut down: nothing listens on this port any more
        self.assertEqual(len(failed_checks(url)), 3)

    def test_exit_code(self) -> None:
        with StandIn() as url, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.main([url, "--timeout", "2"]), 0)
        with StandIn(ready=False) as url, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.main([url, "--timeout", "2"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
