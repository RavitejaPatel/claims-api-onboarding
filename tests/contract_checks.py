"""Contract checks for the rendered claims-api manifests.

Each check takes the rendered resources for one environment and returns a list of
problems. An empty list means the check passed. Every rule traces back to an input:
  brief    = inputs/candidate-brief.md
  notes    = inputs/starter-pack/application-notes.md
  platform = inputs/starter-pack/platform-contract.md
  request  = inputs/starter-pack/customer-request.md
  eng      = docs/engagement.md (our assumptions and decisions)
"""

from __future__ import annotations

import copy
import json
import re

APP = "claims-api"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


# --- helpers ---------------------------------------------------------------------------

def one(docs: list[dict], kind: str, name: str | None = None) -> dict:
    matches = [
        d for d in docs
        if d.get("kind") == kind and (name is None or d["metadata"]["name"] == name)
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one {kind} {name or ''}, found {len(matches)}")
    return matches[0]


def app_container(docs: list[dict]) -> dict:
    return one(docs, "Deployment", APP)["spec"]["template"]["spec"]["containers"][0]


def expected_host(env: str) -> str:
    return f"{APP}.{env}.apps.example.invalid"  # request


# --- checks ----------------------------------------------------------------------------

def check_namespace(docs: list[dict], env: str) -> list[str]:
    """platform: each environment runs in a dedicated namespace (eng A1)."""
    want = f"{APP}-{env}"
    return [
        f"{d['kind']}/{d['metadata']['name']} is in namespace "
        f"{d['metadata'].get('namespace')!r}, expected {want!r}"
        for d in docs if d["metadata"].get("namespace") != want
    ]


def check_image_pinned(docs: list[dict], env: str) -> list[str]:
    """platform: immutable digest or pinned version; `latest` is rejected."""
    problems = []
    for d in docs:
        pod = d.get("spec", {}).get("template", {}).get("spec", {})
        for c in pod.get("containers", []) + pod.get("initContainers", []):
            image = c.get("image", "")
            if not DIGEST.search(image):
                problems.append(f"container {c['name']} image {image!r} is not pinned by sha256 digest")
            if image.endswith(":latest") or ":latest@" in image:
                problems.append(f"container {c['name']} uses the mutable latest tag")
    return problems


def check_probes_and_port(docs: list[dict], env: str) -> list[str]:
    """notes/brief: port 8080; liveness = process health, readiness = database."""
    c = app_container(docs)
    problems = []
    ports = {p.get("name"): p.get("containerPort") for p in c.get("ports", [])}
    if ports.get("http") != 8080:
        problems.append(f"expected a port named http on 8080, found {ports}")
    wanted = {"livenessProbe": "/healthz", "readinessProbe": "/readyz", "startupProbe": "/healthz"}
    for probe, path in wanted.items():
        got = c.get(probe, {}).get("httpGet", {}).get("path")
        if got != path:
            problems.append(f"{probe} path is {got!r}, expected {path!r}")
    if c.get("livenessProbe", {}).get("httpGet", {}).get("path") == "/readyz":
        problems.append("liveness must not depend on the database (/readyz)")
    return problems


def check_rollout(docs: list[dict], env: str) -> list[str]:
    """notes: zero-downtime rolling deploys; never drop all capacity."""
    spec = one(docs, "Deployment", APP)["spec"]
    problems = []
    if spec.get("replicas", 1) < 2:
        problems.append(f"replicas is {spec.get('replicas')}, need at least 2 for zero downtime")
    strategy = spec.get("strategy", {})
    rolling = strategy.get("rollingUpdate", {})
    if strategy.get("type") != "RollingUpdate":
        problems.append("deployment strategy must be RollingUpdate")
    if rolling.get("maxUnavailable") not in (0, "0", "0%"):
        problems.append(f"maxUnavailable is {rolling.get('maxUnavailable')!r}, expected 0")
    if rolling.get("maxSurge") in (None, 0, "0", "0%"):
        problems.append("maxSurge must be at least 1 so a rollout can make progress")
    pdb = one(docs, "PodDisruptionBudget", APP)["spec"]
    if pdb.get("minAvailable", 0) < 1:
        problems.append("PodDisruptionBudget must keep at least one pod available")
    return problems


def check_resources(docs: list[dict], env: str) -> list[str]:
    """brief: resource policy."""
    res = app_container(docs).get("resources", {})
    return [
        f"missing resources.{kind}.{name}"
        for kind in ("requests", "limits")
        for name in ("cpu", "memory")
        if name not in res.get(kind, {})
    ]


def check_security_context(docs: list[dict], env: str) -> list[str]:
    """Least privilege: non-root, no escalation, read-only root, no API token (eng section 5)."""
    pod = one(docs, "Deployment", APP)["spec"]["template"]["spec"]
    c = app_container(docs)
    sc = c.get("securityContext", {})
    problems = []
    if not pod.get("securityContext", {}).get("runAsNonRoot"):
        problems.append("pod must set runAsNonRoot: true")
    if sc.get("allowPrivilegeEscalation") is not False:
        problems.append("container must set allowPrivilegeEscalation: false")
    if sc.get("readOnlyRootFilesystem") is not True:
        problems.append("container must set readOnlyRootFilesystem: true")
    if "ALL" not in sc.get("capabilities", {}).get("drop", []):
        problems.append("container must drop ALL capabilities")
    if sc.get("privileged"):
        problems.append("container must not be privileged")
    if pod.get("serviceAccountName") in (None, "default"):
        problems.append("pod must use a dedicated service account")
    if pod.get("automountServiceAccountToken") is not False:
        problems.append("pod must not mount a Kubernetes API token")
    if any(d["kind"] in ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding") for d in docs):
        problems.append("no RBAC should be granted; the app does not call the Kubernetes API")
    return problems


def check_config_and_secret(docs: list[dict], env: str) -> list[str]:
    """notes: LOG_LEVEL, PUBLIC_MODE from config; DATABASE_URL only by Secret reference."""
    c = app_container(docs)
    problems = []
    if any(d["kind"] == "Secret" for d in docs):
        problems.append("a Secret object is rendered; secret values must be supplied out of band")
    cm_refs = [e["configMapRef"]["name"] for e in c.get("envFrom", []) if "configMapRef" in e]
    config_maps = {d["metadata"]["name"]: d for d in docs if d["kind"] == "ConfigMap"}
    data = {}
    for ref in cm_refs:
        if ref not in config_maps:
            problems.append(f"envFrom references missing ConfigMap {ref!r}")
        else:
            data.update(config_maps[ref].get("data", {}))
    for key in ("LOG_LEVEL", "PUBLIC_MODE"):
        if key not in data:
            problems.append(f"required config {key} is not provided")
    env_vars = {e["name"]: e for e in c.get("env", [])}
    db = env_vars.get("DATABASE_URL")
    if db is None:
        problems.append("DATABASE_URL is not set")
    elif "value" in db or "secretKeyRef" not in db.get("valueFrom", {}):
        problems.append("DATABASE_URL must come from a secretKeyRef, never a literal value")
    if "DATABASE_URL" in data:
        problems.append("DATABASE_URL must not be in a ConfigMap")
    return problems


def check_ingress(docs: list[dict], env: str) -> list[str]:
    """brief/platform/request: TLS, explicit hostname, no admin endpoint; eng A4 internal-only."""
    ing = one(docs, "Ingress", APP)
    spec = ing["spec"]
    annotations = ing["metadata"].get("annotations", {})
    want = expected_host(env)
    problems = []
    rule_hosts = [r.get("host") for r in spec.get("rules", [])]
    tls_hosts = [h for t in spec.get("tls", []) for h in t.get("hosts", [])]
    if rule_hosts != [want]:
        problems.append(f"rule hosts are {rule_hosts}, expected [{want!r}]")
    if tls_hosts != [want]:
        problems.append(f"TLS hosts are {tls_hosts}, expected [{want!r}]")
    if any("*" in (h or "") for h in rule_hosts + tls_hosts):
        problems.append("wildcard hostnames are not allowed")
    if annotations.get("alb.ingress.kubernetes.io/scheme") != "internal":
        problems.append("load balancer must stay internal until auth and rate limiting are confirmed (eng A4, Q1, Q2)")
    listeners = json.loads(annotations.get("alb.ingress.kubernetes.io/listen-ports", "[]"))
    if listeners != [{"HTTPS": 443}]:
        problems.append(f"listeners are {listeners}, expected HTTPS 443 only")
    for rule in spec.get("rules", []):
        for path in rule.get("http", {}).get("paths", []):
            if "admin" in path.get("path", "").lower():
                problems.append(f"admin path {path['path']!r} must not be exposed")
    return problems


def check_service_wiring(docs: list[dict], env: str) -> list[str]:
    """Service and PodDisruptionBudget must select the claims-api pods."""
    labels = one(docs, "Deployment", APP)["spec"]["template"]["metadata"]["labels"]
    problems = []
    svc = one(docs, "Service", APP)["spec"]
    selector = svc.get("selector", {})
    if not selector or any(labels.get(k) != v for k, v in selector.items()):
        problems.append(f"Service selector {selector} does not match pod labels")
    if svc.get("ports", [{}])[0].get("targetPort") != "http":
        problems.append("Service must target the named http port")
    pdb_sel = one(docs, "PodDisruptionBudget", APP)["spec"].get("selector", {}).get("matchLabels", {})
    if not pdb_sel or any(labels.get(k) != v for k, v in pdb_sel.items()):
        problems.append(f"PodDisruptionBudget selector {pdb_sel} does not match pod labels")
    return problems


def check_network_policy(docs: list[dict], env: str) -> list[str]:
    """platform: default-deny; database egress described; no arbitrary internet egress."""
    problems = []
    deny = one(docs, "NetworkPolicy", "default-deny-all")["spec"]
    if deny.get("podSelector") != {} or sorted(deny.get("policyTypes", [])) != ["Egress", "Ingress"]:
        problems.append("default-deny-all must select all pods for Ingress and Egress")
    if deny.get("ingress") or deny.get("egress"):
        problems.append("default-deny-all must not allow any traffic")
    app = one(docs, "NetworkPolicy", APP)["spec"]
    for rule in app.get("egress", []):
        if not rule.get("to"):
            problems.append("an egress rule without `to` allows traffic to anywhere")
        for peer in rule.get("to", []):
            cidr = peer.get("ipBlock", {}).get("cidr")
            if cidr and not cidr.endswith("/32"):
                problems.append(f"egress to {cidr} is broader than a single database address")
            if cidr in ("0.0.0.0/0", "::/0"):
                problems.append("egress to the whole internet is not allowed")
        ports = {(p.get("protocol"), p.get("port")) for p in rule.get("ports", [])}
        if not ports:
            problems.append("every egress rule must be restricted to specific ports")
        if ports - {("UDP", 53), ("TCP", 53), ("TCP", 5432)}:
            problems.append(f"unexpected egress ports {sorted(ports)}")
    for rule in app.get("ingress", []):
        ports = {(p.get("protocol"), p.get("port")) for p in rule.get("ports", [])}
        if ports != {("TCP", 8080)}:
            problems.append(f"ingress must be limited to TCP 8080, found {sorted(ports)}")
    return problems


ALL_CHECKS = (
    check_namespace,
    check_image_pinned,
    check_probes_and_port,
    check_rollout,
    check_resources,
    check_security_context,
    check_config_and_secret,
    check_ingress,
    check_service_wiring,
    check_network_policy,
)


# --- environment drift -----------------------------------------------------------------

def _strip_allowed(doc: dict) -> dict:
    """Remove the fields an overlay is allowed to change (eng section 5)."""
    d = copy.deepcopy(doc)
    meta = d["metadata"]
    meta.pop("namespace", None)
    meta.get("labels", {}).pop("app.kubernetes.io/environment", None)
    if d["kind"] == "ConfigMap":
        meta["name"] = meta["name"].rsplit("-", 1)[0]  # generated hash suffix
        for key in ("LOG_LEVEL", "PUBLIC_MODE"):
            d.get("data", {}).pop(key, None)
    if d["kind"] == "Deployment":
        d["spec"].pop("replicas", None)
        tmpl = d["spec"]["template"]
        tmpl["metadata"].get("labels", {}).pop("app.kubernetes.io/environment", None)
        for c in tmpl["spec"]["containers"]:
            c["image"] = c["image"].split("@")[0]
            for e in c.get("envFrom", []):
                if "configMapRef" in e:
                    e["configMapRef"]["name"] = e["configMapRef"]["name"].rsplit("-", 1)[0]
    if d["kind"] == "Ingress":
        for rule in d["spec"].get("rules", []):
            rule.pop("host", None)
        for tls in d["spec"].get("tls", []):
            tls.pop("hosts", None)
    if d["kind"] == "NetworkPolicy":
        for rule in d["spec"].get("egress", []):
            for peer in rule.get("to", []):
                peer.get("ipBlock", {}).pop("cidr", None)
    return d


def check_drift(dev: list[dict], stage: list[dict]) -> list[str]:
    """brief: dev and stage differ only through reviewed overlay configuration."""
    def index(docs):
        return {(d["kind"], _strip_allowed(d)["metadata"]["name"]): _strip_allowed(d) for d in docs}

    a, b = index(dev), index(stage)
    problems = [f"{k[0]}/{k[1]} exists only in dev" for k in a.keys() - b.keys()]
    problems += [f"{k[0]}/{k[1]} exists only in stage" for k in b.keys() - a.keys()]
    for key in sorted(a.keys() & b.keys()):
        for path in _differences(a[key], b[key]):
            problems.append(f"{key[0]}/{key[1]} field {path} differs between dev and stage")
    return problems


def _differences(a, b, path: str = "") -> list[str]:
    """Paths (like spec.template.spec.containers[0].resources) where two values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(a.keys() | b.keys()):
            out += _differences(a.get(k), b.get(k), f"{path}.{k}" if path else k)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _differences(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [path or "(document)"]


def run_all(docs: list[dict], env: str) -> dict[str, list[str]]:
    results = {}
    for check in ALL_CHECKS:
        try:
            results[check.__name__] = check(docs, env)
        except (AssertionError, KeyError, IndexError, TypeError) as error:
            results[check.__name__] = [f"could not evaluate: {error}"]
    return results
