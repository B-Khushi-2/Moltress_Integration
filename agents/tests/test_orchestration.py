"""
agents/tests/test_orchestration.py

Tests for the v2 controlled, iterative tool-use loop in BaseAgent:
  - genuine multi-turn tool use (LLM requests a tool, gets a REAL result,
    then answers)
  - tool permission enforcement (agents only get their allowed tools)
  - destructive-tool approval gating (write_file)
  - max-iteration stop condition
  - consecutive-tool-failure stop condition
  - duplicate tool-call detection
  - unknown/unregistered tool handling
  - RAG / Knowledge Graph / Memory context auto-injection
  - VerificationProvider invocation (including failure isolation)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.debugging_agent import DebuggingAgent
from agents.developer_agent import DeveloperAgent
from agents.providers import (
    GraphProvider,
    MemoryProvider,
    RAGProvider,
    VerificationProvider,
    VerificationResult,
)
from agents.schemas.common import (
    AgentRequest,
    AgentStatus,
    GraphRelationship,
    MemoryEntry,
    RetrievedDocument,
)


@pytest.fixture
def sandbox_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("def compute_average(values):\n    return sum(values) / len(values)\n")
        yield tmp


# ---------------------------------------------------------------------------
# Genuine multi-turn tool use
# ---------------------------------------------------------------------------

def test_agent_performs_real_multi_turn_tool_use(fake_llm_factory, sandbox_dir):
    """The agent should actually execute the requested tool and use its
    REAL result on the next turn — not simulate it."""
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    responses = [
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "inspect"},
        {
            "status": "success",
            "error_summary": "ZeroDivisionError on empty input.",
            "most_probable_cause": "Empty list passed to compute_average.",
            "confidence": "high",
            "evidence": [], "assumptions": [], "warnings": [],
        },
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DebuggingAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Why does this raise ZeroDivisionError?"))

    assert response.status == AgentStatus.SUCCESS
    assert llm.call_count == 2  # one tool-call turn, one final-answer turn
    assert len(response.tools_used) == 1
    assert response.tools_used[0].tool_name == "read_file"
    assert response.tools_used[0].success is True
    second_call_messages = llm.call_log[1]["messages"]
    assert any("compute_average" in m.content for m in second_call_messages)


def test_single_shot_response_still_works_without_any_tool_call(fake_llm_factory):
    """Backward compatibility: a canned response with no 'action' field is
    treated as the final answer on the very first turn (v1 behavior)."""
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm)

    response = agent.run(AgentRequest(query="hello"))

    assert response.status == AgentStatus.SUCCESS
    assert llm.call_count == 1
    assert response.tools_used == []


# ---------------------------------------------------------------------------
# Tool permissions
# ---------------------------------------------------------------------------

def test_agent_only_registers_its_allowed_tools(fake_llm_factory):
    agent = DeveloperAgent(llm_client=fake_llm_factory())
    assert set(agent._tools.keys()) <= set(DeveloperAgent.allowed_tool_names)
    assert "scan_for_secrets" not in agent._tools  # security-only tool


def test_debugging_agent_does_not_get_write_file(fake_llm_factory):
    agent = DebuggingAgent(llm_client=fake_llm_factory())
    assert "write_file" not in agent._tools


def test_write_file_tool_not_registered_unless_explicitly_enabled(fake_llm_factory):
    agent = DeveloperAgent(llm_client=fake_llm_factory())  # default config: enable_write_tool=False
    assert "write_file" not in agent._tools


def test_write_file_tool_registers_when_enabled(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir, enable_write_tool=True))
    agent = DeveloperAgent(llm_client=fake_llm_factory(), config=cfg)
    assert "write_file" in agent._tools


# ---------------------------------------------------------------------------
# Destructive-tool approval gating
# ---------------------------------------------------------------------------

def test_write_file_denied_without_approval(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir, enable_write_tool=True))
    responses = [
        {"action": "use_tool", "tool_name": "write_file", "tool_arguments": {"path": "x.py", "content": "y=1"}, "reasoning": "apply fix"},
        {"status": "success", "result": "done", "confidence": "low", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Fix and write it"))  # no approved_actions

    assert response.status == AgentStatus.SUCCESS
    call = response.tools_used[0]
    assert call.tool_name == "write_file"
    assert call.success is False
    assert call.denied is True
    assert not os.path.exists(os.path.join(sandbox_dir, "x.py"))  # nothing was actually written


def test_write_file_executes_when_approved(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir, enable_write_tool=True))
    responses = [
        {"action": "use_tool", "tool_name": "write_file", "tool_arguments": {"path": "x.py", "content": "y=1\n"}, "reasoning": "apply fix"},
        {"status": "success", "result": "done", "confidence": "medium", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Fix and write it", approved_actions=["write_file"]))

    assert response.status == AgentStatus.SUCCESS
    call = response.tools_used[0]
    assert call.tool_name == "write_file"
    assert call.success is True
    assert call.denied is False
    with open(os.path.join(sandbox_dir, "x.py")) as f:
        assert f.read() == "y=1\n"


# ---------------------------------------------------------------------------
# Stop conditions
# ---------------------------------------------------------------------------

def test_max_iterations_stop_condition(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir),
        orchestration=OrchestrationConfig(max_tool_iterations=2, max_consecutive_tool_failures=10),
    )
    responses = [
        {"action": "use_tool", "tool_name": "inspect_project", "tool_arguments": {"directory": "."}, "reasoning": "a"},
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "b"},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Keep exploring forever"))

    assert response.status == AgentStatus.PARTIAL
    assert "maximum" in response.explanation.lower()
    assert any("iteration" in w.lower() for w in response.warnings)
    assert llm.call_count == 2


def test_consecutive_tool_failure_stop_condition(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir),
        orchestration=OrchestrationConfig(max_tool_iterations=10, max_consecutive_tool_failures=2),
    )
    bad_call = {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "nope1.py"}, "reasoning": "x"}
    bad_call_2 = {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "nope2.py"}, "reasoning": "y"}
    llm = fake_llm_factory(canned_responses=[bad_call, bad_call_2])
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Read a missing file"))

    assert response.status == AgentStatus.PARTIAL
    assert "failure" in response.explanation.lower()
    assert all(not t.success for t in response.tools_used)


def test_duplicate_tool_call_is_rejected(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir),
        orchestration=OrchestrationConfig(max_tool_iterations=5, max_consecutive_tool_failures=10),
    )
    same_call = {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "x"}
    final = {"status": "success", "result": "done", "confidence": "low", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_responses=[same_call, same_call, final])
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="Read app.py twice"))

    assert response.tools_used[0].success is True
    assert response.tools_used[1].success is False
    assert response.tools_used[1].denied is True


def test_unregistered_tool_request_is_handled_gracefully(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    responses = [
        {"action": "use_tool", "tool_name": "scan_for_secrets", "tool_arguments": {"content": "x"}, "reasoning": "z"},
        {"status": "success", "result": "done", "confidence": "low", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)  # DeveloperAgent has no security tools

    response = agent.run(AgentRequest(query="Scan this for secrets"))

    assert response.status == AgentStatus.SUCCESS  # agent recovers and still answers
    assert response.tools_used[0].tool_name == "scan_for_secrets"
    assert response.tools_used[0].success is False


# ---------------------------------------------------------------------------
# RAG / Knowledge Graph / Memory context injection
# ---------------------------------------------------------------------------

class _FakeRAG(RAGProvider):
    def retrieve(self, query, project_root=None, top_k=5):
        return [RetrievedDocument(source="style_guide.md", content="Use snake_case.", score=0.9)]


class _FakeGraph(GraphProvider):
    def get_relationships(self, entity, depth=1):
        return [GraphRelationship(subject="ServiceA", relation="depends_on", target="DatabaseB")]


class _FakeMemory(MemoryProvider):
    def get_recent(self, session_id, limit=10):
        return [MemoryEntry(role="user", content="Earlier we agreed to use pytest.")]

    def append(self, session_id, entry):
        pass


def test_rag_context_is_injected_when_enabled(fake_llm_factory):
    cfg = AgentConfig(rag_enabled=True)
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, config=cfg, rag_provider=_FakeRAG())

    request = AgentRequest(query="Write a function")
    agent.run(request)

    assert len(request.context.retrieved_documents) == 1
    assert "style_guide.md" in llm.call_log[0]["messages"][0].content


def test_graph_context_is_injected_when_enabled(fake_llm_factory):
    cfg = AgentConfig(graph_enabled=True)
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, config=cfg, graph_provider=_FakeGraph())

    request = AgentRequest(query="Write a function")
    agent.run(request)

    assert len(request.context.graph_context) == 1
    assert "ServiceA" in llm.call_log[0]["messages"][0].content


def test_memory_context_is_injected_when_enabled(fake_llm_factory):
    cfg = AgentConfig(memory_enabled=True)
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, config=cfg, memory_provider=_FakeMemory())

    request = AgentRequest(query="Write a function")
    agent.run(request)

    assert len(request.context.memory) == 1
    assert "pytest" in llm.call_log[0]["messages"][0].content


def test_context_not_auto_injected_when_flags_disabled(fake_llm_factory):
    """Default config has rag/graph/memory disabled -> providers must not be called."""
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, rag_provider=_FakeRAG())  # rag_enabled defaults False

    request = AgentRequest(query="Write a function")
    agent.run(request)

    assert request.context.retrieved_documents == []


def test_user_supplied_context_is_not_overwritten_by_providers(fake_llm_factory):
    cfg = AgentConfig(rag_enabled=True)
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, config=cfg, rag_provider=_FakeRAG())

    request = AgentRequest(query="Write a function")
    request.context.retrieved_documents = [RetrievedDocument(source="user_supplied.md", content="pre-existing")]
    agent.run(request)

    assert len(request.context.retrieved_documents) == 1
    assert request.context.retrieved_documents[0].source == "user_supplied.md"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class _FakeVerification(VerificationProvider):
    def verify(self, response, context):
        return VerificationResult(verified=True, notes="ok")


class _BrokenVerification(VerificationProvider):
    def verify(self, response, context):
        raise RuntimeError("verification backend down")


def test_verification_provider_result_is_attached(fake_llm_factory):
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, verification_provider=_FakeVerification())

    response = agent.run(AgentRequest(query="hi"))

    assert response.metadata["verification"] == {"verified": True, "notes": "ok"}


def test_verification_provider_failure_does_not_break_response(fake_llm_factory):
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm, verification_provider=_BrokenVerification())

    response = agent.run(AgentRequest(query="hi"))

    assert response.status == AgentStatus.SUCCESS
    assert response.metadata["verification"]["verified"] is False
    assert "verification backend down" in response.metadata["verification"]["notes"]


def test_default_verification_provider_is_a_clearly_marked_noop(fake_llm_factory):
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm)  # no verification_provider supplied

    response = agent.run(AgentRequest(query="hi"))

    assert response.metadata["verification"]["verified"] is False
    assert "not yet integrated" in response.metadata["verification"]["notes"].lower()
