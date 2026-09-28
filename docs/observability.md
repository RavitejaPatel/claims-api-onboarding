# Observability and alerting

What to watch for `claims-api`, what is alerted today, and what is added once the customer
confirms application metric names.

## Signals available now

| Signal | Source | Used for |
| --- | --- | --- |
| Pod readiness and availability | kube-state-metrics (A15) | `ClaimsApiNoReadyPods`, `ClaimsApiDegraded` |
| Rollout progress | kube-state-metrics, from `progressDeadlineSeconds: 300` | `ClaimsApiRolloutStuck` |
| Container restarts | kube-state-metrics | `ClaimsApiRestarting` |
| Scrape health | Prometheus `up` series | `ClaimsApiMetricsMissing` |
| Application metrics | `/metrics` on port 8080 (Prometheus text) | Dashboards; application alerts after Q11 |
| Logs | stdout/stderr, collected by the platform | Diagnosis; level set by `LOG_LEVEL` |

## Alerts in `solution/observability/alerts.yaml`

| Alert | Fires when | Severity | Acts first | Runbook |
| --- | --- | --- | --- | --- |
| ClaimsApiNoReadyPods | 0 available pods for 2 min | critical | claims | [link](../runbook.md#claimsapinoreadypods) |
| ClaimsApiDegraded | fewer available than desired for 10 min | warning | claims | [link](../runbook.md#claimsapidegraded) |
| ClaimsApiRolloutStuck | rollout passed its 5 min deadline | warning | claims | [link](../runbook.md#claimsapirolloutstuck) |
| ClaimsApiRestarting | more than 3 restarts in 15 min | warning | claims | [link](../runbook.md#claimsapirestarting) |
| ClaimsApiMetricsMissing | no successful scrape for 10 min | warning | platform | [link](../runbook.md#claimsapimetricsmissing) |

The rules are unit-tested with `promtool` (`alerts.test.yaml`) against four scenarios: a
10-minute database outage (only `ClaimsApiNoReadyPods` fires, no restart alert, and it
resolves on recovery), a crash loop, a stuck rollout, and broken scraping.

**Proposed routing** (confirm with the customer, Q4, Q5): dev alerts go to a team channel
only. In stage, `critical` pages the customer on-call and `warning` goes to the channel.
The platform team receives `team="platform"` alerts through its existing rotation.

How the rule file is loaded (for example wrapped in a PrometheusRule resource, or added to
a rules directory) is decided by the platform team, who own the shared alerting stack.

## Application alerts to add after Q11

The application's metric names are not in the starter pack, so these are expectations,
not rules yet. Once the customer shares the `/metrics` output, each becomes a rule with a
`promtool` test like the ones above.

| Signal | Why | Starting threshold (tune with real traffic, Q5) |
| --- | --- | --- |
| Request rate | Detects traffic drops that readiness cannot see | Alert if it falls to zero while pods are ready |
| Error ratio (5xx / all) | Main user-facing signal | Above 5% for 5 minutes |
| Latency p95 | Slow database or dependency | Above an agreed target for 10 minutes |
| Database connection errors or pool saturation | Earlier warning than `/readyz` failing | Any sustained errors; pool above 90% |

A pilot availability objective (for example 99.5% of requests succeed over 30 days) can
follow once traffic and error-rate data exist. It is a question for the customer, not a
default to impose.

## Dashboards

One Grafana dashboard per environment, using the shared stack: ready vs desired pods,
restarts, CPU and memory against requests and limits, rollout events, and, after Q11,
request rate, error ratio and latency.

## Logs

- Logs go to stdout/stderr; the platform collects them.
- `LOG_LEVEL` is `debug` in dev and `info` in stage.
- Ask the customer to log a request ID and never log request bodies or claim details
  (Q6), because claims likely contain personal data.
