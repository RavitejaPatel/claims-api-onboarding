# AI usage

AI assistance was used throughout, as the brief allows. This records which tool, how it
was used, what was checked, and what was changed or rejected after checking.

## Tool and setup

- **Claude (Anthropic)**, in claude.ai, with a cloud Linux workspace where it could run
  commands. Evidence files from that workspace are labelled
  `container (Linux, Claude workspace)`.
- **My Windows laptop**, where I set up the repository, made every commit in this
  history, installed the tools, and ran the validation myself. Those evidence files are
  labelled `local (Windows)`.

## How I worked with it

- I asked it to read the assessment materials first and walk me through the requirements
  before building anything, and to split the work into goals, one at a time, each ending in
  a commit I made myself.
- For each goal it drafted the files and ran the checks in its workspace; I reviewed the
  files, asked about anything I did not understand, applied them to my repository, and
  ran the validation on my laptop.
- It was not allowed to push or commit to any repository on my behalf.

Representative prompts (paraphrased):

- "Read the repo and help me understand the complete requirements; I will read along."
- "Go one goal at a time; tell me what is done and what is next, with a commit message."
- "What did you include in `.gitignore` and `.gitattributes`, and why?"
- "What does `kustomization.yaml` do?"
- "How did you come up with this image digest value?"

## Assessment materials

The repository shared with me contained the whole assessment repository, including
evaluator-only files (an evaluator guide and a scorecard). The assistant read them during
its first scan of the repository, before we realized what they were. From then on we
worked only from the candidate brief, the starter pack and the submission contract, which
are the only assessment files included here (in `inputs/`, unchanged).

## What was verified, and how

| Claim | How it was checked |
| --- | --- |
| Manifests render and are valid | `kustomize build` + `kubeconform -strict` (Kubernetes 1.30 schemas), on Linux and on Windows |
| Manifests follow the brief | 10 contract checks per environment, each traced to an input document |
| Dev and stage do not drift | Field-by-field comparison outside the approved overlay fields |
| The checks can actually fail | Unit tests break copies of the manifests, workflows and alert rules on purpose and expect each check to catch it |
| No secrets committed | Repository-wide credential scan, plus the assessment's own preflight script |
| GitHub Actions pinned correctly | Each commit SHA resolved from its release tag with `git ls-remote`, not typed from memory |
| Tool downloads are genuine | Checksums compared against each project's published checksum file |
| Workflows are well-formed | `actionlint` |
| Alerts fire when they should | `promtool test rules` against four scenarios, including a 10-minute database outage |
| Smoke test works | Run against local stand-ins of the app, healthy and broken. **Not** run against a real deployment. |
| Same result on two machines | Content fingerprint in each evidence file matches between Linux and Windows |

## Changed or rejected after checking

| What the assistant produced or suggested | What was wrong | What we did |
| --- | --- | --- |
| A hand-typed placeholder image digest | Indistinguishable from a real digest; not reproducible | I asked where it came from. Replaced with the sha256 of a stated text, documented as assumption A12. |
| Evidence fingerprint | Differed between my Windows run and the Linux run for identical files: Windows sorts paths case-insensitively | Found by comparing the two runs; fixed to sort by path text; confirmed matching fingerprints |
| Windows download link for kustomize | Wrong file name (`.tar.gz`; the Windows release is a `.zip`) | Checked the release assets before I used it; corrected |
| Credential-scan pattern for Secret objects | Could match across YAML documents (a later ConfigMap's `data:`) | Limited to one document; test added |
| Tool-version command with the kubectl fallback | `kubectl version` would try to contact a cluster | Changed to `kubectl version --client` |
| Using `kustomize edit set image` in CI | Rewrites the overlay and drops its explanatory comments | Rejected; small script that changes exactly one line, with tests |
| Opening pull requests with the default `GITHUB_TOKEN` | Such pull requests do not trigger other workflows, so the required check would never run | Rejected; short-lived GitHub App token instead |
| Engagement assumption "no controller-specific annotations" | Contradicted the internal-only load balancer, which needs one | Rewrote A5 to state the controller assumption explicitly |
| Default Ingress routing | Exposes `/metrics` on the same host | Accepted while internal-only; recorded as Q9, a blocker for going public |
| A draft of the test suite left in the assistant's workspace by an interrupted session | Not yet reviewed | Every file was re-read and fixed before use; its scratch history was cleaned |

## In my own words

<!-- Written by me before submitting: the three decisions I would defend first, and why. -->
