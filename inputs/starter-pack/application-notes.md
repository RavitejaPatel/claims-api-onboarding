# Application notes

- Image is published by the customer to `registry.example.invalid/claims-api`.
- The application listens on TCP port 8080.
- `GET /healthz` checks only process health.
- `GET /readyz` checks database connectivity and schema compatibility.
- `GET /metrics` exposes Prometheus text format.
- Required non-secret configuration: `LOG_LEVEL`, `PUBLIC_MODE`.
- Required secret configuration: `DATABASE_URL`.
- The application has no admin HTTP route; administrative actions are a CLI run by the
  customer team.
- The customer expects zero-downtime rolling deploys for the pilot.
