# Evidence

Everything here is produced by `python tests/validate.py`. Each file says where it ran;
nothing here came from a live cluster, because this exercise has none.

| File | Produced by | Where it ran |
| --- | --- | --- |
| `rendered/dev.yaml`, `rendered/stage.yaml` | Step 1 of `validate.py` (`kustomize build`) | Same as the latest validation run |
| `validation-container-linux-claude-workspace.txt` | Full run of `validate.py` | Linux container used during AI-assisted development (see `ai-usage.md`) |
| `validation-local-windows.txt` | Full run of `validate.py` (added after the candidate runs it) | The candidate's Windows laptop |

Each validation file records the commit, a content fingerprint (sha256 over `solution/`
and `tests/`, line endings normalized), and the tool versions. Two runs with the same
fingerprint checked byte-identical manifests and tests, even on different machines.

What is **not** evidenced here, because it needs a real platform: an Argo CD sync, the
load balancer and certificate, pods starting, and the database connection. The runbook
describes how to verify those after a real deployment.
