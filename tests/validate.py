#!/usr/bin/env python3
"""One-command validation for the claims-api onboarding.

Steps:
  1. Render the dev and stage overlays with Kustomize.
  2. Validate every rendered resource against the Kubernetes 1.30 schemas (kubeconform).
  3. Run the contract checks for each environment.
  4. Check that dev and stage differ only in approved overlay fields.
  5. Scan the repository for credentials.
  6. Run the unit tests (manifests, delivery path, workflow trust rules, smoke test).
  7. Check and unit-test the alert rules with promtool (optional locally; --strict in CI).

Rendered manifests and a log of everything are written to evidence/.
Nothing is deployed and no cluster is contacted.

Usage:
  python tests/validate.py                  # label defaults to your OS, e.g. "local (Windows)"
  python tests/validate.py --where ci       # label used in the evidence file name/header
  python tests/validate.py --strict         # fail if an optional tool (promtool) is missing
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import platform
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import contract_checks as cc  # noqa: E402
import manifests  # noqa: E402
import secret_scan  # noqa: E402

EVIDENCE = manifests.REPO_ROOT / "evidence"
KUBERNETES_VERSION = "1.30.0"


class Log:
    """Print to the console and keep a copy for the evidence file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)


def tool_version(command: list[str]) -> str:
    try:
        out = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except (OSError, IndexError):
        return "not found"


def git_commit() -> str:
    if not shutil.which("git"):
        return "unknown (git not found)"
    out = subprocess.run(
        ["git", "-C", str(manifests.REPO_ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    dirty = subprocess.run(
        ["git", "-C", str(manifests.REPO_ROOT), "status", "--porcelain", "--", "solution", "tests", ".github"],
        capture_output=True, text=True, check=False,
    )
    commit = out.stdout.strip() or "unknown"
    return commit + (" (with uncommitted changes in solution/, tests/ or .github/)" if dirty.stdout.strip() else "")


def content_fingerprint() -> str:
    """sha256 over every file in solution/, tests/ and .github/, line endings normalized.

    Git commit hashes differ between copies of the repo; this does not. Two runs with the
    same fingerprint validated byte-identical manifests and tests.
    """
    import hashlib

    root = manifests.REPO_ROOT
    digest = hashlib.sha256()
    for folder in ("solution", "tests", ".github"):
        files = [
            p for p in (root / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
        # Sort by the POSIX path string, not Path objects: Windows paths compare
        # case-insensitively, which would give a different order (and hash) than Linux.
        for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--where", default=f"local ({platform.system()})",
                        help="where this run happens, recorded in the evidence file")
    parser.add_argument("--strict", action="store_true",
                        help="treat missing optional tools (promtool) as a failure; used in CI")
    args = parser.parse_args()

    missing = []
    if not (shutil.which("kustomize") or shutil.which("kubectl")):
        missing.append("kustomize (or kubectl): https://github.com/kubernetes-sigs/kustomize/releases")
    if not shutil.which("kubeconform"):
        missing.append("kubeconform: https://github.com/yannh/kubeconform/releases")
    if missing:
        print("Missing tools. Install them and make sure they are on PATH:")
        for item in missing:
            print(f"  - {item}")
        return 2

    log = Log()
    failures: list[str] = []
    started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    log("claims-api validation")
    log(f"  where:       {args.where}")
    log(f"  when (UTC):  {started.isoformat()}")
    log(f"  commit:      {git_commit()}")
    log(f"  content:     {content_fingerprint()} (sha256 of solution/, tests/ and .github/)")
    log(f"  python:      {platform.python_version()}")
    log(f"  kustomize:   {tool_version(manifests.kustomize_version_command())}")
    log(f"  kubeconform: {tool_version(['kubeconform', '-v'])}")
    log(f"  promtool:    {tool_version(['promtool', '--version']) if shutil.which('promtool') else 'not installed (optional)'}")
    log("  scope:       static checks only; nothing is deployed and no cluster is contacted")
    log()

    # 1. Render
    log("[1/7] Render overlays with Kustomize")
    rendered_dir = EVIDENCE / "rendered"
    rendered_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, list[dict]] = {}
    for env in manifests.ENVIRONMENTS:
        try:
            text = manifests.render_text(env)
        except subprocess.CalledProcessError as error:
            log(f"  FAIL {env}: {error.stderr.strip()}")
            failures.append(f"render {env}")
            continue
        (rendered_dir / f"{env}.yaml").write_text(text, encoding="utf-8", newline="\n")
        rendered[env] = manifests.load(text)
        kinds = ", ".join(sorted(f"{d['kind']}/{d['metadata']['name']}" for d in rendered[env]))
        log(f"  PASS {env}: {len(rendered[env])} resources -> evidence/rendered/{env}.yaml")
        log(f"       {kinds}")
    if len(rendered) != len(manifests.ENVIRONMENTS):
        log("\nRendering failed; later steps need rendered output.")
        return finish(log, failures, args.where, started)

    # 2. Schema validation
    log("\n[2/7] Validate against Kubernetes schemas (kubeconform)")
    if shutil.which("kubeconform"):
        files = [str(rendered_dir / f"{env}.yaml") for env in manifests.ENVIRONMENTS]
        out = subprocess.run(
            ["kubeconform", "-strict", "-summary", "-kubernetes-version", KUBERNETES_VERSION, *files],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        for line in (out.stdout + out.stderr).strip().splitlines():
            log(f"  {line}")
        if out.returncode != 0:
            failures.append("kubeconform")
        log(f"  {'PASS' if out.returncode == 0 else 'FAIL'} schema validation")
    else:
        log("  FAIL kubeconform not found on PATH: https://github.com/yannh/kubeconform/releases")
        failures.append("kubeconform missing")

    # 3. Contract checks
    log("\n[3/7] Contract checks")
    for env in manifests.ENVIRONMENTS:
        for name, problems in cc.run_all(rendered[env], env).items():
            log(f"  {'PASS' if not problems else 'FAIL'} {env:5} {name}")
            for problem in problems:
                log(f"         - {problem}")
            if problems:
                failures.append(f"{env} {name}")

    # 4. Drift
    log("\n[4/7] Environment drift (dev vs stage)")
    drift = cc.check_drift(rendered["dev"], rendered["stage"])
    log(f"  {'PASS' if not drift else 'FAIL'} dev and stage differ only in approved overlay fields")
    for problem in drift:
        log(f"         - {problem}")
    if drift:
        failures.append("drift")

    # 5. Secret scan
    log("\n[5/7] Credential scan (whole repository)")
    findings = secret_scan.scan_repo()
    log("  PASS no credential markers found" if not findings else "  FAIL credential markers found")
    for finding in findings:
        log(f"         - {finding}")
    if findings:
        failures.append("secret scan")

    # 6. Unit tests
    log("\n[6/7] Unit tests (python -m unittest)")
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
    with redirect_stdout(stream), redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    for line in stream.getvalue().strip().splitlines():
        log(f"  {line}")
    if not result.wasSuccessful():
        failures.append("unit tests")

    # 7. Alert rules
    log("\n[7/7] Alert rules (promtool)")
    rules = manifests.REPO_ROOT / "solution" / "observability"
    if shutil.which("promtool"):
        for label, command in (
            ("rule syntax", ["promtool", "check", "rules", str(rules / "alerts.yaml")]),
            ("alert unit tests", ["promtool", "test", "rules", str(rules / "alerts.test.yaml")]),
        ):
            out = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
            for line in (out.stdout + out.stderr).strip().splitlines():
                log(f"  {line}")
            log(f"  {'PASS' if out.returncode == 0 else 'FAIL'} {label}")
            if out.returncode != 0:
                failures.append(label)
    elif args.strict:
        log("  FAIL promtool not found on PATH (required with --strict)")
        failures.append("promtool missing")
    else:
        log("  SKIP promtool not installed; alert rules are checked in CI (see tests/README.md)")

    return finish(log, failures, args.where, started)


def finish(log: Log, failures: list[str], where: str, started: dt.datetime) -> int:
    log()
    log("RESULT: PASS" if not failures else f"RESULT: FAIL ({', '.join(failures)})")
    slug = re.sub(r"[^a-z0-9]+", "-", where.lower()).strip("-")
    path = EVIDENCE / f"validation-{slug}.txt"
    EVIDENCE.mkdir(exist_ok=True)
    path.write_text("\n".join(log.lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\nEvidence written to {path.relative_to(manifests.REPO_ROOT).as_posix()}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
