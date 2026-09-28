"""Contract tests for claims-api.

Two kinds of tests:
1. The real rendered dev and stage manifests pass every contract check.
2. Each check actually catches the mistake it exists for. We break a copy of the real
   manifests on purpose and expect the check to fail, so a passing run means something.

Run: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_checks as cc  # noqa: E402
import manifests  # noqa: E402
import secret_scan  # noqa: E402

RENDERED: dict[str, list[dict]] = {}


def setUpModule() -> None:
    for env in manifests.ENVIRONMENTS:
        RENDERED[env] = manifests.render(env)


def broken(env: str) -> list[dict]:
    """A fresh copy of the real manifests that a test may mutate."""
    return copy.deepcopy(RENDERED[env])


def deployment(docs):
    return cc.one(docs, "Deployment", cc.APP)


class RealManifestsPass(unittest.TestCase):
    def test_every_check_passes_for_every_environment(self) -> None:
        for env in manifests.ENVIRONMENTS:
            for name, problems in cc.run_all(RENDERED[env], env).items():
                with self.subTest(env=env, check=name):
                    self.assertEqual(problems, [])

    def test_dev_and_stage_differ_only_in_approved_fields(self) -> None:
        self.assertEqual(cc.check_drift(RENDERED["dev"], RENDERED["stage"]), [])

    def test_repository_contains_no_credentials(self) -> None:
        self.assertEqual(secret_scan.scan_repo(), [])


class ChecksCatchMistakes(unittest.TestCase):
    def assertCaught(self, check, docs, env="dev") -> None:
        self.assertNotEqual(check(docs, env), [], f"{check.__name__} missed the problem")

    def test_unpinned_image(self) -> None:
        docs = broken("dev")
        container = deployment(docs)["spec"]["template"]["spec"]["containers"][0]
        container["image"] = "registry.example.invalid/claims-api:" + "latest"
        self.assertCaught(cc.check_image_pinned, docs)

    def test_liveness_on_database_endpoint(self) -> None:
        docs = broken("dev")
        container = deployment(docs)["spec"]["template"]["spec"]["containers"][0]
        container["livenessProbe"]["httpGet"]["path"] = "/readyz"
        self.assertCaught(cc.check_probes_and_port, docs)

    def test_rollout_that_can_drop_capacity(self) -> None:
        docs = broken("dev")
        deployment(docs)["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] = 1
        self.assertCaught(cc.check_rollout, docs)

    def test_single_replica(self) -> None:
        docs = broken("dev")
        deployment(docs)["spec"]["replicas"] = 1
        self.assertCaught(cc.check_rollout, docs)

    def test_missing_memory_limit(self) -> None:
        docs = broken("dev")
        container = deployment(docs)["spec"]["template"]["spec"]["containers"][0]
        del container["resources"]["limits"]["memory"]
        self.assertCaught(cc.check_resources, docs)

    def test_privilege_escalation(self) -> None:
        docs = broken("dev")
        container = deployment(docs)["spec"]["template"]["spec"]["containers"][0]
        container["securityContext"]["allowPrivilegeEscalation"] = True
        self.assertCaught(cc.check_security_context, docs)

    def test_database_url_as_literal_value(self) -> None:
        docs = broken("dev")
        container = deployment(docs)["spec"]["template"]["spec"]["containers"][0]
        container["env"] = [{"name": "DATABASE_URL", "value": "placeholder"}]
        self.assertCaught(cc.check_config_and_secret, docs)

    def test_secret_object_committed(self) -> None:
        docs = broken("dev")
        docs.append({"kind": "Secret", "metadata": {"name": "claims-api-db", "namespace": "claims-api-dev"}})
        self.assertCaught(cc.check_config_and_secret, docs)

    def test_public_load_balancer(self) -> None:
        docs = broken("dev")
        ingress = cc.one(docs, "Ingress", cc.APP)
        ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/scheme"] = "internet-facing"
        self.assertCaught(cc.check_ingress, docs)

    def test_wildcard_host(self) -> None:
        docs = broken("dev")
        cc.one(docs, "Ingress", cc.APP)["spec"]["rules"][0]["host"] = "*.apps.example.invalid"
        self.assertCaught(cc.check_ingress, docs)

    def test_plain_http_listener(self) -> None:
        docs = broken("dev")
        annotations = cc.one(docs, "Ingress", cc.APP)["metadata"]["annotations"]
        annotations["alb.ingress.kubernetes.io/listen-ports"] = '[{"HTTP": 80}, {"HTTPS": 443}]'
        self.assertCaught(cc.check_ingress, docs)

    def test_admin_path_exposed(self) -> None:
        docs = broken("dev")
        paths = cc.one(docs, "Ingress", cc.APP)["spec"]["rules"][0]["http"]["paths"]
        paths.append({"path": "/admin", "pathType": "Prefix", "backend": paths[0]["backend"]})
        self.assertCaught(cc.check_ingress, docs)

    def test_overlay_forgot_hostname(self) -> None:
        docs = broken("stage")
        self.assertCaught(cc.check_ingress, docs, env="dev")

    def test_egress_to_internet(self) -> None:
        docs = broken("dev")
        egress = cc.one(docs, "NetworkPolicy", cc.APP)["spec"]["egress"]
        egress.append({"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}], "ports": [{"protocol": "TCP", "port": 443}]})
        self.assertCaught(cc.check_network_policy, docs)

    def test_service_selector_mismatch(self) -> None:
        docs = broken("dev")
        cc.one(docs, "Service", cc.APP)["spec"]["selector"] = {"app.kubernetes.io/name": "other"}
        self.assertCaught(cc.check_service_wiring, docs)

    def test_wrong_namespace(self) -> None:
        self.assertCaught(cc.check_namespace, broken("stage"), env="dev")

    def test_drift_outside_overlay_fields(self) -> None:
        stage = broken("stage")
        container = deployment(stage)["spec"]["template"]["spec"]["containers"][0]
        container["resources"]["limits"]["memory"] = "2Gi"
        problems = cc.check_drift(RENDERED["dev"], stage)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("resources.limits.memory", problems[0])

    def test_secret_scanner_detects_credentials(self) -> None:
        scheme = "postgres" + "ql://"
        fake = scheme + "claims" + ":" + "not-a-real-password" + "@db.example.invalid/claims"
        self.assertIn("password inside a database URL", secret_scan.scan_text(fake))
        key = "-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5
        self.assertIn("PEM private key", secret_scan.scan_text(key))

    def test_secret_scanner_flags_inline_secret_but_not_a_later_configmap(self) -> None:
        label = "Kubernetes Secret with inline data"
        inline = "kind: Secret\nmetadata:\n  name: x\nstringData:\n  k: v\n"
        self.assertIn(label, secret_scan.scan_text(inline))
        separate = "kind: Secret\nmetadata:\n  name: x\n---\nkind: ConfigMap\ndata:\n  k: v\n"
        self.assertNotIn(label, secret_scan.scan_text(separate))


if __name__ == "__main__":
    unittest.main(verbosity=2)
