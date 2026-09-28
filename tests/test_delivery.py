"""Tests for the delivery path: digest pinning, Argo CD wiring, and workflow trust rules.

Run: python -m unittest discover -s tests -v   (also runs as part of tests/validate.py)
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "solution" / "ci"))

import set_image_digest as pin  # noqa: E402

WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
APP_REPO_WORKFLOW = REPO_ROOT / "solution" / "ci" / "app-repo-release.yml"
ALL_WORKFLOWS = WORKFLOWS + [APP_REPO_WORKFLOW]
SETUP_TOOLS = REPO_ROOT / ".github" / "actions" / "setup-tools" / "action.yml"
PINNED_ACTION = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    value = workflow.get("on", workflow.get(True))
    return value if isinstance(value, dict) else {name: None for name in ([value] if isinstance(value, str) else value)}


def uses_steps(path: Path) -> list[str]:
    doc = load_yaml(path)
    steps = []
    if "jobs" in doc:
        for job in doc["jobs"].values():
            steps += [s["uses"] for s in job.get("steps", []) if "uses" in s]
    else:  # composite action
        steps += [s["uses"] for s in doc["runs"].get("steps", []) if "uses" in s]
    return steps


class DigestPinning(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        for env in pin.ENVIRONMENTS:
            target = self.tmp / env
            target.mkdir()
            shutil.copy(pin.overlay_file(env), target / "kustomization.yaml")

    def file(self, env: str) -> Path:
        return pin.overlay_file(env, self.tmp)

    def test_changes_only_the_digest_line(self) -> None:
        before = self.file("dev").read_text(encoding="utf-8").splitlines()
        self.assertTrue(pin.set_digest(self.file("dev"), DIGEST_A))
        after = self.file("dev").read_text(encoding="utf-8").splitlines()
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(len(before), len(after), "line count changed; comments may have been lost")
        self.assertEqual(len(changed), 1, changed)
        self.assertEqual(changed[0][1].strip(), f"digest: {DIGEST_A}")

    def test_same_digest_is_a_no_op(self) -> None:
        current = pin.read_digest(self.file("dev"))
        self.assertFalse(pin.set_digest(self.file("dev"), current))

    def test_rejects_anything_but_a_sha256_digest(self) -> None:
        for bad in ("1.4.2", "sha256:abc", "latest", DIGEST_A.upper(), DIGEST_A + " "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pin.set_digest(self.file("dev"), bad)

    def test_promotion_copies_dev_digest_to_stage(self) -> None:
        pin.set_digest(self.file("dev"), DIGEST_B)
        pin.set_digest(self.file("stage"), pin.read_digest(self.file("dev")))
        self.assertEqual(pin.read_digest(self.file("stage")), DIGEST_B)

    def test_refuses_an_overlay_with_two_digests(self) -> None:
        path = self.file("dev")
        path.write_text(path.read_text(encoding="utf-8") + f"# extra\n    digest: {DIGEST_A}\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            pin.set_digest(path, DIGEST_B)


class ArgoApplications(unittest.TestCase):
    def test_each_environment_points_at_its_own_overlay_and_namespace(self) -> None:
        for env in pin.ENVIRONMENTS:
            with self.subTest(env=env):
                app = load_yaml(REPO_ROOT / "solution" / "argocd" / f"claims-api-{env}.yaml")
                spec = app["spec"]
                self.assertEqual(app["kind"], "Application")
                self.assertEqual(spec["source"]["path"], f"solution/k8s/overlays/{env}")
                self.assertTrue((REPO_ROOT / spec["source"]["path"] / "kustomization.yaml").is_file())
                overlay = load_yaml(pin.overlay_file(env))
                self.assertEqual(spec["destination"]["namespace"], overlay["namespace"])
                self.assertEqual(spec["source"]["targetRevision"], "main")
                self.assertTrue(spec["syncPolicy"]["automated"]["selfHeal"])
                self.assertIn("CreateNamespace=false", spec["syncPolicy"]["syncOptions"])


class WorkflowTrustBoundary(unittest.TestCase):
    def test_workflows_exist(self) -> None:
        names = {p.name for p in WORKFLOWS}
        self.assertEqual(names, {"validate.yml", "promote-to-stage.yml"})
        self.assertTrue(APP_REPO_WORKFLOW.is_file())

    def test_third_party_actions_are_pinned_to_a_commit(self) -> None:
        for path in ALL_WORKFLOWS + [SETUP_TOOLS]:
            for ref in uses_steps(path):
                if ref.startswith("./"):
                    continue  # local action from this repository
                with self.subTest(file=path.name, uses=ref):
                    self.assertRegex(ref, PINNED_ACTION)

    def test_default_token_is_read_only(self) -> None:
        for path in ALL_WORKFLOWS:
            with self.subTest(file=path.name):
                self.assertEqual(load_yaml(path).get("permissions"), {"contents": "read"})
                for name, job in load_yaml(path)["jobs"].items():
                    self.assertNotIn("permissions", job, f"job {name} widens token permissions")

    def test_no_privileged_pull_request_triggers(self) -> None:
        for path in ALL_WORKFLOWS:
            with self.subTest(file=path.name):
                self.assertNotIn("pull_request_target", triggers(load_yaml(path)))
                self.assertNotIn("workflow_run", triggers(load_yaml(path)))

    def test_pull_request_workflow_uses_no_secrets(self) -> None:
        text = (REPO_ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request", triggers(yaml.safe_load(text)))
        self.assertNotIn("secrets.", text)

    def test_jobs_with_secrets_run_only_after_merge_and_inside_an_environment(self) -> None:
        for path in ALL_WORKFLOWS:
            doc = load_yaml(path)
            on = triggers(doc)
            for name, job in doc["jobs"].items():
                if "secrets." not in yaml.safe_dump(job):
                    continue
                with self.subTest(file=path.name, job=name):
                    self.assertNotIn("pull_request", on)
                    self.assertIn("environment", job)

    def test_checkout_does_not_leave_credentials_behind(self) -> None:
        for path in ALL_WORKFLOWS:
            for job in load_yaml(path)["jobs"].values():
                for step in job.get("steps", []):
                    if step.get("uses", "").startswith("actions/checkout@"):
                        with self.subTest(file=path.name):
                            self.assertIs(step.get("with", {}).get("persist-credentials"), False)

    def test_tool_downloads_are_checksum_verified(self) -> None:
        text = SETUP_TOOLS.read_text(encoding="utf-8")
        downloads = re.findall(r'fetch "https://', text)
        checksums = re.findall(r"\b[0-9a-f]{64}\b", text)
        self.assertEqual(len(downloads), 3)
        self.assertEqual(len(checksums), len(downloads))
        self.assertIn("sha256sum -c", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
