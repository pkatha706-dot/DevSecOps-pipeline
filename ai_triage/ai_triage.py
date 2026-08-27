import json
import os
import sys
import time
from datetime import datetime, timezone
import requests
from google import genai
from google.genai import errors, types

REPORTS_DIR = os.environ.get("REPORTS_DIR", ".")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # format: owner/repo
GITHUB_SHA = os.environ.get("GITHUB_SHA", "")


def load_reports() -> dict:
    reports = {}
    report_files = {
        "bandit": "bandit-report.json",
        "snyk": "snyk-report.json",
        "trivy": "trivy-report.json",
        "zap": "zap-report.json",
    }
    for tool, filename in report_files.items():
        path = os.path.join(REPORTS_DIR, filename)
        if os.path.exists(path):
            with open(path) as f:
                try:
                    reports[tool] = json.load(f)
                except json.JSONDecodeError:
                    reports[tool] = {"error": f"Failed to parse {filename}"}
        else:
            reports[tool] = {"error": f"{filename} not found"}
    return reports


def _count_findings(reports: dict) -> dict:
    counts = {}

    bandit = reports.get("bandit", {})
    counts["bandit"] = 0 if "error" in bandit else len(bandit.get("results", []))

    snyk = reports.get("snyk", {})
    counts["snyk"] = 0 if "error" in snyk else len(snyk.get("vulnerabilities", []))

    trivy = reports.get("trivy", {})
    if "error" in trivy:
        counts["trivy"] = 0
    else:
        counts["trivy"] = sum(
            len(r.get("Vulnerabilities", [])) for r in trivy.get("Results", [])
        )

    zap = reports.get("zap", {})
    if "error" in zap:
        counts["zap"] = 0
    else:
        alerts = zap.get("site", [{}])[0].get("alerts", []) if zap.get("site") else []
        if not alerts:
            alerts = zap.get("alerts", [])
        counts["zap"] = len(alerts)

    return counts


def build_triage_prompt(reports: dict) -> str:
    bandit_summary = _summarize_bandit(reports.get("bandit", {}))
    snyk_summary = _summarize_snyk(reports.get("snyk", {}))
    trivy_summary = _summarize_trivy(reports.get("trivy", {}))
    zap_summary = _summarize_zap(reports.get("zap", {}))

    counts = _count_findings(reports)
    total = sum(counts.values())

    return f"""You are a senior application security engineer delivering a vulnerability triage report to engineering leadership. Write with the precision and restraint of a professional security assessment: no hedging, no filler, no meta-commentary about the task itself, no conversational openers or closers.

Ground truth finding counts (computed directly from the tool output — use these exact numbers, do not recount): Bandit {counts['bandit']}, Snyk {counts['snyk']}, Trivy {counts['trivy']}, ZAP {counts['zap']} — {total} total.

Below are findings from four security scanning tools. Your task is to:
1. Prioritize findings by combined severity and exploitability (Critical > High > Medium > Low)
2. Identify any findings that are false positives and explain why
3. For each confirmed finding, provide: CVE/ID, tool source, severity, affected component, and a one-sentence remediation
4. Flag any findings that represent immediate production risk
5. Output a structured Markdown report suitable for a GitHub Issue

## Bandit SAST Findings
{bandit_summary}

## Snyk SCA Findings
{snyk_summary}

## Trivy Container Findings
{trivy_summary}

## OWASP ZAP DAST Findings
{zap_summary}

Produce the triage report now. Requirements:
- Every confirmed finding from the sections above must appear in exactly one table row — do not omit or summarize any away.
- Use standard GitHub-Flavored Markdown tables (no bullet lists standing in for tables).
- Do not add sections beyond the structure below, and do not stop early.

Structure, in this exact order:
- ## Executive Summary (2-3 sentences: total findings, single most severe risk, overall posture)
- ## Critical & High Findings (table: ID | Tool | Severity | Component | Remediation)
- ## Medium Findings (table: ID | Tool | Severity | Component | Remediation)
- ## Likely False Positives (list with one-sentence reasoning each, or "None identified.")
- ## Recommended Immediate Actions (numbered list, ordered by priority)
"""


def _summarize_bandit(report: dict) -> str:
    if "error" in report:
        return f"Error loading report: {report['error']}"
    results = report.get("results", [])
    if not results:
        return "No issues found."
    lines = []
    for r in results[:20]:
        lines.append(
            f"- [{r.get('issue_severity', 'UNKNOWN')}] {r.get('issue_text', '')} "
            f"(file: {r.get('filename', '')}, line: {r.get('line_number', '')}, "
            f"test_id: {r.get('test_id', '')})"
        )
    return "\n".join(lines)


def _summarize_snyk(report: dict) -> str:
    if "error" in report:
        return f"Error loading report: {report['error']}"
    vulns = report.get("vulnerabilities", [])
    if not vulns:
        return "No vulnerabilities found."
    lines = []
    for v in vulns[:20]:
        lines.append(
            f"- [{v.get('severity', 'unknown').upper()}] {v.get('title', '')} "
            f"in {v.get('packageName', '')}@{v.get('version', '')} "
            f"(CVE: {', '.join(v.get('identifiers', {}).get('CVE', ['N/A']))})"
        )
    return "\n".join(lines)


def _summarize_trivy(report: dict) -> str:
    if "error" in report:
        return f"Error loading report: {report['error']}"
    results = report.get("Results", [])
    lines = []
    for result in results:
        for vuln in result.get("Vulnerabilities", [])[:20]:
            lines.append(
                f"- [{vuln.get('Severity', 'UNKNOWN')}] {vuln.get('VulnerabilityID', '')} "
                f"in {vuln.get('PkgName', '')}@{vuln.get('InstalledVersion', '')} "
                f"(fixed in: {vuln.get('FixedVersion', 'no fix available')})"
            )
    return "\n".join(lines) if lines else "No vulnerabilities found."


def _summarize_zap(report: dict) -> str:
    if "error" in report:
        return f"Error loading report: {report['error']}"
    alerts = report.get("site", [{}])[0].get("alerts", []) if report.get("site") else []
    if not alerts:
        alerts = report.get("alerts", [])
    if not alerts:
        return "No alerts found."
    lines = []
    for alert in alerts[:20]:
        lines.append(
            f"- [Risk: {alert.get('riskdesc', 'Unknown')}] {alert.get('alert', '')} "
            f"at {alert.get('url', '')} (CWE: {alert.get('cweid', 'N/A')})"
        )
    return "\n".join(lines)


def generate_with_retry(client: genai.Client, max_attempts: int = 3, delay: int = 15, **kwargs):
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(**kwargs)
        except errors.ServerError:
            if attempt == max_attempts:
                raise
            print(f"Gemini overloaded (attempt {attempt}/{max_attempts}), retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2


def build_report_header(reports: dict) -> str:
    counts = _count_findings(reports)
    total = sum(counts.values())
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    repo_line = GITHUB_REPO or "local run"
    commit_line = GITHUB_SHA[:7] if GITHUB_SHA else "n/a"

    return f"""**Repository:** {repo_line}  \n**Commit:** `{commit_line}`  \n**Generated:** {generated_at}  \n**Scanners:** Bandit ({counts['bandit']}) · Snyk ({counts['snyk']}) · Trivy ({counts['trivy']}) · OWASP ZAP ({counts['zap']}) — **{total} total findings**

---

"""


def create_github_issue(markdown: str) -> dict:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GITHUB_TOKEN or GITHUB_REPO not set — skipping issue creation")
        print("\n--- Triage Report ---\n")
        print(markdown)
        return {}

    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": "Security Pipeline Triage Report",
        "body": markdown,
        "labels": ["security"],
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    print(f"GitHub Issue created: {result.get('html_url')}")
    return result


def main():
    reports = load_reports()
    print(f"Loaded reports: {list(reports.keys())}")

    prompt = build_triage_prompt(reports)

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = generate_with_retry(
        client,
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=8192),
    )

    triage_markdown = build_report_header(reports) + response.text
    create_github_issue(triage_markdown)


if __name__ == "__main__":
    main()
