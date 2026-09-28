# claims-api on the shared platform: customer handoff

For the `claims-api` team. What is ready, what we need from you, who does what, and what
to do when something goes wrong.

## What you get

| | Dev | Stage |
| --- | --- | --- |
| URL | `https://claims-api.dev.apps.example.invalid` | `https://claims-api.stage.apps.example.invalid` |
| Reachable from | Your internal network (see "Before going public") | Same |
| How releases arrive | Automatically after you merge to `main` | When you promote a release that is healthy in dev |
| Approvals | None beyond the automated checks | One person from your team and one from the platform team |
| Pods | 2, updated one at a time with no downtime | 2, same |

You maintain **one** definition of the service. Dev and stage differ only in a short,
reviewed list of settings (address, image version, log level, replica count, database
address), and an automated check stops them drifting apart.

## How a release reaches you

1. You merge to `main` in your application repository.
2. Your pipeline builds the image and opens a one-line pull request that points dev at it.
3. Automated checks pass, the pull request merges, and dev updates within minutes.
4. When you are happy with dev, run **promote-to-stage**. A reviewer from each team
   approves the one-line pull request, and stage updates.

To undo a release, revert its pull request. The previous version rolls back the same
zero-downtime way. The runbook has the exact steps.

## What we need from you

- [ ] **Database password:** give it to the platform team through the agreed secure
      channel. Never in Git, chat, email, or a ticket.
- [ ] **Database address** for dev and stage, so network rules allow only that
      connection (Q3).
- [ ] **How callers authenticate**, and what `PUBLIC_MODE` changes (Q1).
- [ ] **Rate-limit expectations** for public use (Q2).
- [ ] **On-call contacts** for dev and stage incidents (Q4).
- [ ] **Expected traffic and latency** so alert thresholds fit (Q5).
- [ ] **Whether claims contain personal data**, and confirmation that request bodies are
      not logged (Q6).
- [ ] **How schema migrations run** relative to deploys (Q8).
- [ ] **Sample `/metrics` output**, so we can add error-rate and latency alerts (Q11).
- [ ] **The image's runtime user** is non-root and it writes only to `/tmp` (A11).
- [ ] **Two GitHub settings in your repository:** a `release` environment holding the
      registry push credential, and a `gitops-dev` environment holding the deploy app key
      (`docs/delivery.md`).

The full list of questions, and the default we used for each until you answer, is in
`docs/engagement.md`.

## Who owns what

| You (claims team) | Platform team |
| --- | --- |
| Application code and container image | Cluster, namespaces, and nodes |
| Releases, promotions, rollbacks | Load balancer, certificates, DNS, ingress |
| Service behaviour, errors, and performance | Secret delivery (storing and rotating the password you supply) |
| First response to `team="claims"` alerts | Shared metrics, dashboards, and alerting; `team="platform"` alerts |
| Database schema and migrations | Argo CD and the GitOps repository settings |
| Reviewing stage changes | Reviewing stage and shared-definition changes |

## When something is wrong

Alerts link straight to the matching section of `runbook.md`. The most important one:

- **No ready pods** usually means the database cannot be reached. The pods stay up and
  recover by themselves when it comes back. Do not restart them; check the database.
- **Stuck rollout** means a new release did not become healthy. The previous version keeps
  serving. Revert the release.
- **Restarts** mean the application process itself is failing. Check its logs.

If the problem is the load balancer, certificate, cluster, or alerting, contact the
platform team. The runbook's ownership table lists which symptom goes where.

## Before going public

The load balancer is internal-only for now. Making stage reachable from the internet is
a one-line reviewed change, and we will make it once:

1. Authentication for callers is confirmed (Q1).
2. A rate limit or abuse protection is agreed (Q2).
3. `/metrics` is not reachable through the public address (Q9).
4. On-call contacts are in place (Q4).

## Go-live checklists

**Dev (this week):** password and database address delivered; first release deployed
through a pull request; smoke test passes; a test rollback done once.

**Stage (next week):** questions Q1, Q2, Q4, Q9 answered; one release promoted from dev;
alerts routed to your on-call; your team has walked through `runbook.md` once.

The detailed acceptance criteria are in `docs/engagement.md`, section 6.
