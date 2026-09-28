# claims-api runbook

For whoever operates `claims-api` in dev or stage: deploy, verify, roll back, respond to
alerts, and know who to call. You should not need anything outside this repository.

| | |
| --- | --- |
| Service | `claims-api`, customer-facing HTTP API, port 8080 |
| Environments | dev: namespace `claims-api-dev`, `https://claims-api.dev.apps.example.invalid`<br>stage: namespace `claims-api-stage`, `https://claims-api.stage.apps.example.invalid` |
| Exposure | Internal load balancer only, HTTPS only, until authentication and rate limiting are confirmed (`docs/engagement.md`, Q1, Q2) |
| Health | `/healthz` = process only (liveness). `/readyz` = database and schema (readiness). `/metrics` = Prometheus. |
| Deploys through | Pull request to the GitOps repository, applied by Argo CD (`claims-api-dev`, `claims-api-stage`) |
| Dependencies | Managed PostgreSQL (via `DATABASE_URL` from Secret `claims-api-db`), cluster DNS |
| Alert rules | `solution/observability/alerts.yaml` |

Access assumed for operators (A16): read-only access to both namespaces, view access to
the two Argo CD applications, and permission to run Argo CD's **restart** action. No one
needs write access to the cluster for normal work.

## 1. Ownership and escalation

| If the problem is... | First responder | Escalate to |
| --- | --- | --- |
| Application errors, crashes, bad release, slow responses | Customer app team (`claims`) | Platform team, if the cause looks like the cluster |
| Database unreachable or slow | Customer app team confirms from `/readyz` and logs | Owner of the managed PostgreSQL (Q3); platform team for network paths |
| Load balancer, certificate, DNS, ingress controller | Platform team | Cloud provider support via platform team |
| Secret missing or wrong | Platform team (owns secret delivery) | Customer supplies a new value out of band |
| Argo CD not syncing, cluster capacity, node problems | Platform team | Platform escalation path |
| Alerts not arriving, metrics not scraped | Platform team (owns shared alerting) | |

Named people, on-call rotations and chat channels are placeholders until Q4 is answered.
Alerts carry a `team` label (`claims` or `platform`) that says who acts first.

## 2. Deploy

### Dev (automatic)

1. Merge a change in the customer's application repository.
2. The release workflow builds and pushes the image, then opens a pull request in the
   GitOps repository titled **"Deploy claims-api `<digest>` to dev"**. It changes one line.
3. The `validate` check runs. When it passes, the pull request merges itself.
4. Argo CD applies the change to `claims-api-dev` with a rolling update.
5. [Verify](#3-verify-a-deployment).

If the pull request does not merge, open it and read the failing `validate` output; it
names the exact check and field that failed.

### Promote to stage

Promote only a digest that has been healthy in dev (no active alerts, smoke test passing).

1. In the GitOps repository, run the **promote-to-stage** workflow (Actions tab, "Run
   workflow" on `main`).
2. It opens **"Promote claims-api `<digest>` to stage"**, changing one line.
3. A reviewer from the customer team and one from the platform team approve it.
4. Merge. Argo CD applies it to `claims-api-stage`.
5. [Verify](#3-verify-a-deployment).

### Configuration changes

Change `LOG_LEVEL` or `PUBLIC_MODE` in the environment's overlay
(`solution/k8s/overlays/<env>/kustomization.yaml`) through a normal pull request. The
generated ConfigMap gets a new name, so the change rolls out like a release and can be
reverted the same way.

## 3. Verify a deployment

Run these in order. Each is read-only.

```sh
# 1. Argo CD applied the commit and the app is healthy (waits up to 5 minutes)
argocd app wait claims-api-stage --sync --health --timeout 300

# 2. The rollout finished
kubectl -n claims-api-stage rollout status deployment/claims-api --timeout=5m

# 3. The running image is the digest you expect
kubectl -n claims-api-stage get deployment claims-api \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   compare with: solution/k8s/overlays/stage/kustomization.yaml

# 4. All pods ready, no restarts
kubectl -n claims-api-stage get pods -l app.kubernetes.io/name=claims-api

# 5. The application contract, from a machine inside the allowed network
python tests/smoke.py https://claims-api.stage.apps.example.invalid
```

Done when: Argo CD shows *Synced* and *Healthy*, the rollout is complete, the image
digest matches Git, every pod is ready with zero restarts, and the smoke test prints
`RESULT: PASS`.

## 4. Roll back

Git is the source of truth, and Argo CD reverts manual changes (`selfHeal`). A rollback is
therefore a Git change, like a deploy.

### Standard rollback (minutes)

1. Find the commit that introduced the problem: the "Deploy ... to dev" or
   "Promote ... to stage" merge in the GitOps repository.
2. Revert it: `git revert <commit>` on a branch, or the **Revert** button on the merged
   pull request in GitHub.
3. Get the revert pull request approved (same rules as a promotion for stage) and merge.
4. Argo CD applies the previous digest with the same zero-downtime rolling update.
5. [Verify](#3-verify-a-deployment), checking the digest matches the previous one.

### Emergency rollback (platform on-call only)

If waiting for review is not acceptable during an incident:

1. Platform on-call turns off auto-sync for the application and runs
   `argocd app rollback claims-api-stage <history-id>` (find the id with
   `argocd app history claims-api-stage`).
2. Open and merge the Git revert immediately afterwards (standard steps 1–3), then turn
   auto-sync back on. Until then Git and the cluster disagree; say so in the incident
   channel.

### Do not

- Do not use `kubectl rollout undo`, or edit the Deployment in the cluster. Argo CD will put
  it back within minutes and the incident gets harder to reason about.
- Do not roll back past a database schema change without the customer team. If a release
  migrated the schema, the old version may fail `/readyz` (schema compatibility). The
  rollout then stalls safely rather than serving errors, but it will not finish (A8, Q8).

## 5. Alerts

Every alert links here. `team` says who acts first.

### ClaimsApiNoReadyPods

**Critical, team `claims`.** No pod has passed `/readyz` for 2 minutes. Users get errors.

1. Is it the database? Readiness checks it; liveness does not, so pods are running but
   not ready. `kubectl -n <ns> get pods` shows `0/1` READY with **no** restarts.
2. Read the reason: `kubectl -n <ns> logs deployment/claims-api --tail=100` and
   `kubectl -n <ns> describe pod <pod>` (the readiness failure message is in Events).
3. If the database is unreachable, follow [Database unavailable](#database-unavailable).
4. If it started right after a deploy, the new version may be incompatible with the schema:
   [roll back](#4-roll-back).
5. If pods are restarting as well, see [ClaimsApiRestarting](#claimsapirestarting).

### ClaimsApiDegraded

**Warning, team `claims`.** Fewer ready pods than desired for 10 minutes. Still serving,
with less headroom.

1. `kubectl -n <ns> get pods -o wide`: find the pod that is not ready and why (Events).
2. `Pending` usually means no capacity or scheduling rules: platform team.
3. Not ready or restarting: treat as for the matching alert above or below.

### ClaimsApiRolloutStuck

**Warning, team `claims`.** A new version did not become ready within 5 minutes. The
previous version keeps serving, because `maxUnavailable` is 0.

1. `kubectl -n <ns> rollout status deployment/claims-api` and `describe` the new pod.
2. Image pull error: the digest does not exist or cannot be pulled; check the deploy PR.
3. New pod not ready: read its logs. Usually a bad release or a schema mismatch.
4. Decide: [roll back](#4-roll-back) (default) or fix forward with a new release.

### ClaimsApiRestarting

**Warning, team `claims`.** A container restarted more than 3 times in 15 minutes.
Liveness only checks the process, so this is not a database problem.

1. `kubectl -n <ns> logs <pod> --previous` for the crash.
2. `kubectl -n <ns> describe pod <pod>`: look for `OOMKilled` under Last State. If so, the
   memory limit (512Mi) is too low for the workload: raise it through a pull request to the
   base, with platform review.
3. If it began with a release, [roll back](#4-roll-back).

### ClaimsApiMetricsMissing

**Warning, team `platform`.** Prometheus has not scraped `/metrics` for 10 minutes. Other
alerts may be blind.

1. Are there pods? If not, this is a symptom; follow the other alerts.
2. If pods are fine, the scrape path is broken. The network policy already allows port 8080
   from any source, so check the platform's scrape configuration for the namespace
   (A6, A15).

## 6. Scenarios

### Database unavailable

What happens if PostgreSQL is unreachable for ten minutes:

| Time | What the system does |
| --- | --- |
| 0–15 s | `/readyz` fails 3 times; pods are removed from the Service and load balancer. Liveness keeps passing, so **pods are not restarted**. |
| 2 min | `ClaimsApiNoReadyPods` fires (critical, team `claims`). With no ready targets the load balancer answers `503` quickly instead of letting requests hang. |
| During | A deploy started now stalls safely: new pods cannot become ready, old pods are not removed. |
| Recovery | When the database answers, `/readyz` passes within seconds and traffic returns on its own. The alert resolves. No action needed on the pods. |

What to do:

1. Confirm from pod events and logs that readiness fails on the database.
2. Contact the database owner (Q3) and the platform team if a network path is suspected
   (egress is allowed only to the database address in the network policy).
3. Do **not** restart pods or roll back: neither fixes the database, and restarts add load
   when it comes back.
4. After recovery, run the [verification](#3-verify-a-deployment) steps and note the
   outage window in the incident record.

### Secret rotation

The platform team owns secret delivery; the customer supplies the new value out of band.

1. Platform team updates Secret `claims-api-db` in the namespace.
2. Environment variables are read at start-up, so pods keep the old value until they
   restart. Run Argo CD's **restart** action on the `claims-api` Deployment. It performs a
   normal rolling update (one extra pod at a time, never below the ready count).
3. [Verify](#3-verify-a-deployment). If `/readyz` fails, the new credential is wrong: restore
   the previous value first, then investigate.

### Scaling

Replica count lives in each overlay (`replicas:`). Change it through a pull request;
dev and stage may differ here by design. Keep at least 2 for zero-downtime rollouts.

## 7. Reference

Read-only commands used above (replace `<ns>` with `claims-api-dev` or `claims-api-stage`):

```sh
argocd app get claims-api-stage
argocd app history claims-api-stage
kubectl -n <ns> get deployment,pods,svc,ingress -l app.kubernetes.io/name=claims-api
kubectl -n <ns> describe pod <pod>
kubectl -n <ns> logs deployment/claims-api --tail=200
kubectl -n <ns> logs <pod> --previous
kubectl -n <ns> get events --sort-by=.lastTimestamp
```

Related documents: `docs/delivery.md` (how changes flow), `docs/observability.md` (signals
and alerts), `docs/handoff.md` (customer summary), `docs/engagement.md` (assumptions and
open questions).
