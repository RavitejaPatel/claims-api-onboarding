# Platform contract

- Environments: `dev` and `stage`, each in a dedicated namespace.
- Delivery: a pull request to the GitOps repository; Argo CD applies the approved result.
- Configuration: Kustomize bases and overlays are supported.
- Images: use immutable digests or a pinned version; `latest` is rejected.
- Secrets: reference an existing Secret or external-secret integration. Secret values
  are supplied out of band by the platform team.
- Ingress: an AWS load balancer is provisioned from a reviewed Kubernetes Ingress.
  TLS certificates are managed by the platform; the hostname must be explicit.
- Network: default-deny is available, and egress to the managed database must be
  described. Do not assume arbitrary internet egress.
- Observability: stdout/stderr, Prometheus metrics, and a shared Grafana/alerting stack
  are available.
- CI: GitHub Actions can run linting and tests. Deployment credentials are not stored
  in pull requests from forks.
- Ownership: the application team owns code and service behavior; the platform team
  owns cluster primitives, ingress controllers, secret delivery, and shared alerting.
