"""
agents/tests/test_developer_agent.py
"""

from __future__ import annotations

from agents.developer_agent import DeveloperAgent
from agents.schemas.common import AgentRequest, AgentStatus


def test_developer_agent_instantiation(fake_llm_factory):
    agent = DeveloperAgent(llm_client=fake_llm_factory())
    assert agent.agent_name == "developer_agent"
    assert "read_file" in agent._tools


def test_developer_agent_accepts_request_and_returns_structured_response(fake_llm_factory):
    canned = {
        "status": "success",
        "result": "def validate_email(email: str) -> bool:\n    return '@' in email",
        "generated_code": "def validate_email(email: str) -> bool:\n    return '@' in email",
        "language": "python",
        "explanation": "Simple presence-of-@ check as a placeholder implementation.",
        "design_notes": ["Real validation should use a proper regex or the `email-validator` package."],
        "confidence": "medium",
        "evidence": [],
        "assumptions": ["No project context was supplied; assumed Python 3."],
        "warnings": [],
    }
    agent = DeveloperAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(query="Create a Python function to validate an email.")

    response = agent.run(request)

    assert response.status == AgentStatus.SUCCESS
    assert response.agent_name == "developer_agent"
    assert response.request_id == request.request_id
    assert "def validate_email" in (response.generated_code or "")
    assert response.execution_time_ms is not None


def test_developer_agent_handles_llm_unavailable(fake_llm_factory):
    agent = DeveloperAgent(llm_client=fake_llm_factory(available=False))
    request = AgentRequest(query="Write a function.")

    response = agent.run(request)

    assert response.status == AgentStatus.ERROR
    assert response.error is not None
    assert response.error.error_type == "LLMUnavailable"


def test_developer_agent_rejects_empty_query(fake_llm_factory):
    agent = DeveloperAgent(llm_client=fake_llm_factory())
    request = AgentRequest(query="   ")

    response = agent.run(request)

    assert response.status == AgentStatus.ERROR
    assert response.error.error_type == "InvalidInput"
