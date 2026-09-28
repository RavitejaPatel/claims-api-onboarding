#!/usr/bin/env python3
"""Pin the claims-api image in one overlay to an immutable digest.

Used by the delivery pipeline:
  - the customer's release workflow pins a newly pushed image in the dev overlay;
  - the promotion workflow copies the digest running in dev into the stage overlay.

`kustomize edit set image` does the same job but rewrites the whole kustomization file and
drops the comments that explain the overlay. This changes exactly one line instead, so the
pull request diff is a single, reviewable digest change.

Usage:
  python solution/ci/set_image_digest.py --env dev --digest sha256:<64 hex characters>
  python solution/ci/set_image_digest.py --env stage --from-env dev

When run inside GitHub Actions it also writes `changed`, `digest` and `short` outputs.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAYS = REPO_ROOT / "solution" / "k8s" / "overlays"
ENVIRONMENTS = ("dev", "stage")

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_LINE = re.compile(r"^(?P<prefix>[ \t]*digest:[ \t]*)(?P<digest>sha256:[0-9a-f]{64})[ \t]*$", re.M)


def overlay_file(env: str, overlays: Path = OVERLAYS) -> Path:
    return overlays / env / "kustomization.yaml"


def read_digest(path: Path) -> str:
    matches = DIGEST_LINE.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one image digest line in {path}, found {len(matches)}")
    return matches[0][1]


def set_digest(path: Path, digest: str) -> bool:
    """Replace the digest line in `path`. Returns True if the file changed."""
    if not DIGEST.match(digest):
        raise ValueError(f"not an immutable sha256 digest: {digest!r}")
    text = path.read_text(encoding="utf-8")
    if len(DIGEST_LINE.findall(text)) != 1:
        raise ValueError(f"expected exactly one image digest line in {path}")
    updated = DIGEST_LINE.sub(lambda m: m.group("prefix") + digest, text)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def write_github_outputs(**values: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True, choices=ENVIRONMENTS, help="overlay to update")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--digest", help="new digest, sha256:<64 hex characters>")
    source.add_argument("--from-env", choices=ENVIRONMENTS, help="copy the digest pinned in this overlay")
    args = parser.parse_args(argv)

    try:
        if args.from_env == args.env:
            raise ValueError("--from-env must be a different environment")
        digest = args.digest or read_digest(overlay_file(args.from_env))
        target = overlay_file(args.env)
        before = read_digest(target)
        changed = set_digest(target, digest)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    short = digest.split(":", 1)[1][:12]
    if changed:
        print(f"{args.env}: {before} -> {digest}")
    else:
        print(f"{args.env}: already pinned to {digest}; nothing to change")
    write_github_outputs(changed=str(changed).lower(), digest=digest, short=short)
    return 0


if __name__ == "__main__":
    sys.exit(main())
