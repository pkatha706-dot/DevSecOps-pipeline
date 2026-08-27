# Building the DevSecOps Pipeline on GitHub — Step-by-Step Guide

This guide walks through taking the project in this folder — a vulnerable Flask app, an 8-stage GitHub Actions security pipeline, an AI triage agent, and an MCP server — from local files to a working, running pipeline on GitHub. Each step explains not just *what* to do but *why* it matters, so the underlying application security concepts stick.

---

## Part 1: The Core Idea

Traditional software security works like a final inspection: developers write code for months, then a security team reviews it right before release. Problems found that late are expensive to fix and create bottlenecks. **DevSecOps** folds security into the development pipeline itself — every `git push` triggers automated scanners that catch problems in minutes, not months.

This project is a working example of that idea. It has two halves:

1. **A deliberately vulnerable target** (`app/app.py`) — a small Flask app with real, common vulnerabilities baked in on purpose, so there's something for the scanners to actually find.
2. **A security pipeline** (`.github/workflows/devsecops.yml`) — eight sequential stages that scan the code, its dependencies, its container, and its running behavior, then feed the results to an AI agent that triages what matters.

The concept to internalize here is **shift-left security**: pushing security checks as early as possible in the development lifecycle, rather than bolting them on at the end.

---

## Part 2: What's Already Built

Your repo currently has:

| Path | Purpose |
|---|---|
| `app/app.py` | Vulnerable Flask app — SQL injection in `/search`, hardcoded secret key |
| `app/requirements.txt` | Dependencies, including `requests==2.25.0` (has a known CVE for Snyk to catch) |
| `Dockerfile` | Multi-stage build, runs as non-root user |
| `.github/workflows/devsecops.yml` | The 8-stage pipeline |
| `ai_triage/ai_triage.py` | Reads scanner JSON reports, calls Claude to prioritize findings, opens a GitHub Issue |
| `security_tools_mcp/server.py` | Exposes the scanners as MCP tools so an AI coding assistant can call them directly |

Nothing has been pushed to GitHub yet — the repo exists locally with a remote configured (`github.com/pkatha706-dot/DevSecOps-pipeline`) but no commits.

---

## Part 3: Step-by-Step Build

### Step 1 — Understand the vulnerable app before you scan it

Open `app/app.py`. Two things are intentionally wrong:

- **SQL Injection (`/search` route):** the username from the URL is dropped straight into a SQL string with an f-string: `f"SELECT ... WHERE username = '{username}'"`. A request like `/search?username=' OR '1'='1` closes the quote early and turns the query into "return every row." This is CWE-89, and it's the same class of bug behind breaches like the 2017 Equifax and 2015 TalkTalk incidents.
- **Hardcoded secret (`SECRET_KEY`):** the Flask session-signing key is a literal string in the source file. Anyone who reads the code — or finds it in git history — can forge signed session cookies. This is CWE-798.

**Concept to learn:** OWASP Top 10, specifically A03 (Injection) and A02 (Cryptographic Failures). Knowing these categories cold is table stakes for any AppSec interview.

### Step 2 — Commit the project

From the project root:

```bash
git add .
git commit -m "Initial DevSecOps pipeline: vulnerable app, 8-stage scan, AI triage, MCP server"
```

**Concept to learn:** why the commit matters for Stage 1. TruffleHog (the first pipeline stage) scans the *entire git history*, not just the current file state. If you'd hardcoded a real secret at some point and later deleted it, it would still be recoverable from an earlier commit — this is why secret scanning has to look at history, not just HEAD.

### Step 3 — Push to GitHub

```bash
git branch -M main
git push -u origin main
```

This pushes to the `origin` remote already configured (`github.com/pkatha706-dot/DevSecOps-pipeline`). The push itself is what triggers the pipeline — look at `.github/workflows/devsecops.yml`:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

**Concept to learn:** GitHub Actions triggers (`on:`). This one fires on every push to `main` and every PR targeting `main` — meaning even a proposed change gets scanned before it's merged, not just after.

### Step 4 — Configure required secrets

GitHub Actions needs credentials to run some of these scanners. In your repo: **Settings → Secrets and variables → Actions → New repository secret.**

| Secret | Why it's needed |
|---|---|
| `SNYK_TOKEN` | Authenticates the Snyk SCA scan against Snyk's CVE database (free account at snyk.io) |
| `ANTHROPIC_API_KEY` | Lets `ai_triage.py` call Claude to generate the prioritized findings report |
| `GITHUB_TOKEN` | Already provided automatically by Actions — no setup needed, used to open the triage issue |

**Concept to learn:** why secrets live in GitHub's encrypted secret store instead of the repo itself. This is the correct pattern that Stage 1 (TruffleHog) exists to enforce — if you ever see yourself typing a real key into a file, that's the exact behavior this pipeline is designed to catch.

### Step 5 — Watch the pipeline run, stage by stage

Go to the **Actions** tab in your GitHub repo after the push. You'll see the 8 jobs execute in sequence (each `needs:` the previous one, so a failure stops the chain):

1. **Secret scan (TruffleHog)** — walks git history for credentials.
2. **SAST (Bandit)** — parses the Python source into an abstract syntax tree and flags dangerous patterns (SQL string concatenation, `eval()`, weak crypto). This is *static* analysis — it never runs the code.
3. **SCA (Snyk)** — checks `requirements.txt` against a CVE database. This is why `requests==2.25.0` was pinned deliberately — it's known-vulnerable, so this stage has something real to report.
4. **IaC scan (Checkov)** — checks the Dockerfile itself for misconfigurations (running as root, missing `HEALTHCHECK`, etc.) before anything is even built.
5. **Docker build** — builds the image and saves it as a pipeline artifact so later stages don't have to rebuild it.
6. **Container scan (Trivy)** — scans the *built image*, catching OS-level CVEs in the base image layers that Bandit and Snyk can't see (they only look at your Python code, not what's inside `python:3.11-slim`).
7. **Deploy for DAST** — starts the container and waits for the `/health` endpoint to respond, confirming the app is actually reachable (this is the stage that depended on the `0.0.0.0` bind fix).
8. **DAST (OWASP ZAP)** — sends real HTTP traffic at the *running* app: SQLi probes, XSS payloads, header injection attempts. This is dynamic analysis — it doesn't read source code, it attacks the live app the way a real attacker would.

**Concept to learn:** the difference between SAST, SCA, and DAST is one of the most commonly tested distinctions in AppSec interviews:
- **SAST** reads source code without running it (Bandit).
- **SCA** checks third-party dependencies for known CVEs (Snyk).
- **DAST** attacks the running application externally, with no knowledge of the source (ZAP).

Each catches a different class of bug — which is why real pipelines run all three rather than picking one.

### Step 6 — Read the artifacts

Each stage uploads its findings as a downloadable JSON artifact (visible at the bottom of the workflow run page): `bandit-report.json`, `snyk-report.json`, `checkov-report.json`, `trivy-report.json`, `zap-report.json` (or similarly named). These are the raw inputs the AI triage agent consumes next.

### Step 7 — Run the AI triage agent

`ai_triage/ai_triage.py` reads all the scanner outputs, builds a single prompt combining them, and asks Claude to produce one prioritized report — critical findings first, with specific remediation steps — then opens it as a GitHub Issue labeled `security`.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export GITHUB_TOKEN=ghp_...
export GITHUB_REPO=pkatha706-dot/DevSecOps-pipeline
python ai_triage/ai_triage.py
```

**Concept to learn:** *vulnerability triage*. In a real environment, four different scanners can flag the same underlying bug in four different ways, with no ranking. A human (or here, an LLM) has to correlate them, decide what's actually exploitable versus noise, and produce one clear action list. This is what separates "the pipeline ran" from "the finding actually got fixed."

### Step 8 — Try the MCP server (optional, but the most distinctive piece)

`security_tools_mcp/server.py` wraps Bandit, Snyk, and Trivy as callable tools using the Model Context Protocol, so an AI coding assistant (Claude Desktop, for example) can run these scanners *during development*, before code is even pushed — not just after, in CI.

```bash
python security_tools_mcp/server.py
```

Point Claude Desktop at it via `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "security-tools": {
      "command": "python",
      "args": ["/absolute/path/to/security_tools_mcp/server.py"]
    }
  }
}
```

**Concept to learn:** MCP (Model Context Protocol) is how AI assistants call external tools in a standardized way — the same pattern this very conversation is built on. Exposing security scanners as MCP tools means an AI assistant can answer "is this code safe?" by actually running Bandit, not by guessing from training data.

---

## Part 4: Reading the Results Like a Security Engineer

When a stage fails, don't just re-run it — read the artifact. Ask:

- **Is this a true positive or noise?** (Bandit and ZAP both produce false positives; part of the job is knowing which findings are real.)
- **What's the actual impact if left unfixed?** (An unauthenticated SQLi that dumps the whole database is very different from a low-confidence "possible" issue.)
- **What's the minimal fix?** (Parameterized queries for SQLi, not "delete the search feature.")

This is the mental model the AI triage agent is automating — but understanding it yourself is what makes the project defensible in an interview, not just something that runs.

---

## Part 5: Quick Reference — Concepts Covered

| Concept | Where it shows up |
|---|---|
| Shift-left security | The whole pipeline design |
| OWASP Top 10 | SQLi and hardcoded secret in `app.py` |
| Git history vs. working tree | Why TruffleHog scans full history |
| SAST vs. SCA vs. DAST | Stages 2, 3, and 8 |
| Container vs. code vulnerabilities | Trivy (Stage 6) vs. Bandit (Stage 2) |
| IaC scanning | Checkov (Stage 4) |
| CI/CD pipeline gating | `needs:` dependencies between jobs |
| Vulnerability triage/prioritization | `ai_triage.py` |
| MCP (Model Context Protocol) | `security_tools_mcp/server.py` |

---

## Next Steps

Once this is pushed and running green (or intentionally red on the vulnerable stages), the natural additions are: fixing the vulnerabilities on a separate `remediated` branch to show before/after, and writing a short README section walking through one finding end-to-end (scanner output → triage → fix). Both make the project easier to talk through live in an interview.
