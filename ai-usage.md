## In my own words

How I used AI:

- **Understanding the requirements.** I used the assistant to skim and scan the whole
  repository first and summarize what was being asked. I then studied the brief, starter
  pack and submission contract myself, in detail, to understand the requirements properly.
- **Clarifying things I was unsure about.** I asked it to explain parts I did not fully
  understand (for example what `kustomization.yaml` does, and where the image digest value
  came from) before accepting them.
- **Debugging.** When something failed or looked wrong on my machine (missing tools on
  PATH, and different evidence fingerprints on Windows and Linux), I used it to find the
  cause and fix it.

Decisions I would defend first:

- **Internal-only load balancer for now.** The brief requires an authentication and
  rate-limiting decision before public exposure, and the inputs do not say how the API
  authenticates callers. Keeping it internal is safe, and going public is one reviewed change.
- **Liveness on `/healthz`, readiness on `/readyz`.** A database outage should stop traffic
  to the pods, not restart them. Restarts would not fix the database and would add load
  when it comes back.
- **CI never holds cluster credentials.** Deploys are Git merges that Argo CD pulls, so even
  a compromised workflow cannot change the cluster directly.