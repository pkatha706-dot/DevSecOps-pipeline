# DevSecOps Pipeline — Portfolio Project

Demonstrates automated security scanning, AI-assisted triage, and MCP-based security tooling for early-career Security Engineer roles.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        GitHub Repository                             │
│                                                                      │
│   app/app.py  (vulnerable Flask app — intentional findings)          │
│   Dockerfile  (multi-stage, non-root)                                │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ git push
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   GitHub Actions CI/CD Pipeline                      │
│                                                                      │
│  Stage 1: TruffleHog ──► secret scan (full git history)             │
│      │                                                               │
│  Stage 2: Bandit ──────► SAST (Python code)  → bandit-report.json   │
│      │                                                               │
│  Stage 3: Snyk ────────► SCA (dependencies)  → snyk-report.json     │
│      │                                                               │
│  Stage 4: Checkov ─────► IaC (Dockerfile)    → checkov-report.json  │
│      │                                                               │
│  Stage 5: Docker Build ► image artifact       → .tar.gz             │
│      │                                                               │
│  Stage 6: Trivy ───────► container scan       → trivy-report.json   │
│      │                                                               │
│  Stage 7: Deploy ──────► docker run -p 5000                         │
│      │                                                               │
│  Stage 8: OWASP ZAP ──► DAST baseline scan   → zap-report.json     │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ reports downloaded
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│              AI Triage Agent (ai_triage/ai_triage.py)                │
│                                                                      │
│  load_reports() → build_triage_prompt() → Gemini 3.6 Flash          │
│       → prioritized Markdown report → GitHub Issue (label: security) │
└──────────────────────────────────────────────────────────────────────┘
                       │ parallel / ad-hoc
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│          MCP Security Tools Server (security_tools_mcp/server.py)    │
│                                                                      │
│  run_bandit()  · run_snyk()  · run_trivy()  · explain_vulnerability()│
└──────────────────────────────────────────────────────────────────────┘
                       │ supply chain
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│           SBOM Generation (supply_chain/generate_sbom.sh)            │
│                                                                      │
│  syft → sbom.json (SPDX)  →  cosign sign-blob → sbom.json.sig       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Tool Reference

| Tool | Role |
|---|---|
| **TruffleHog** | Scans full git history for leaked secrets and credentials |
| **Bandit** | Static analysis of Python source code for common security issues (CWE mapping) |
| **Snyk** | Software Composition Analysis — finds CVEs in open-source dependencies |
| **Checkov** | Infrastructure-as-Code scan — checks Dockerfile and IaC configs against security policies |
| **Trivy** | Scans the built container image for OS and library CVEs |
| **OWASP ZAP** | Dynamic Application Security Testing — active baseline scan against the running app |
| **Gemini (Google)** | AI triage agent that prioritizes findings across all scanners and drafts a GitHub Issue |
| **MCP FastMCP** | Exposes security scanner tools as MCP-protocol endpoints for Claude or other LLM agents |
| **Syft** | Generates a Software Bill of Materials (SBOM) in SPDX JSON format |
| **Cosign** | Signs the SBOM blob to establish supply chain provenance |

---

## Running Locally

### Prerequisites

```bash
pip install flask bandit google-genai mcp requests
# install snyk CLI, trivy, syft, cosign via their respective install docs
```

### Start the vulnerable app

```bash
cd app
python app.py
# App runs at http://localhost:5000
```

### Trigger SQL injection manually

```bash
curl "http://localhost:5000/search?username=' OR '1'='1"
```

### Run SAST

```bash
bandit -r app/ --severity-level medium --format json
```

### Run AI triage (requires reports to exist)

```bash
export GEMINI_API_KEY=AIza...
export GITHUB_TOKEN=ghp_...
export GITHUB_REPO=yourname/devsecops-pipeline
python ai_triage/ai_triage.py
```

### Start the MCP server

```bash
export GEMINI_API_KEY=AIza...
python security_tools_mcp/server.py
```

### Generate and sign SBOM

```bash
export COSIGN_KEY="$(cat cosign.key)"
bash supply_chain/generate_sbom.sh devsecops-app:latest
```

---

## OWASP DevSecOps Maturity Model (DSOMM) Mapping

| DSOMM Activity | Pipeline Implementation |
|---|---|
| **Secret Management (Level 1)** | TruffleHog scans full git history on every push |
| **Static Analysis (Level 2)** | Bandit runs on Python source with medium+ severity threshold |
| **Software Composition Analysis (Level 2)** | Snyk flags high-severity CVEs in dependencies |
| **Infrastructure Hardening (Level 2)** | Checkov validates Dockerfile against CIS benchmarks |
| **Container Security (Level 3)** | Trivy scans the built image for critical/high CVEs |
| **Dynamic Analysis (Level 3)** | OWASP ZAP baseline scan against the live running container |
| **Vulnerability Management (Level 3)** | AI triage agent (Gemini) cross-correlates all scanner outputs into a prioritized GitHub Issue |
| **Supply Chain Security (Level 4)** | Syft generates SPDX SBOM; Cosign signs for provenance |

---

## Required GitHub Secrets

| Secret | Purpose |
|---|---|
| `SNYK_TOKEN` | Authenticate Snyk SCA scans |
| `GITHUB_TOKEN` | Post triage findings as GitHub Issues (auto-provided by Actions) |
| `GEMINI_API_KEY` | Gemini API access for AI triage and MCP explain tool |
| `COSIGN_KEY` | Private key for signing the SBOM |
