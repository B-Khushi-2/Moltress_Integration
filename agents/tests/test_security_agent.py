"""
agents/tests/test_security_agent.py
"""

from __future__ import annotations

from agents.security_agent import SecurityAgent
from agents.tools.security_tools import SecretScanTool, InsecurePatternScanTool
from agents.schemas.common import AgentRequest, AgentStatus

INSECURE_CODE = """
import subprocess

AWS_KEY = "AKIAABCDEFGHIJKLMNOP"

def run(cmd):
    subprocess.run(cmd, shell=True)
"""


def test_security_agent_instantiation(fake_llm_factory):
    agent = SecurityAgent(llm_client=fake_llm_factory())
    assert agent.agent_name == "security_agent"


def test_security_agent_reports_findings(fake_llm_factory):
    canned = {
        "status": "success",
        "findings": [
            {
                "vulnerability": "Hardcoded AWS credential",
                "severity": "critical",
                "affected_area": "app.py:3",
                "explanation": "An AWS access key is hardcoded in source, risking credential leakage via VCS.",
                "recommended_fix": "Move the credential to a secret manager or environment variable.",
                "confidence": 0.9,
                "cwe_reference": "CWE-798",
            },
            {
                "vulnerability": "Shell injection risk (shell=True)",
                "severity": "high",
                "affected_area": "app.py:6",
                "explanation": "subprocess.run with shell=True and an unsanitized `cmd` argument risks command injection.",
                "recommended_fix": "Use shell=False and pass command arguments as a list.",
                "confidence": 0.75,
            },
        ],
        "overall_risk_summary": "Two significant issues found; static review only, no dynamic testing performed.",
        "scanned_files": ["app.py"],
        "confidence": "medium",
        "evidence": [],
        "assumptions": [],
        "warnings": ["This review is not exhaustive and does not guarantee the code is secure."],
    }
    agent = SecurityAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(query="Check this code for security vulnerabilities.", code=INSECURE_CODE)

    response = agent.run(request)

    assert response.status == AgentStatus.SUCCESS
    assert len(response.findings) == 2
    assert response.findings[0].severity == "critical"


def test_secret_scan_tool_detects_aws_key():
    tool = SecretScanTool()
    result = tool.safe_run(content=INSECURE_CODE, file_path="app.py")
    assert result.success
    assert any(f["pattern_name"] == "AWS Access Key ID" for f in result.data)


def test_insecure_pattern_scan_tool_detects_shell_true():
    tool = InsecurePatternScanTool()
    result = tool.safe_run(content=INSECURE_CODE, file_path="app.py")
    assert result.success
    assert any(f["pattern_name"] == "Shell execution with shell=True" for f in result.data)
