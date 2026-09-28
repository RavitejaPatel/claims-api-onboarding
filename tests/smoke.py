#!/usr/bin/env python3
"""Smoke test for a running claims-api deployment.

Checks the application contract from inputs/starter-pack/application-notes.md against a
live URL, after every deploy or rollback (see runbook.md):

  1. /healthz returns 200            (process is up)
  2. /readyz returns 200             (database reachable, schema compatible)
  3. /metrics returns Prometheus text
  4. no admin endpoint answers       (the app has none; nothing must expose one)
  5. HTTPS only: plain HTTP on the same host does not serve the API (https URLs only)

Usage (from a machine inside the allowed network, since the load balancer is internal):
  python tests/smoke.py https://claims-api.dev.apps.example.invalid
  python tests/smoke.py https://claims-api.stage.apps.example.invalid --ca-file platform-ca.pem

Standard library only. Exit code 0 = all checks passed, 1 = at least one failed.
This test was exercised against local stand-ins (tests/test_smoke.py); it has not been run
against a real deployment, because this exercise has none.
"""

from __future__ import annotations

import argparse
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

ADMIN_PATHS = ("/admin", "/admin/", "/actuator", "/debug")


@dataclass
class Response:
    status: int | None
    content_type: str
    body: str
    error: str = ""


def fetch(url: str, timeout: float, context: ssl.SSLContext | None) -> Response:
    request = urllib.request.Request(url, headers={"User-Agent": "claims-api-smoke/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return Response(response.status, response.headers.get("Content-Type", ""), body)
    except urllib.error.HTTPError as error:
        return Response(error.code, error.headers.get("Content-Type", ""), "")
    except (urllib.error.URLError, OSError) as error:
        return Response(None, "", "", str(getattr(error, "reason", error)))


def run(base_url: str, timeout: float = 5.0, ca_file: str | None = None) -> list[tuple[str, bool, str]]:
    """Return (check, passed, detail) for every check."""
    base = base_url.rstrip("/")
    context = ssl.create_default_context(cafile=ca_file) if base.startswith("https://") else None
    results: list[tuple[str, bool, str]] = []

    def get(path: str) -> Response:
        return fetch(base + path, timeout, context)

    health = get("/healthz")
    results.append(("healthz returns 200", health.status == 200, detail(health)))

    ready = get("/readyz")
    hint = "" if ready.status == 200 else " (readiness includes the database: see runbook, ClaimsApiNoReadyPods)"
    results.append(("readyz returns 200", ready.status == 200, detail(ready) + hint))

    metrics = get("/metrics")
    is_prometheus = metrics.status == 200 and "text/plain" in metrics.content_type and "# TYPE" in metrics.body
    results.append(("metrics is Prometheus text", is_prometheus, detail(metrics)))

    exposed = [p for p in ADMIN_PATHS if get(p).status == 200]
    results.append(("no admin endpoint answers", not exposed, f"answered: {exposed}" if exposed else "none answered"))

    if base.startswith("https://"):
        host = urllib.parse.urlsplit(base).netloc
        plain = fetch(f"http://{host}/healthz", timeout, None)
        served = plain.status == 200
        results.append(("plain HTTP does not serve the API", not served, detail(plain)))

    return results


def detail(response: Response) -> str:
    if response.status is None:
        return f"no response ({response.error})"
    return f"HTTP {response.status}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url", help="for example https://claims-api.dev.apps.example.invalid")
    parser.add_argument("--timeout", type=float, default=5.0, help="seconds per request (default 5)")
    parser.add_argument("--ca-file", help="CA bundle, if the platform certificate is not publicly trusted")
    args = parser.parse_args(argv)

    results = run(args.base_url, args.timeout, args.ca_file)
    for name, passed, info in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:36} {info}")
    failed = [name for name, passed, _ in results if not passed]
    print("RESULT: PASS" if not failed else f"RESULT: FAIL ({len(failed)} of {len(results)} checks)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
