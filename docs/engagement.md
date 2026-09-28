# Engagement: onboarding `claims-api` to the shared platform

This document shapes the engagement before any manifests are written. It separates what
the inputs actually say (facts) from what I am assuming, lists the questions I would take
back to the customer, and records the defaults I chose so the work can keep moving.

Sources: `inputs/candidate-brief.md`, `inputs/starter-pack/customer-request.md`,
`inputs/starter-pack/application-notes.md`, `inputs/starter-pack/platform-contract.md`.

## 1. What the customer is asking for

> "Give us a URL for the API, make deploys automatic, keep the database password safe,
> and tell us what to do when it is unhealthy. We need dev this week and stage next
> week. We do not want to maintain a separate set of manifests for every environment."

Translated into outcomes:

| Customer outcome | What it means for this integration |
| --- | --- |
| A URL for the API | An explicit TLS hostname per environment through a reviewed Ingress |
| Automatic deploys | A new pinned image reaches dev without a human editing YAML; stage is a reviewed promotion |
| Password kept safe | `DATABASE_URL` is referenced from a platform-delivered Secret, never stored in Git or CI |
| Know what to do when unhealthy | Probes, metrics/alert expectations, a runbook, and a clear ownership/escalation path |
| Dev this week, stage next week | Dev is the first milestone; stage reuses the same base with a small, reviewed overlay |
| No per-environment manifest copies | One Kustomize base, thin `dev` and `stage` overlays, and a check that they do not drift |

## 2. Facts (stated in the inputs)

| # | Fact | Source |
| --- | --- | --- |
| F1 | Environments are `dev` and `stage`, each in a dedicated namespace | platform-contract |
| F2 | Delivery is a pull request to the GitOps repository; Argo CD applies the approved result | platform-contract, brief |
| F3 | Kustomize bases and overlays are supported | platform-contract |
| F4 | Images must be pinned by digest or version; `latest` is rejected | platform-contract |
| F5 | Image is published by the customer to `registry.example.invalid/claims-api` | application-notes |
| F6 | App listens on TCP 8080 | application-notes, brief |
| F7 | `/healthz` = process health only; `/readyz` = database connectivity and schema compatibility; `/metrics` = Prometheus text | application-notes |
| F8 | Non-secret config: `LOG_LEVEL`, `PUBLIC_MODE`. Secret config: `DATABASE_URL` | application-notes |
| F9 | No admin HTTP route; admin actions are a CLI run by the customer team | application-notes |
| F10 | Customer expects zero-downtime rolling deploys for the pilot | application-notes |
| F11 | Hostname pattern: `claims-api.<environment>.apps.example.invalid` | customer-request |
| F12 | Database is an existing managed PostgreSQL; the password must be referenced, never stored in the repo | customer-request, brief |
| F13 | Secrets: reference an existing Secret or external-secret integration; values are supplied out of band by the platform team | platform-contract |
| F14 | Ingress: an AWS load balancer is provisioned from a reviewed Ingress; TLS certificates are platform-managed; hostname must be explicit | platform-contract |
| F15 | Default-deny networking is available; egress to the database must be described; no arbitrary internet egress | platform-contract |
| F16 | Observability: stdout/stderr logs, Prometheus metrics, shared Grafana/alerting | platform-contract |
| F17 | CI is GitHub Actions; deployment credentials are not available to pull requests from forks | platform-contract |
| F18 | Application team owns code and service behavior; platform team owns cluster primitives, ingress controllers, secret delivery, and shared alerting | platform-contract, brief |
| F19 | Public ingress needs TLS, an explicit hostname, and an explanation of authentication and rate limiting | brief |

## 3. Assumptions (to confirm with the customer or platform team)

Each assumption has the default I used and what changes if it is wrong.

| # | Assumption | Default used in this submission | If wrong |
| --- | --- | --- | --- |
| A1 | Namespace names follow `<service>-<env>` | `claims-api-dev`, `claims-api-stage` | Change one line per overlay |
| A2 | The platform team creates a Secret named `claims-api-db` with key `DATABASE_URL` in each namespace | Deployment references that Secret key; no Secret object is committed | Rename the reference, or add the platform's external-secret resource once its API is documented |
| A3 | The managed PostgreSQL endpoint is a known private address on port 5432 | NetworkPolicy egress uses a documentation placeholder address (`192.0.2.10/32`) that must be replaced | The platform team supplies the real CIDR; one overlay value changes |
| A4 | The API does not yet have confirmed caller authentication or rate limiting | Load balancer is internal-only in dev and stage until Q1/Q2 are answered; switching to internet-facing is a reviewed overlay change | If the customer confirms auth plus a rate-limit control, stage can go public via one reviewed change |
| A5 | The platform's ingress class and TLS attachment method are platform-defined | Use an `ingressClassName` and TLS host entry only; no controller-specific annotations beyond what is documented | Add the platform's documented annotations |
| A6 | Prometheus discovers targets through a platform convention that is not documented in the starter pack | Expose a named `http` port and document `/metrics`; the scrape integration is an explicit integration point | Add the platform's scrape resource once confirmed |
| A7 | Pilot traffic is low | 2 replicas per environment with conservative requests/limits, tuned from metrics | Raise replicas or add autoscaling after real traffic data |
| A8 | Schema migrations are run by the customer (their CLI), before or compatible with a new release | `/readyz` failing on schema mismatch stops a rollout safely (old pods keep serving) | Add a migration step to the release process |
| A9 | Dev may auto-merge bot image-bump PRs once checks pass; stage requires human approval | Dev: automated PR + required checks. Stage: promotion PR reviewed by the customer and a platform code owner | If auto-merge is not allowed, dev also needs one click to merge |

## 4. Open questions

At least these must be answered before public exposure or stage sign-off.

| # | Question | Ask | Blocks | Default until answered |
| --- | --- | --- | --- | --- |
| Q1 | How does the API authenticate callers (API keys, OAuth/OIDC, mTLS, or none)? What does `PUBLIC_MODE` change? | Customer | Public exposure | Internal-only load balancer (A4); `PUBLIC_MODE` value set per overlay and flagged |
| Q2 | What rate limit or abuse protection is expected, and does the platform offer one at the load balancer (for example WAF)? | Customer + platform | Public exposure | No public exposure; limit documented as a prerequisite |
| Q3 | What is the database endpoint/CIDR, and will the Secret be a plain Secret or an external-secret resource? | Platform | Dev go-live | Placeholder CIDR and Secret name (A2, A3) |
| Q4 | Who is on call for `claims-api` incidents, and what are the escalation paths to the platform team? | Customer + platform | Stage sign-off | Ownership split from F18; named contacts left as placeholders |
| Q5 | Expected traffic, latency, and availability targets for the pilot? | Customer | Alert thresholds | Starter alert thresholds, marked as tunable |
| Q6 | Does the API handle personal data in claims? Could it appear in logs? | Customer | Stage sign-off | Recommend no request bodies in logs; `LOG_LEVEL=info` in stage |
| Q7 | Where does the GitOps repository live, and may the customer's CI open PRs against it (GitHub App or bot)? | Platform | Automatic dev deploys | PR-based bot design described; credential scoped to the GitOps repo only |
| Q8 | How are schema migrations run and ordered relative to deploys? | Customer | Safe stage rollouts | Assumption A8 |

## 5. Decisions made to keep the work moving

- **One base, two thin overlays.** Overlays may only change: namespace, hostname, image
  digest, replica count, `LOG_LEVEL`, `PUBLIC_MODE`, and the database egress address. A test
  fails if anything else differs.
- **Pinned images only.** Dev tracks the newest image digest from the customer's CI; stage
  receives the same digest through a promotion PR, so what was tested in dev is exactly what
  runs in stage.
- **Secret by reference only.** Nothing in Git or CI contains a password or example
  connection string.
- **Probes follow the app's own semantics.** Liveness uses `/healthz` so a database outage
  does not restart pods; readiness uses `/readyz` so traffic stops going to pods that cannot
  reach the database.
- **Zero-downtime rollout.** `maxUnavailable: 0`, `maxSurge: 1`, readiness-gated, plus a
  PodDisruptionBudget so node maintenance never takes all pods at once.
- **Least privilege.** Dedicated service account with no API token mounted, non-root,
  read-only root filesystem, all Linux capabilities dropped.
- **Network intent is explicit.** Default-deny; allow ingress only on 8080; allow egress
  only to DNS and the database.
- **Safe exposure default.** Internal-only until authentication and rate limiting are
  confirmed (Q1, Q2). No admin surface is exposed (the app has none; F9).
- **No invented platform APIs.** Where the starter pack is silent (scrape config, external
  secrets, ingress annotations), the gap is written down as an integration point.

## 6. Acceptance criteria (customer-facing)

**Dev (this week)**

1. `https://claims-api.dev.apps.example.invalid/healthz` returns 200 from inside the
   allowed network.
2. Merging a new image build in the customer's repo results in a dev deployment PR with a
   pinned digest, without anyone hand-editing YAML.
3. A rollout never drops below the current number of ready pods.
4. If the database is unreachable, pods stay running, stop receiving traffic, and an alert
   fires; they recover without manual action when the database returns.
5. No secret value appears in Git, CI logs, or rendered manifests.

**Stage (next week)**

6. The same image digest that passed in dev is promoted to stage through one reviewed PR.
7. `dev` and `stage` rendered manifests differ only in the approved fields (section 5).
8. A new operator can deploy, verify, and roll back stage using only `runbook.md`.
9. Q1, Q2, Q4 are answered before stage is exposed beyond the internal network.

## 7. Out of scope

- Building or changing the application or its container image.
- Creating the Secret value, the database, the cluster, or ingress controllers
  (platform-owned).
- A production environment, autoscaling, and multi-region.
- A real deployment. All validation in this submission is static (rendered manifests and
  tests) and says so.
