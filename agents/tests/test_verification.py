"""
agents/tests/test_verification.py
==================================

Tests for CodeFactVerificationProvider and anti-hallucination verification layer.
"""

import tempfile
import pytest

from agents.schemas.common import AgentContext, AgentRequest, AgentResponse, Evidence, SourceFile, ToolInvocationRecord
from agents.verification import CodeFactVerificationProvider, DetailedVerificationResult


def test_verification_provider_basic():
    verifier = CodeFactVerificationProvider()

    # Case 1: Valid response with verified syntax and evidence
    response = AgentResponse(
        agent_name="developer_agent",
        request_id="req-101",
        status="success",
        result="def add(a, b):\n    return a + b",
        evidence=[Evidence(source="math_utils.py", reason="Source file")],
        tools_used=[ToolInvocationRecord(tool_name="read_file", success=True)],
    )

    request = AgentRequest(
        query="Refactor add function",
        files=[SourceFile(path="math_utils.py", content="def add(a,b): return a+b")],
    )

    result = verifier.verify(response, request)

    assert isinstance(result, DetailedVerificationResult)
    assert result.verified is True
    assert result.confidence_score >= 0.8
    assert len(result.verified_claims) > 0


def test_verification_provider_syntax_error():
    verifier = CodeFactVerificationProvider()

    # Case 2: Response with invalid Python syntax
    response = AgentResponse(
        agent_name="developer_agent",
        request_id="req-102",
        status="success",
        result="def broken_func(:\n    return 42",  # invalid syntax
    )

    request = AgentRequest(query="Write broken function")
    result = verifier.verify(response, request)

    assert result.verified is False
    assert any("syntax error" in claim.lower() for claim in result.unverified_claims)
