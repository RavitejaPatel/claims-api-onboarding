# Candidate brief: onboard `claims-api`

You are the forward deployed engineer for a team launching `claims-api`, a small
customer-facing service. The team can build a container, but has never deployed to the
shared Hosting Services platform. They want a fast path to dev and stage while preserving
the platform's GitOps, security, and support conventions.

You have **24–36 hours**. AI tools are allowed. Do not use real credentials or connect
to an external cluster.

## Customer request

> "Give us a URL for the API, make deploys automatic, keep the database password safe,
> and tell us what to do when it is unhealthy. We need dev this week and stage next
> week. We do not want to maintain a separate set of manifests for every environment."

The synthetic platform contract and application notes are in `starter-pack/`.

## Constraints

- Delivery is pull-request based and rendered by Kustomize/Argo CD.
- Dev and stage must differ only through reviewed overlay configuration.
- The service listens on port 8080 and exposes `/healthz`, `/readyz`, and `/metrics`.
- The database is an existing managed service. The password must be referenced, never
  stored in the repository.
- Public ingress requires TLS, an explicit hostname, and an explanation of
  authentication/rate limiting. Do not expose an admin endpoint.
- The platform team owns the cluster; the application team owns application code and
  service-level configuration.
- A new operator should be able to deploy, diagnose, and roll back the service from
  your documentation.

## Tasks

1. **Shape the engagement.** Record the assumptions you would confirm with the customer,
   identify at least three unanswered questions, and state which defaults you chose to
   keep the work moving.
2. **Build a reusable integration.** Create a base plus dev and stage overlays (or an
   equivalent parametrized structure) containing the workload, service, ingress, config
   references, resource policy, health probes, and safe rollout settings.
3. **Add the delivery path.** Provide a CI workflow or a precise workflow design that
   validates manifests, builds or references an immutable image, and creates the
   deployment pull request. Explain the trust boundary and required permissions.
4. **Make it supportable.** Add a smoke/contract test, useful metrics or alerting
   expectations, a runbook, rollback instructions, and a short customer handoff.
5. **Show the next increment.** Describe what you would automate or standardize after
   the first onboarding, and what evidence would justify that investment.

## Required response

Return a repository or archive following the [submission contract](../../docs/submission-contract.md).
At minimum, include the base/overlays, validation or contract tests, evidence,
`runbook.md`, `ai-usage.md`, and the customer-facing handoff.

Do not implement a real deployment, add secrets, or claim that a command ran if it did
not run. If a platform capability is missing from the starter pack, make the assumption
explicit and describe the integration point rather than inventing undocumented APIs.

## What will be assessed

We will assess how well you translate ambiguity into a safe path, make the happy path
repeatable, preserve platform boundaries, and communicate trade-offs to both the
customer and the operations team.
