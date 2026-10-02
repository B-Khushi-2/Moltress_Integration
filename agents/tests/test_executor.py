"""
agents/tests/test_executor.py

Tests specific to the extracted AgentExecutionLoop component
(agents/executor.py) and the v2.1 additions built on top of it:
  - the loop is a standalone, reusable class (not just inline BaseAgent code)
  - both supported tool-call JSON shapes are recognized
  - the simplified {"action": "final", "answer": ...} shape is normalized
  - repeated approval denials produce AgentStatus.NEEDS_INPUT (distinct
    from a generic technical failure)
  - tool operation_type (READ/WRITE/EXECUTE/DESTRUCTIVE) is surfaced on
    every ToolInvocationRecord
  - a human-readable execution trace is generated and excludes tool
    arguments/data
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.developer_agent import DeveloperAgent
from agents.executor import AgentExecutionLoop
from agents.schemas.common import AgentRequest, AgentStatus
from agents.tools.base_tool import ToolOperationType
from agents.tools.file_tools import ReadFileTool


@pytest.fixture
def sandbox_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b\n")
        yield tmp


def test_execution_loop_is_a_standalone_class(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    tools = {"read_file": ReadFileTool(cfg.tools)}
    canned = {"status": "success", "result": "done", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    llm = fake_llm_factory(canned_response=canned)

    loop = AgentExecutionLoop(llm_client=llm, tools=tools, config=cfg, agent_name="standalone_test")
    request = AgentRequest(query="hello")
    state = loop.execute(request, system_prompt="You are a test agent.", initial_user_prompt="hello")

    assert state.status == "completed"
    assert state.final_result == canned


def test_execution_loop_actually_calls_the_tool(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    tools = {"read_file": ReadFileTool(cfg.tools)}
    responses = [
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "check"},
        {"status": "success", "result": "done", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)

    loop = AgentExecutionLoop(llm_client=llm, tools=tools, config=cfg, agent_name="standalone_test")
    state = loop.execute(AgentRequest(query="read the file"), system_prompt="sys", initial_user_prompt="hello")

    assert len(state.tools_used) == 1
    assert state.tools_used[0].success is True
    assert any("def add" in m.content for m in llm.call_log[1]["messages"])


def test_alias_tool_call_shape_is_recognized(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    responses = [
        {"action": "tool", "tool": "read_file", "arguments": {"path": "app.py"}, "reasoning": "check"},
        {"status": "success", "result": "done", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="read the file"))

    assert response.status == AgentStatus.SUCCESS
    assert len(response.tools_used) == 1
    assert response.tools_used[0].tool_name == "read_file"
    assert response.tools_used[0].success is True


def test_alias_final_answer_shape_is_normalized(fake_llm_factory):
    canned = {"action": "final", "answer": "Here is the answer.", "confidence": "medium"}
    llm = fake_llm_factory(canned_response=canned)
    agent = DeveloperAgent(llm_client=llm)

    response = agent.run(AgentRequest(query="hi"))

    assert response.status == AgentStatus.SUCCESS
    assert response.result == "Here is the answer."


def test_repeated_approval_denial_yields_needs_input_status(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir, enable_write_tool=True),
        orchestration=OrchestrationConfig(max_tool_iterations=5, max_consecutive_tool_failures=2),
    )
    write_call_1 = {"action": "use_tool", "tool_name": "write_file", "tool_arguments": {"path": "a.py", "content": "x=1"}, "reasoning": "r1"}
    write_call_2 = {"action": "use_tool", "tool_name": "write_file", "tool_arguments": {"path": "b.py", "content": "x=2"}, "reasoning": "r2"}
    llm = fake_llm_factory(canned_responses=[write_call_1, write_call_2])
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="write two files"))

    assert response.status == AgentStatus.NEEDS_INPUT
    assert "approval" in response.explanation.lower()


def test_repeated_generic_tool_failure_yields_partial_not_needs_input(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir),
        orchestration=OrchestrationConfig(max_tool_iterations=5, max_consecutive_tool_failures=2),
    )
    bad_1 = {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "missing1.py"}, "reasoning": "r1"}
    bad_2 = {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "missing2.py"}, "reasoning": "r2"}
    llm = fake_llm_factory(canned_responses=[bad_1, bad_2])
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="read missing files"))

    assert response.status == AgentStatus.PARTIAL


def test_tool_invocation_record_carries_operation_type(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    responses = [
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "x"},
        {"status": "success", "result": "done", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="read app.py"))

    assert response.tools_used[0].operation_type == ToolOperationType.READ.value


def test_write_file_is_classified_destructive():
    from agents.tools.file_tools import WriteFileTool
    assert WriteFileTool.operation_type == ToolOperationType.DESTRUCTIVE
    assert WriteFileTool.requires_approval is True


def test_terminal_tool_requires_approval():
    from agents.tools.terminal_tools import TerminalTool
    assert TerminalTool.requires_approval is True
    assert TerminalTool.operation_type == ToolOperationType.EXECUTE


def test_execution_trace_is_generated_and_excludes_arguments(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(tools=ToolConfig(project_root=sandbox_dir))
    responses = [
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "x"},
        {"status": "success", "result": "SECRET_CONTENT_MARKER", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="read app.py"))
    trace = response.metadata["execution_trace"]

    assert "Task Started" in trace
    assert "Agent: developer_agent" in trace
    assert "Action: read_file" in trace
    assert "Status: success" in trace
    assert "Final" in trace
    assert "app.py" not in trace
    assert "SECRET_CONTENT_MARKER" not in trace


def test_execution_trace_present_on_stopped_response(fake_llm_factory, sandbox_dir):
    cfg = AgentConfig(
        tools=ToolConfig(project_root=sandbox_dir),
        orchestration=OrchestrationConfig(max_tool_iterations=1, max_consecutive_tool_failures=10),
    )
    responses = [
        {"action": "use_tool", "tool_name": "inspect_project", "tool_arguments": {"directory": "."}, "reasoning": "x"},
    ]
    llm = fake_llm_factory(canned_responses=responses)
    agent = DeveloperAgent(llm_client=llm, config=cfg)

    response = agent.run(AgentRequest(query="explore"))

    assert response.status == AgentStatus.PARTIAL
    assert "execution_trace" in response.metadata
    assert "Task Started" in response.metadata["execution_trace"]
