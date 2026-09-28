# Kubernetes manifests

```text
base/                       Shared definition. Never copied per environment.
  kustomization.yaml        Labels, resource list, non-secret config (ConfigMap generator)
  serviceaccount.yaml       Dedicated identity, no API token mounted, no RBAC
  deployment.yaml           Probes, zero-downtime rollout, resources, security context
  service.yaml              ClusterIP on port 80 -> container port 8080
  ingress.yaml              Explicit host, HTTPS only, internal load balancer
  networkpolicy.yaml        Default deny + allow app port in, DNS and PostgreSQL out
  poddisruptionbudget.yaml  Keeps one pod serving during node maintenance
overlays/
  dev/kustomization.yaml    Namespace, host, image digest, replicas, LOG_LEVEL, DB address
  stage/kustomization.yaml  Same fields, stage values
```

Render an environment:

```sh
kustomize build solution/k8s/overlays/dev
kustomize build solution/k8s/overlays/stage
```

(`kubectl kustomize <dir>` works too.) Why each setting exists is explained in comments
inside the files and in `docs/engagement.md`.
