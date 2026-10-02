"""
agents/tests/test_handoff_and_orchestrator.py
================================================

Tests for HandoffPayload, OrchestrationTaskState, and AgentOrchestrator.
"""

import tempfile
import pytest

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.handoff import HandoffPayload, OrchestrationTaskState
from agents.orchestrator import AgentOrchestrator
from agents.schemas.common import AgentRequest
from agents.tests.conftest import FakeOllamaClient


def test_handoff_payload_and_state():
    state = OrchestrationTaskState(original_query="Fix login KeyError")
    payload = state.create_handoff(
        from_agent="debugging_agent",
        to_agent="developer_agent",
        summary="KeyError in login.py",
        root_cause="users[username] un-guarded lookup",
        suggested_fix="Use users.get(username)",
    )

    assert payload.from_agent == "debugging_agent"
    assert payload.to_agent == "developer_agent"
    assert state.latest_handoff() == payload
    assert len(state.handoffs) == 1


def test_orchestrator_debug_fix_test_pipeline(fake_llm_factory):
    # Canned responses for the three turns in the pipeline
    canned_responses = [
        # DebuggingAgent response
        {
            "status": "success",
            "result": "KeyError: 'carol' in login.py",
            "explanation": "login() directly indexes dict without guard.",
            "root_cause": "Direct indexing users[username]",
            "suggested_fix": "Use users.get(username, False)",
            "confidence": "high",
        },
        # DeveloperAgent response
        {
            "status": "success",
            "result": "def login(u, p):\n    return users.get(u) == p",
            "explanation": "Replaced direct indexing with dict.get()",
            "generated_code": "def login(u, p):\n    return users.get(u) == p",
            "confidence": "high",
        },
        # TestingAgent response
        {
            "status": "success",
            "result": "Generated test_login.py",
            "generated_tests": [
                {"name": "test_login_unknown_user", "test_type": "unit", "code": "assert not login('carol', 'pass')"}
            ],
            "confidence": "high",
        },
    ]

    llm = FakeOllamaClient(canned_responses=canned_responses)

    with tempfile.TemporaryDirectory() as project_root:
        config = AgentConfig(
            tools=ToolConfig(project_root=project_root),
            orchestration=OrchestrationConfig(max_tool_iterations=3),
        )
        orchestrator = AgentOrchestrator(llm_client=llm, config=config)

        request = AgentRequest(query="Why is login crashing with KeyError: 'carol'?")
        orch_state = orchestrator.run_debug_fix_test_pipeline(request, auto_approve_dev_write=True)

        assert orch_state.status == "completed"
        assert len(orch_state.pipeline_steps) == 3
        assert orch_state.pipeline_steps == ["debugging_agent", "developer_agent", "testing_agent"]
        assert len(orch_state.handoffs) == 2
        assert "Debugging Agent" in orch_state.final_output
