"""
examples/demo_4_multi_agent_pipeline.py
===========================================

DEMO 4: Multi-Agent Orchestration Pipeline — Debugging -> Developer -> Testing

Demonstrates:
  - Multi-agent collaboration with shared task state and inter-agent handoffs.
  - Step 1: Debugging Agent investigates a crash (`KeyError`) and identifies root cause.
  - Step 2: Handoff payload passed to Developer Agent, which refactors the file on disk.
  - Step 3: Handoff payload passed to Testing Agent, which generates unit tests and runs pytest.
  - Step 4: Claim Verification Layer checks facts and syntax before returning final pipeline state.

Run with:
    python -m agents.examples.demo_4_multi_agent_pipeline --scripted
    python -m agents.examples.demo_4_multi_agent_pipeline          # (live Ollama mode)
"""

import os
import sys
import tempfile

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.llm.ollama_client import OllamaClient
from agents.orchestrator import AgentOrchestrator
from agents.providers_impl import (
    ASTGraphProvider,
    CodeFactVerificationProvider,
    InMemoryMemoryProvider,
    LocalCodeRAGProvider,
)
from agents.schemas.common import AgentRequest
from agents.tests.conftest import FakeOllamaClient

SAMPLE_LOGIN = """\
def login(username, password):
    users = {"alice": "hunter2", "bob": "correcthorse"}
    # Fails with KeyError when username is not found in dict
    return users[username] == password
"""

FIXED_LOGIN = """\
def login(username, password):
    users = {"alice": "hunter2", "bob": "correcthorse"}
    if username not in users:
        return False
    return users[username] == password
"""

TEST_LOGIN_CODE = """\
from login import login

def test_login_valid():
    assert login("alice", "hunter2") is True

def test_login_unknown_user():
    assert login("carol", "wrong") is False
"""


def build_sample_project(root: str) -> None:
    with open(os.path.join(root, "login.py"), "w") as f:
        f.write(SAMPLE_LOGIN)


def get_canned_pipeline_turns():
    return [
        # Turn 1: Debugging Agent inspects login.py
        {
            "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "login.py"},
            "reasoning": "Read login.py to inspect the un-guarded dictionary access.",
        },
        # Turn 2: Debugging Agent final answer
        {
            "status": "success",
            "result": "KeyError: 'carol' occurs because login.py directly indexes users[username].",
            "explanation": "Direct indexing users[username] raises KeyError when username is not in users.",
            "root_cause": "Direct dictionary indexing without checking 'username in users' or using dict.get().",
            "suggested_fix": "Add a check 'if username not in users: return False' before evaluating password.",
            "confidence": "high",
        },
        # Turn 3: Developer Agent reads login.py
        {
            "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "login.py"},
            "reasoning": "Inspect login.py before writing the fix.",
        },
        # Turn 4: Developer Agent writes the fix
        {
            "action": "use_tool", "tool_name": "write_file",
            "tool_arguments": {"path": "login.py", "content": FIXED_LOGIN},
            "reasoning": "Apply the guarded dictionary lookup fix.",
        },
        # Turn 5: Developer Agent final answer
        {
            "status": "success",
            "result": FIXED_LOGIN,
            "explanation": "Added guard 'if username not in users: return False' to prevent KeyError.",
            "generated_code": FIXED_LOGIN,
            "confidence": "high",
        },
        # Turn 6: Testing Agent reads login.py
        {
            "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "login.py"},
            "reasoning": "Inspect the fixed login.py to write tests.",
        },
        # Turn 7: Testing Agent final answer
        {
            "status": "success",
            "result": "Generated unit tests for login.py.",
            "generated_tests": [
                {"name": "test_login_valid", "test_type": "unit", "code": "assert login('alice', 'hunter2') is True"},
                {"name": "test_login_unknown_user", "test_type": "edge_case", "code": "assert login('carol', 'wrong') is False"},
            ],
            "identified_edge_cases": ["unknown username", "wrong password"],
            "confidence": "high",
        },
    ]


def main():
    scripted = "--scripted" in sys.argv or "-s" in sys.argv

    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)

        config = AgentConfig(
            tools=ToolConfig(
                project_root=project_root,
                enable_write_tool=True,
                enable_terminal_tool=True,
                enable_test_execution=True,
            ),
            orchestration=OrchestrationConfig(max_tool_iterations=6),
        )

        rag_provider = LocalCodeRAGProvider()
        graph_provider = ASTGraphProvider()
        memory_provider = InMemoryMemoryProvider()
        verification_provider = CodeFactVerificationProvider()

        if scripted:
            llm = FakeOllamaClient(canned_responses=get_canned_pipeline_turns())
            print("=" * 70)
            print("DEMO 4: Autonomous Multi-Agent Pipeline (SCRIPTED Mode)")
            print("        Debugging -> Developer -> Testing")
            print("=" * 70)
        else:
            llm = OllamaClient(config=config.ollama)
            print("=" * 70)
            print("DEMO 4: Autonomous Multi-Agent Pipeline (LIVE Ollama Mode)")
            print("        Debugging -> Developer -> Testing")
            print("=" * 70)

        orchestrator = AgentOrchestrator(
            llm_client=llm,
            config=config,
            rag_provider=rag_provider,
            graph_provider=graph_provider,
            memory_provider=memory_provider,
            verification_provider=verification_provider,
        )

        request = AgentRequest(
            query="Investigate KeyError: 'carol' crash in login.py, fix the code, and generate unit tests.",
            approved_actions=["write_file"],
        )

        orch_state = orchestrator.run_debug_fix_test_pipeline(request, auto_approve_dev_write=True)

        print("\n" + orch_state.final_output)
        print("-" * 70)
        print(f"Pipeline Status : {orch_state.status}")
        print(f"Executed Steps  : {orch_state.pipeline_steps}")
        print(f"Total Handoffs  : {len(orch_state.handoffs)}")
        print(f"Tools Invoked   : {[t.tool_name for t in orch_state.cumulative_tools_used]}")

        if orch_state.status == "completed":
            # Write test file to disk and run pytest to demonstrate 100% end-to-end verification
            with open(os.path.join(project_root, "test_login.py"), "w") as f:
                f.write(TEST_LOGIN_CODE)

            from agents.tools.test_tools import RunTestsTool
            test_tool = RunTestsTool(config.tools)
            res = test_tool.safe_run()
            print(f"Real Pytest Result: success={res.success}, summary='{res.summary}'")
        else:
            print("\nNote: Pipeline stopped before completion (LLM server offline or needs input).")
            print("To run the autonomous demonstration offline, use the --scripted flag:")
            print("    python -m agents.examples.demo_4_multi_agent_pipeline --scripted")


if __name__ == "__main__":
    main()
