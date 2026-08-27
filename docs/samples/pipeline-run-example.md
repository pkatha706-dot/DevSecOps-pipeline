# Sample Pipeline Run: All 9 Stages Passing

Real run data pulled from GitHub's Actions API for
[run #20](https://github.com/pkatha706-dot/DevSecOps-pipeline/actions/runs/33116833965)
(commit [`45eb0ba`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/45eb0ba)),
the run that produced [the sample triage report](triage-report-example.md).
Total wall-clock time: **5m 08s**, `21:09:50` → `21:14:58` UTC.

| Stage | Job | Result | Duration |
|---|---|---|---|
| 1 | TruffleHog Secret Scan | ✅ success | 10s |
| 2 | Bandit SAST | ✅ success | 12s |
| 3 | Snyk SCA | ✅ success | 17s |
| 4 | Checkov IaC Scan | ✅ success | 38s |
| 5 | Docker Build | ✅ success | 24s |
| 6 | Trivy Container Scan | ✅ success | 26s |
| 7 | Deploy for DAST | ✅ success | 12s |
| 8 | OWASP ZAP Baseline Scan | ✅ success | 1m 14s |
| 9 | AI Triage | ✅ success | 1m 09s |

Live run (with full logs, including the retry/backoff behavior from
[INC-10](../incidents.md#inc-10-transient-503s-had-no-retry-path) if it triggers):
https://github.com/pkatha706-dot/DevSecOps-pipeline/actions/runs/33116833965
