# Tests and validation

One command checks everything. It only reads files: nothing is deployed and no cluster is
contacted.

```sh
python tests/validate.py
```

| Step | What it checks | Why |
| --- | --- | --- |
| 1. Render | `kustomize build` of the dev and stage overlays, saved to `evidence/rendered/` | The base and overlays combine into valid output |
| 2. Schema | `kubeconform -strict` against Kubernetes 1.30 schemas | No typos, wrong fields, or invalid values |
| 3. Contract | 10 checks per environment in `contract_checks.py` (image pinning, probes, rollout, resources, security context, config/secret, ingress, wiring, network policy, namespace) | The manifests follow the brief, app notes, platform contract, and `docs/engagement.md` |
| 4. Drift | Dev and stage compared after removing the approved overlay fields; any other difference is reported by field path | "Dev and stage differ only through reviewed overlay configuration" |
| 5. Credentials | Every text file in the repository scanned for keys, tokens, passwords in URLs, and Secrets with inline data | A committed secret is a hard fail |
| 6. Unit tests | `test_contract.py`: the real manifests pass, and 19 deliberate mistakes (broken copies of the manifests and fake credentials) are each caught by the right check. `test_delivery.py`: digest pinning, Argo CD wiring, and the CI trust rules (pinned actions, read-only token, no secrets on pull requests) | Proves the checks can fail, so a pass means something |
| 7. Alert rules | `promtool check rules` and `promtool test rules` on `solution/observability/` | Alerts are valid and fire (or stay quiet) in the scenarios that matter. Optional locally (SKIP if promtool is missing); required in CI via `--strict` |

The result and all output are written to `evidence/validation-<where>.txt`. The exit
code is 0 on success and 1 on any failure, so CI can use the same command.

`--where` labels the run in the evidence file, for example
`python tests/validate.py --where ci`. It defaults to `local (<your OS>)`.

## Files

| File | Purpose |
| --- | --- |
| `validate.py` | The one-command runner described above |
| `contract_checks.py` | The rules, each traced to an input document |
| `test_contract.py` | Unit tests for the rules |
| `test_delivery.py` | Tests for the delivery path and workflow trust boundary |
| `smoke.py` | Smoke test for a live deployment (run after every deploy or rollback; see `runbook.md`) |
| `test_smoke.py` | Runs `smoke.py` against local stand-ins of the app, healthy and broken |
| `manifests.py` | Renders an overlay and parses the YAML (shared by the runner and tests) |
| `secret_scan.py` | Credential scanner |
| `requirements.txt` | Python dependency (PyYAML) |

## Setup

Needs Python 3.9+, PyYAML, kustomize v5.4+, and kubeconform. `promtool` (from the
Prometheus release) is optional locally and required in CI. `kubectl kustomize` is used
if standalone kustomize is missing, but kubectl bundles an older kustomize that may not
support every field used here, so the standalone binary is recommended.

### Windows (PowerShell)

```powershell
# Python dependency
python -m pip install -r tests\requirements.txt

# kustomize and kubeconform into a per-user tools folder
$tools = "$HOME\tools"
New-Item -ItemType Directory -Force $tools | Out-Null
Invoke-WebRequest "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.4.3/kustomize_v5.4.3_windows_amd64.zip" -OutFile "$tools\kustomize.zip"
Invoke-WebRequest "https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-windows-amd64.zip" -OutFile "$tools\kubeconform.zip"
Expand-Archive "$tools\kustomize.zip" -DestinationPath $tools -Force
Expand-Archive "$tools\kubeconform.zip" -DestinationPath $tools -Force

# Add the folder to your user PATH (new terminals) and to this terminal
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$tools", "User")
$env:Path += ";$tools"

kustomize version
kubeconform -v
```

Then, from the repository root:

```powershell
python tests\validate.py
```

### macOS / Linux

```sh
python3 -m pip install -r tests/requirements.txt
# kustomize: https://github.com/kubernetes-sigs/kustomize/releases (v5.4.3)
# kubeconform: https://github.com/yannh/kubeconform/releases (v0.6.7)
# or with Homebrew: brew install kustomize kubeconform
python3 tests/validate.py
```

kubeconform downloads the Kubernetes JSON schemas from GitHub on first use, so step 2
needs internet access.
