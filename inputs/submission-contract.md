# Submission contract

Use this contract for both assessments. It makes responses comparable and lets an
evaluator audit a solution without guessing what the candidate intended.

## Required layout

```text
README.md                 What was built, assumptions, and how to validate it
solution/                 The proposed code, manifests, scripts, and configuration
tests/                    Automated checks written or adapted by the candidate
evidence/                  Command output, screenshots, diagrams, or test results
runbook.md                Operations and support handoff
ai-usage.md               Tools used, important prompts, generated content reviewed,
                          and changes made after verification
```

The candidate may use a different layout only if `README.md` maps it to these sections.
Generated dependencies, credentials, kubeconfigs, customer data, and binary build
artifacts must not be included.

## Minimum README contents

- **Goal and scope:** what problem is solved and what is intentionally out of scope.
- **Assumptions:** platform, version, traffic, failure, and access assumptions.
- **Architecture or change summary:** a diagram is welcome but not required.
- **Validation:** exact commands an evaluator can run from a clean checkout.
- **Trade-offs and next steps:** what would change for production.

## Evidence standard

Evidence must be reproducible. Prefer command output over a claim such as "tested
locally." Every command should state whether it ran locally, in a container, or against
a mocked cluster. If something could not be run, explain why and provide the static
check or test that substitutes for it.

## AI-use standard

AI use is allowed and expected to be disclosed. The disclosure is not scored on tool
choice. It is scored on whether the candidate:

- checked generated manifests, scripts, and permissions;
- rejected suggestions that did not fit the stated platform contract;
- tested the final result rather than presenting generated text as proof; and
- can explain the important decisions without the assistant.

## Shared evaluator workflow

1. Run the repository preflight from the assessment repository:

   ```sh
   python3 tools/audit_submission.py --role sre /path/to/submission
   # or
   python3 tools/audit_submission.py --role fde /path/to/submission
   ```

   The preflight checks required paths, high-confidence credential markers, and common
   unsafe defaults. It is a gate, not a replacement for reading the implementation.
2. Confirm the submission contains the required sections and no secrets.
3. Read `README.md`, `runbook.md`, and `ai-usage.md` before reading implementation detail.
4. Run the candidate's documented validation commands from a clean checkout.
5. Run the role-specific static checks and compare behavior to the evaluator oracle.
6. Score each dimension using observed evidence. A dimension scored `0` or `1` must
   include a concrete reason.
7. Run the role-specific follow-up questions. Do not award points for a polished answer
   that contradicts the submitted implementation.

## Rating scale

| Rating | Meaning |
| --- | --- |
| 4 | Production-minded, correct, tested, and clearly explained |
| 3 | Correct for the exercise with minor omissions that are easy to remediate |
| 2 | Partial solution; the main path works but important reliability or safety gaps remain |
| 1 | Significant misunderstanding, unverified claims, or unsafe defaults |
| 0 | Missing, non-functional, or contradicts the stated requirements |

The two role scorecards use the same scale and weights. A hard-fail condition overrides
the numeric total when the candidate introduces a secret, destructive change without a
rollback, or claims validation that did not occur.
