"""
agents/tools/security_tools.py
=================================

Security-related tooling for the Security Agent.

This module provides:
  1. `SecretScanTool` — a genuine, working pattern-based scanner for
     commonly-leaked secrets (API keys, private keys, hardcoded
     passwords, tokens). This is NOT a stub; it actually scans content.
  2. `ExternalScannerProvider` — a clearly-marked integration-point
     interface/stub for plugging in a real SAST tool (e.g. Bandit,
     Semgrep) later, per the "do not fake functionality" requirement:
     we do not pretend to run Semgrep, we expose a clean seam where it
     can be wired in.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult

# A small but genuinely useful set of secret-pattern heuristics.
_SECRET_PATTERNS: List[Dict[str, str]] = [
    {"name": "AWS Access Key ID", "pattern": r"AKIA[0-9A-Z]{16}"},
    {"name": "Generic API Key assignment", "pattern": r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"},
    {"name": "Hardcoded password assignment", "pattern": r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]"},
    {"name": "Private key block", "pattern": r"-----BEGIN (?:RSA|EC|OPENSSH|DSA)?\s?PRIVATE KEY-----"},
    {"name": "Slack token", "pattern": r"xox[baprs]-[0-9A-Za-z-]{10,}"},
    {"name": "Generic bearer token assignment", "pattern": r"(?i)(token|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]"},
    {"name": "JWT-like token", "pattern": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"},
]

_INSECURE_PATTERNS: List[Dict[str, str]] = [
    {"name": "Use of eval()", "pattern": r"\beval\s*\("},
    {"name": "Use of exec()", "pattern": r"\bexec\s*\("},
    {"name": "Shell execution with shell=True", "pattern": r"shell\s*=\s*True"},
    {"name": "Use of pickle.loads on untrusted data", "pattern": r"pickle\.loads\("},
    {"name": "Disabled TLS/SSL verification", "pattern": r"verify\s*=\s*False"},
    {"name": "Weak hash algorithm (MD5/SHA1) for security purposes", "pattern": r"\b(hashlib\.md5|hashlib\.sha1)\("},
    {"name": "SQL query built via string formatting", "pattern": r"(?i)(select|insert|update|delete)\b.{0,80}(%s|\+\s*str\(|f['\"])"},
]


class SecretScanTool(BaseTool):
    operation_type = ToolOperationType.READ
    """Pattern-based scanner for likely hardcoded secrets in source text."""

    name = "scan_for_secrets"
    description = "Scan a block of source code/config text for likely hardcoded secrets using known patterns."

    def run(self, content: str, file_path: str = "<inline>") -> ToolResult:
        findings: List[Dict[str, Any]] = []
        for spec in _SECRET_PATTERNS:
            for match in re.finditer(spec["pattern"], content):
                line_no = content.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "pattern_name": spec["name"],
                        "file": file_path,
                        "line": line_no,
                        "excerpt": content.splitlines()[line_no - 1].strip()[:200]
                        if line_no - 1 < len(content.splitlines())
                        else "",
                    }
                )
        return ToolResult(
            success=True,
            data=findings,
            summary=f"Secret scan found {len(findings)} potential match(es) in {file_path}",
        )


class InsecurePatternScanTool(BaseTool):
    operation_type = ToolOperationType.READ
    """Pattern-based scanner for common insecure coding constructs."""

    name = "scan_insecure_patterns"
    description = "Scan source text for common insecure coding patterns (eval, shell=True, weak hashing, etc.)."

    def run(self, content: str, file_path: str = "<inline>") -> ToolResult:
        findings: List[Dict[str, Any]] = []
        for spec in _INSECURE_PATTERNS:
            for match in re.finditer(spec["pattern"], content):
                line_no = content.count("\n", 0, match.start()) + 1
                lines = content.splitlines()
                findings.append(
                    {
                        "pattern_name": spec["name"],
                        "file": file_path,
                        "line": line_no,
                        "excerpt": lines[line_no - 1].strip()[:200] if line_no - 1 < len(lines) else "",
                    }
                )
        return ToolResult(
            success=True,
            data=findings,
            summary=f"Insecure-pattern scan found {len(findings)} potential match(es) in {file_path}",
        )


class ExternalScannerProvider:
    """
    Integration-point stub for a real SAST tool (e.g. Bandit, Semgrep,
    Trivy) to be wired in later by the Moltress security module.

    IMPORTANT: This class does NOT pretend to run an external scanner.
    Calling `scan()` on the base class explicitly raises
    NotImplementedError so it can never be mistaken for a working
    integration. A concrete subclass should be provided by the module
    that actually shells out to / calls the real scanner.
    """

    name = "external_scanner_provider"

    def scan(self, path: str) -> ToolResult:
        raise NotImplementedError(
            "ExternalScannerProvider is an integration-point stub. "
            "Provide a concrete subclass (e.g. BanditScannerProvider) that "
            "wraps a real SAST tool before using this in production."
        )
