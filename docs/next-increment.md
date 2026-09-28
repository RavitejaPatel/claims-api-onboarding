# Next increment: what to standardize after the first onboarding

Task 5 of the brief. `claims-api` is one service. Most of what was built here is not
specific to it, but turning it into a platform capability too early would mean
generalizing from a sample of one. This proposes what to standardize, in what order, and
the evidence that should trigger each investment.

## What is already reusable

| Built for claims-api | Service-specific part | Reusable part |
| --- | --- | --- |
| Kustomize base and overlays | Name, port, health paths, config keys, database egress | Probe pattern, rollout settings, security context, PDB, default-deny policy, ingress defaults |
| Contract checks and drift test | Expected hostnames and config keys | Pinned image, probes, security, no inline secrets, drift between environments |
| Delivery workflows | Repository names, image name | Validate-on-PR, digest pin by pull request, promotion by copying a digest, trust rules |
| Alert rules and runbook | Thresholds, contacts | Kubernetes-level alerts, runbook structure, rollback procedure |

## Proposed order

### 1. A service onboarding template (after the second onboarding)

Turn the base into a small set of inputs (service name, port, health and readiness paths,
config keys, database address) that generates the base, overlays, Argo CD Applications,
alert rules and a runbook skeleton. A shared Kustomize component, or a repository
template, is enough to start; a portal template can come later.

**Evidence that justifies it:** the second onboarding copies more than about 80% of these
files unchanged, and the time from request to a working dev environment is dominated by
copying and adapting YAML rather than by customer-specific questions.

### 2. Move contract checks into the platform (after three services)

The checks in `tests/contract_checks.py` (pinned image, probes, non-root, no inline
secrets, explicit ingress host) belong at the platform level, as admission policy in the
cluster and as a shared CI check, so every service gets them without copying test code.
Keep service-specific checks (hostnames, config keys) in each repository.

**Evidence:** the same checks are copied into three or more repositories, or a platform
review finds a violation that a shared policy would have blocked.

### 3. A reusable release workflow (after three services)

Publish the release-to-GitOps-PR job as a reusable GitHub workflow, with the GitHub App,
environment names and trust rules built in. Service repositories call it with an image
name and overlay path instead of carrying their own copy.

**Evidence:** three copies of `app-repo-release.yml` exist and have started to diverge,
or a trust-rule fix had to be applied in several repositories.

### 4. Standard secret delivery (when the platform documents it)

Replace "reference an existing Secret" with the platform's external-secret integration as
a documented, tested pattern, including rotation that restarts pods automatically.

**Evidence:** secret handoffs or rotations regularly need manual coordination or cause
incidents (for example, a rotated password with pods still on the old value).

### 5. Promotion gated on health (when promotion volume grows)

Promote to stage only after dev has been healthy for an agreed window, with that check
done automatically rather than by a person reading dashboards. Keep human approval for
stage until the gate has proven itself.

**Evidence:** several promotions a week per service, dev-to-stage lead time dominated by
waiting for a human check, or a bad release promoted despite dev alerts.

### 6. Application SLO alerts from a template (after Q11 for several services)

Once services expose consistent request, error and latency metrics, generate error-rate
and latency alerts from a declared objective instead of hand-writing them per service.

**Evidence:** alert rules differ between services only in names and thresholds, and
on-call reports noisy or missing application alerts.

## What to measure from now on

These numbers decide whether and when each step above is worth it:

| Measure | Why |
| --- | --- |
| Time from onboarding request to first healthy dev deployment | Main signal for the template (step 1) |
| Share of files copied unchanged between onboardings | How much is really generic |
| Deployments and promotions per week; dev-to-stage lead time | Signals for steps 3 and 5 |
| Rollbacks, and failed or stuck rollouts | Whether release safety needs more automation |
| Platform-review findings per onboarding | Signal for step 2 |
| Secret-related incidents or manual steps | Signal for step 4 |

## What not to standardize yet

- A single promotion model for every team: other customers may need different approval
  rules. Learn from two or three first.
- Application-level alert thresholds: they depend on each service's traffic.
- Autoscaling defaults: there is no traffic data yet (A7).
