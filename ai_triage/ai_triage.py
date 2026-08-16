import json
import os
import sys
import requests
import anthropic

REPORTS_DIR = os.environ.get("REPORTS_DIR", ".")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # format: owner/repo


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


def build_triage_prompt(reports: dict) -> str:
    bandit_summary = _summarize_bandit(reports.get("bandit", {}))
    snyk_summary = _summarize_snyk(reports.get("snyk", {}))
    trivy_summary = _summarize_trivy(reports.get("trivy", {}))
    zap_summary = _summarize_zap(reports.get("zap", {}))

    return f"""You are a senior application security engineer performing vulnerability triage for a DevSecOps pipeline.

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

Produce the triage report now. Use this structure:
- ## Executive Summary (2-3 sentences)
- ## Critical & High Findings (table with columns: ID | Tool | Severity | Component | Remediation)
- ## Medium Findings (table)
- ## Likely False Positives (list with reasoning)
- ## Recommended Immediate Actions (numbered list)
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

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    triage_markdown = message.content[0].text
    create_github_issue(triage_markdown)


if __name__ == "__main__":
    main()
