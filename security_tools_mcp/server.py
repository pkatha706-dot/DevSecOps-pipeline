import json
import os
import subprocess
import anthropic
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("security-tools")


@mcp.tool()
def run_bandit(path: str, severity: str = "medium") -> str:
    """Run Bandit SAST scan on a Python path and return JSON findings."""
    severity_map = {"low": "l", "medium": "m", "high": "h"}
    level_flag = severity_map.get(severity.lower(), "m")

    result = subprocess.run(
        ["bandit", "-r", path, f"-l{level_flag}", "--format", "json"],
        capture_output=True,
        text=True,
    )
    output = result.stdout or result.stderr
    try:
        return json.dumps(json.loads(output), indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse Bandit output", "raw": output})


@mcp.tool()
def run_snyk(requirements_path: str) -> str:
    """Run Snyk SCA test on a requirements file and return JSON findings."""
    snyk_token = os.environ.get("SNYK_TOKEN", "")
    env = {**os.environ, "SNYK_TOKEN": snyk_token}

    result = subprocess.run(
        ["snyk", "test", "--file", requirements_path, "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    output = result.stdout or result.stderr
    try:
        return json.dumps(json.loads(output), indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse Snyk output", "raw": output})


@mcp.tool()
def run_trivy(image_name: str) -> str:
    """Run Trivy container image scan and return JSON findings."""
    result = subprocess.run(
        [
            "trivy",
            "image",
            "--format", "json",
            "--severity", "CRITICAL,HIGH",
            "--ignore-unfixed",
            image_name,
        ],
        capture_output=True,
        text=True,
    )
    output = result.stdout or result.stderr
    try:
        return json.dumps(json.loads(output), indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse Trivy output", "raw": output})


@mcp.tool()
def explain_vulnerability(vulnerability_id: str, context: str = "") -> str:
    """Use Claude to explain a vulnerability in plain English for a developer audience."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""You are a security engineer explaining vulnerabilities to developers.

Vulnerability ID: {vulnerability_id}
Additional context: {context if context else 'None provided'}

Explain this vulnerability in plain English covering:
1. What it is (one sentence)
2. How an attacker could exploit it (concrete example)
3. What the impact is (confidentiality/integrity/availability)
4. How to fix it (specific code-level recommendation)

Keep the explanation under 300 words. Use developer-friendly language, not academic security jargon."""

    message = client.messages.create(
        model="claude-opus-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


if __name__ == "__main__":
    mcp.run()
