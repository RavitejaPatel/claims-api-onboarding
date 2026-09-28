"""Render the Kustomize overlays and load the result for checking.

Used by both validate.py and test_contract.py so they always check the same output.
Works on Windows, macOS and Linux. Needs `kustomize` (or `kubectl`) on PATH and PyYAML.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - friendly message for a fresh machine
    raise SystemExit("PyYAML is not installed. Run: python -m pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = REPO_ROOT / "solution" / "k8s" / "overlays"
ENVIRONMENTS = ("dev", "stage")


def kustomize_command() -> list[str]:
    """Prefer a standalone kustomize binary; fall back to `kubectl kustomize`.

    kubectl bundles its own (often older) kustomize, so the standalone v5.4+ binary is
    recommended: the base uses the `labels.includeTemplates` field.
    """
    exe = shutil.which("kustomize")
    if exe:
        return [exe, "build"]
    exe = shutil.which("kubectl")
    if exe:
        return [exe, "kustomize"]
    raise RuntimeError(
        "Neither `kustomize` nor `kubectl` was found on PATH. "
        "Install kustomize: https://github.com/kubernetes-sigs/kustomize/releases"
    )


def kustomize_version_command() -> list[str]:
    cmd = kustomize_command()
    if cmd[1] == "kustomize":  # kubectl fallback: never contact a cluster
        return [cmd[0], "version", "--client"]
    return [cmd[0], "version"]


def render_text(env: str) -> str:
    """Return the rendered YAML for one environment as text."""
    result = subprocess.run(
        [*kustomize_command(), str(OVERLAYS / env)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout


def load(text: str) -> list[dict]:
    """Parse a multi-document YAML string into a list of resources."""
    return [doc for doc in yaml.safe_load_all(text) if doc]


def render(env: str) -> list[dict]:
    return load(render_text(env))
