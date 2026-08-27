# Engineering Log — Pipeline Incidents & Fixes

This is a running log of every real failure hit while building and hardening this
pipeline, in the order they occurred. Each entry follows the same structure:
**Symptom → Investigation → Root Cause → Fix → Verification**.

The point of keeping this is that a security pipeline that "just worked" on the
first try would be a tutorial, not evidence of debugging ability. Every entry
below is a real CI failure with a real root cause and a real, tested fix — not a
hypothetical. Commit hashes are given so each fix can be inspected directly.

| # | Incident | Category | Commit |
|---|---|---|---|
| 1 | [Container failed its health check](#inc-01--container-failed-its-health-check) | Container / permissions | [`0b84806`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/0b84806) |
| 2 | [Checkov failed the IaC scan](#inc-02--checkov-failed-the-iac-scan) | IaC policy | [`a5b7515`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/a5b7515) |
| 3 | [ZAP failed on a GitHub API permission error](#inc-03--zap-failed-on-a-github-api-permission-error) | CI permissions | [`a5b7515`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/a5b7515) |
| 4 | [AI triage script was dead code](#inc-04--ai-triage-script-was-dead-code) | Pipeline design gap | [`5b5992c`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/5b5992c) |
| 5 | [Invalid model ID silently shipped](#inc-05--invalid-model-id-silently-shipped) | Latent bug | [`5b5992c`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/5b5992c) |
| 6 | [Upstream drift mid-implementation](#inc-06--upstream-drift-mid-implementation) | Concurrent-edit conflict | [`5b5992c`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/5b5992c) |
| 7 | [Live run failed on billing, not code](#inc-07--live-run-failed-on-billing-not-code) | Cost control | [`dd97fd1`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/dd97fd1) |
| 8 | [Migrated providers: Anthropic → Gemini](#inc-08--migrated-providers-anthropic--gemini) | Vendor migration | [`38dc125`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/38dc125) |
| 9 | [Gemini model deprecated under us](#inc-09--gemini-model-deprecated-under-us) | Vendor deprecation | [`70d4238`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/70d4238) |
| 10 | [Transient 503s had no retry path](#inc-10--transient-503s-had-no-retry-path) | Resilience | [`0f26d54`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/0f26d54) |
| 11 | [Report silently truncated to one paragraph](#inc-11--report-silently-truncated-to-one-paragraph) | Silent data loss | [`87a8001`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/87a8001) |
| 12 | [The fix for #11 broke on the model that caused it](#inc-12--the-fix-for-11-broke-on-the-model-that-caused-it) | API contract mismatch | [`45eb0ba`](https://github.com/pkatha706-dot/DevSecOps-pipeline/commit/45eb0ba) |

---

## INC-01 — Container failed its health check

**Symptom:** `dast-deploy` timed out after 60s waiting on `curl http://localhost:5000/health`; `docker logs` showed the container had already exited.

**Investigation:** Reproduced locally with `docker build` + `docker run` rather than guessing from CI logs. The container logs showed the real error immediately:
```
sqlite3.OperationalError: attempt to write a readonly database
```

**Root Cause:** The Dockerfile copies the app and creates `appuser` while still root, then drops to `USER appuser` — but never changes ownership of `/app`. SQLite needs to write a journal file into the directory containing the database, and the non-root user had no write permission there.

**Fix:** Added `chown -R appuser:appuser /app` before the `USER appuser` line.

**Verification:** Rebuilt and reran the container locally; confirmed `/health` returned `{"status": "ok"}` and `docker inspect` reported `Health.Status: "healthy"` before pushing.

---

## INC-02 — Checkov failed the IaC scan

**Symptom:** `iac-scan` failed with `soft_fail: false` after INC-01's fix shipped.

**Investigation:** Installed Checkov locally and ran it directly against the Dockerfile with the same flags as CI, rather than trial-and-error pushing to see what turns green.

**Root Cause:** `CKV_DOCKER_2` — no `HEALTHCHECK` instruction in the Dockerfile. Every other one of the 53 checks passed.

**Fix:** Added a `HEALTHCHECK` that polls the existing `/health` route via `python -c` (no `curl` binary in `python:3.11-slim`, so pure Python avoids adding a package just for this).

**Verification:** Reran Checkov locally — 53/53 passed. Rebuilt the image and confirmed `docker inspect` reported `healthy` after the configured `start-period`.

---

## INC-03 — ZAP failed on a GitHub API permission error

**Symptom:** Same run as INC-02, separate failure: `Resource not accessible by integration` against the GitHub Issues API, plus the ZAP step itself failing with the container's exit code 2.

**Investigation:** The `zaproxy/action-baseline` action tries to open a GitHub Issue with the scan results by default. The default `GITHUB_TOKEN` only has read scope, so that call 403'd. Separately, exit code 2 from the ZAP container means "WARN-level alerts found" — expected, since the target app is intentionally vulnerable.

**Root Cause:** Two distinct issues bundled in one failure — (a) the action's default issue-writing behavior needs write scope it didn't have, and (b) `fail_action: true` treats any alert as a step failure, which is correct behavior for a genuinely vulnerable app, not a bug.

**Fix:** Set `allow_issue_writing: false` to stop the unauthorized API call. Left `fail_action: true` alone — the job already has `continue-on-error: true`, so a real finding shows as a warning, not a blocker.

**Verification:** Confirmed on the next run that the 403 no longer appeared in logs; the ZAP job still reported alerts (expected) without crashing on the issue-writing step.

---

## INC-04 — AI triage script was dead code

**Symptom:** None — this was found by inspection, not a failure. Asked to explain how AI triage was integrated, and the honest answer was: it wasn't.

**Investigation:** Read `.github/workflows/devsecops.yml` line by line against `ai_triage/ai_triage.py`. The workflow had 8 scan/deploy jobs; none of them downloaded the report artifacts or invoked the script. It only ran if someone executed it manually per the README.

**Root Cause:** The script and its documentation were written, but the CI wiring to actually call it was never added.

**Fix:** Added a 9th job (`ai-triage`) that runs after `dast`, downloads all four report artifacts, and runs `ai_triage/ai_triage.py` with the right secrets and environment variables.

**Verification:** Confirmed via GitHub's public Actions API that the new job appeared, ran, and downloaded all four artifacts (`Loaded reports: ['bandit', 'snyk', 'trivy', 'zap']` in the logs).

---

## INC-05 — Invalid model ID silently shipped

**Symptom:** Found by code review while wiring INC-04, not by a failure — the pipeline had never actually called this code path before.

**Investigation:** Both `ai_triage.py` and `security_tools_mcp/server.py` called `client.messages.create(model="claude-opus-4-8", ...)`. No model with that ID has ever existed.

**Root Cause:** A hallucinated/typo'd model name that nothing had caught because the calling code was never exercised (see INC-04).

**Fix:** Corrected to a real model ID in both files.

**Verification:** This became moot after INC-08's provider migration, but at the time, confirmed the corrected ID didn't 404 on a live call. A mocked dry-run harness (see [Verification Methodology](#verification-methodology) below) also asserted the exact model string reaching the API client.

---

## INC-06 — Upstream drift mid-implementation

**Symptom:** A conflict appeared when pulling `origin/main` mid-task — 7 commits had landed there while the local fix for INC-04/05 was in progress.

**Investigation:** Diffed `HEAD` against `origin/main` before touching anything further. The ZAP step had been rewritten directly on GitHub — replaced the `zaproxy/action-baseline` marketplace action with a raw `docker run` against `ghcr.io/zaproxy/zaproxy:stable`, and renamed the output artifact to `zap-scan-results` / `zap-report.json`.

**Root Cause:** Concurrent edits to the same file from two directions (local work in progress vs. a direct GitHub web edit). A naive merge would have silently reintroduced a stale filename assumption (`report_json.json`, which no longer existed).

**Fix:** Stashed local work, fast-forwarded to the real `origin/main`, then manually resolved the merge conflict against the *actual* current state rather than the assumption it was based on — including correcting `ai_triage.py`'s expected ZAP filename to match what the rewritten step really produces.

**Verification:** Validated the merged YAML with a Python `yaml.safe_load` before committing, and re-ran the mocked dry-run harness to confirm the script's file-lookup logic matched the new artifact layout.

---

## INC-07 — Live run failed on billing, not code

**Symptom:** `ai-triage` reached the Anthropic API successfully and was rejected: `Your credit balance is too low to access the Anthropic API.`

**Investigation:** Confirmed this wasn't a code defect — the traceback showed report loading, model ID, and the request itself all succeeded up to the point of a clean 400 from Anthropic's billing layer.

**Root Cause:** No funded Anthropic account, and the job ran on every push — meaning every commit would retry (and fail) the same paid call.

**Fix:** Gated the job behind a manual `workflow_dispatch` trigger with `continue-on-error: true`, so routine pushes never attempt or fail on a paid call the account can't cover. (Later reverted in INC-08 once the provider no longer required payment.)

**Verification:** Confirmed subsequent pushes completed all 8 scan stages without attempting the triage call.

---

## INC-08 — Migrated providers: Anthropic → Gemini

**Decision, not a failure:** rather than fund the Anthropic account, switched the triage call to Google's Gemini API, which has a genuinely free tier.

**Scope:** Swapped the `anthropic` SDK for `google-genai` in both `ai_triage.py` and the MCP server's `explain_vulnerability` tool, updated the CI job's dependency install and secret name (`GEMINI_API_KEY`), and updated every README reference.

**Verification:** Before touching the workflow, verified the new SDK's actual call shape locally (`client.models.generate_content(model=..., contents=..., config=...)`) rather than assuming API parity with Anthropic's client. Ran the full mocked dry-run harness against the new code path — report parsing, prompt assembly, the Gemini call, and the GitHub Issue POST all passed — before pushing. Also reverted the manual-trigger gate from INC-07, since a free tier removes the cost reason for it.

---

## INC-09 — Gemini model deprecated under us

**Symptom:** `404 NOT_FOUND` — `This model models/gemini-2.5-flash is no longer available to new users.`

**Investigation:** The error message itself named the replacement model. Treated the live API response as more authoritative than any prior assumption about model names, since model availability changes faster than any static reference.

**Root Cause:** Model deprecation on Google's side, unrelated to this codebase.

**Fix:** Updated both call sites to the model the API itself recommended.

**Verification:** N/A at the code level — confirmed by the next run reaching a different (unrelated) failure, i.e., this specific error stopped recurring.

---

## INC-10 — Transient 503s had no retry path

**Symptom:** `503 UNAVAILABLE — This model is currently experiencing high demand.` The SDK's own internal retry (via `tenacity`) had already been exhausted by the time this surfaced.

**Investigation:** Confirmed this was Google-side capacity, not an auth or request-shape problem — the error is explicitly described as usually temporary.

**Root Cause:** No application-level retry beyond the SDK's default, and no tolerance for a known-transient failure mode on a free-tier endpoint.

**Fix:** Added `generate_with_retry()` — up to 3 attempts with exponential backoff (15s / 30s / 60s), catching only `google.genai.errors.ServerError` and re-raising immediately on anything else (a bad key or bad model name should fail fast, not retry).

**Verification:** Unit-tested the retry function directly with a mock client that raises `ServerError` twice then succeeds — confirmed it returns the successful result on the third attempt and that a persistent failure still raises after 3 attempts.

---

## INC-11 — Report silently truncated to one paragraph

**Symptom:** The GitHub Issue the pipeline opened contained only an Executive Summary — no findings tables, no remediation list — despite the prompt explicitly requesting five sections.

**Investigation:** Checked the Gemini SDK's config surface for anything that could silently cap output. Found `thinking_config`, a field controlling an internal reasoning pass that shares the same token budget as the visible answer.

**Root Cause:** Newer Gemini models reserve part of `max_output_tokens` for invisible "thinking" by default (`thinking_budget=AUTOMATIC`). With a 2000-token ceiling and 16+ findings needing full tables, the reasoning pass consumed most or all of the budget before the model finished writing — the response hit `MAX_TOKENS` right after the first section.

**Fix:** Attempted `thinking_budget=0` to disable reasoning entirely, and raised the ceiling to 4096.

**Verification:** This fix introduced INC-12 — see below. The eventual working fix (INC-12) was verified against a live pipeline run producing a complete, five-section report.

---

## INC-12 — The fix for #11 broke on the model that caused it

**Symptom:** `400 INVALID_ARGUMENT — Request contains an invalid argument.` — a new failure, immediately after INC-11's fix shipped.

**Investigation:** The only change between the passing run and this one was adding `thinking_config=ThinkingConfig(thinking_budget=0)`. The SDK's own field documentation notes that valid thinking-budget ranges are "model dependent" — `gemini-3.6-flash` apparently doesn't accept a fully-disabled budget.

**Root Cause:** Assumed a parameter value (`0`) was universally valid based on the field's general description, without confirmation for this specific (very new) model.

**Fix:** Removed `thinking_config` entirely rather than guess at a model-specific valid range, and raised `max_output_tokens` to 8192 instead — enough headroom for both an automatic reasoning pass and the full visible report, without depending on an undocumented constraint.

**Verification:** Confirmed via a real pipeline run: the resulting GitHub Issue contained all five required sections, 22 findings across 4 tools, and finding counts that exactly matched the ground-truth counts computed independently in Python (3 + 4 + 9 + 6 = 22).

---

## Verification methodology

A recurring pattern across these fixes, worth naming explicitly: **local reproduction before pushing, wherever possible.**

- Docker/Checkov issues (INC-01, INC-02) were reproduced and re-verified with local `docker build`/`docker run` and a local Checkov install — not by repeatedly pushing and waiting on CI.
- The Gemini integration (INC-04 through INC-12) can't be fully tested without a funded API account, since Anthropic and Gemini both gate the actual model call behind billing/quota. Where the real call couldn't be tested for free, a **mocked dry-run harness** exercised the real, unmodified production code (`ai_triage.py`) against realistically-shaped fixture data, mocking only the two paid/external calls (the LLM API and the GitHub Issues POST). This proved report parsing, prompt construction, and both API call shapes were correct *before* spending anything on a live run — narrowing what a live failure could actually be about.
- Once a funded/free path existed, live runs were polled via GitHub's public Actions API (`/actions/runs`, `/actions/runs/{id}/jobs`) to confirm job-level outcomes, since a workflow's overall "success" can mask an individual job failure under `continue-on-error: true`.
