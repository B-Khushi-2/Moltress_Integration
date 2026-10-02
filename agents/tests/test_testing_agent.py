"""
agents/tests/test_testing_agent.py
"""

from __future__ import annotations

from agents.testing_agent import TestingAgent
from agents.schemas.common import AgentRequest, AgentStatus


def test_testing_agent_instantiation(fake_llm_factory):
    agent = TestingAgent(llm_client=fake_llm_factory())
    assert agent.agent_name == "testing_agent"


def test_testing_agent_generates_tests(fake_llm_factory):
    canned = {
        "status": "success",
        "test_file_name": "test_add.py",
        "generated_tests": [
            {
                "name": "test_add_positive_numbers",
                "description": "Adding two positive integers returns their sum.",
                "test_type": "unit",
                "code": "def test_add_positive_numbers():\n    assert add(2, 3) == 5",
            },
            {
                "name": "test_add_with_zero",
                "description": "Adding zero returns the other operand unchanged.",
                "test_type": "edge_case",
                "code": "def test_add_with_zero():\n    assert add(5, 0) == 5",
            },
        ],
        "identified_edge_cases": ["zero", "negative numbers", "very large numbers (overflow, if applicable)"],
        "coverage_notes": "Covers the happy path and a basic edge case; negative-number case not yet covered.",
        "confidence": "medium",
        "evidence": [],
        "assumptions": ["Assumed pytest since no test framework was specified."],
        "warnings": [],
    }
    agent = TestingAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(query="Write unit tests for this add(a, b) function.", code="def add(a, b):\n    return a + b")

    response = agent.run(request)

    assert response.status == AgentStatus.SUCCESS
    assert len(response.generated_tests) == 2
    assert response.execution_result is None  # test execution not enabled by default


def test_testing_agent_handles_llm_unavailable(fake_llm_factory):
    agent = TestingAgent(llm_client=fake_llm_factory(available=False))
    request = AgentRequest(query="Write tests for this function.")

    response = agent.run(request)

    assert response.status == AgentStatus.ERROR
    assert response.error.error_type == "LLMUnavailable"
