"""Scan every text file in the repository for credential markers.

A committed secret is a hard fail for this exercise, so this runs on the whole
repository, including docs and evidence. Marker strings are assembled at runtime so
this file does not trip its own scan (or anyone else's).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules"}

DASHES = "-" * 5
PATTERNS = (
    ("PEM private key", re.compile(DASHES + r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY" + DASHES)),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("Kubernetes client key", re.compile(r"(?im)^\s*client-key-data\s*:")),
    ("password inside a database URL", re.compile(r"(?i)(?:postgres(?:ql)?|mysql)://[^/\s:@]+:[^/\s@]+@")),
    # Stops at the next `---` so a later ConfigMap's `data:` is not mistaken for Secret data.
    ("Kubernetes Secret with inline data",
     re.compile(r"(?ms)^kind:\s*Secret\s*$(?:(?!^---).)*?^(?:data|stringData):")),
)


def scan_text(text: str) -> list[str]:
    return [label for label, pattern in PATTERNS if pattern.search(text)]


def scan_repo(root: Path = REPO_ROOT) -> list[str]:
    findings = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIP_DIRS.intersection(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary file
        for label in scan_text(text):
            findings.append(f"{label} in {path.relative_to(root).as_posix()}")
    return findings
