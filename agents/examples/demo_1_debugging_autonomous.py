"""
examples/demo_1_debugging_autonomous.py
==========================================

DEMO 1: Debugging Agent — reads code, investigates, runs a test, produces
a diagnosis. Demonstrates genuine multi-step autonomy: the AGENT decides
what to inspect next based on what it has already seen, not a
hard-coded script.

Two run modes
-------------
1. LIVE (default): uses the real local Ollama/Qwen model. The exact
   sequence of tool calls is decided by the model at each turn — run it
   more than once and you may see a different (still correct) path.
   Requires `ollama serve` running with MODEL_NAME pulled.

2. SCRIPTED (--scripted): uses a scripted FakeOllamaClient so the demo
   is 100% reproducible without a running model — useful for a project
   presentation where model availability/quality shouldn't be a
   variable. IMPORTANT: even in scripted mode, every tool call is REAL —
   only the model's "brain" is replaced; read_file and run_tests
   genuinely execute against real files on disk. This is clearly
   labeled in the output so it is never mistaken for the live path.

Run with:
    python -m agents.examples.demo_1_debugging_autonomous
    python -m agents.examples.demo_1_debugging_autonomous --scripted
"""

import os
import sys
import tempfile

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.debugging_agent import DebuggingAgent
from agents.schemas.common import AgentContext, AgentRequest

SAMPLE_LOGIN = """\
def login(username, password):
    users = {"alice": "hunter2", "bob": "correcthorse"}
    return users[username] == password


def main():
    print(login("alice", "wrong-password"))
    print(login("carol", "whatever"))


if __name__ == "__main__":
    main()
"""

SAMPLE_TEST = """\
from login import login

def test_login_rejects_unknown_user():
    try:
        login("carol", "whatever")
        assert False, "expected KeyError"
    except KeyError:
        pass
"""

STACK_TRACE = """\
Traceback (most recent call last):
  File "login.py", line 8, in main
    print(login("carol", "whatever"))
  File "login.py", line 3, in login
    return users[username] == password
KeyError: 'carol'
"""


def build_sample_project(root: str) -> None:
    with open(os.path.join(root, "login.py"), "w") as f:
        f.write(SAMPLE_LOGIN)
    with open(os.path.join(root, "test_login.py"), "w") as f:
        f.write(SAMPLE_TEST)


def run_live():
    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)
        config = AgentConfig(tools=ToolConfig(project_root=project_root))
        agent = DebuggingAgent(config=config)

        request = AgentRequest(
            query="The login function is failing for some users. Investigate and diagnose the root cause.",
            context=AgentContext(error_logs=STACK_TRACE),
        )
        response = agent.run(request)
        _print_result(response)


def run_scripted():
    """Reproducible demo: the model's decisions are scripted, but every
    tool call below genuinely executes against real files on disk."""
    from agents.tests.conftest import FakeOllamaClient

    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)

        # This sequence is what the LIVE model chose in practice for this
        # scenario — replayed here for a deterministic demo. The tool
        # calls below are executed for real (see build_sample_project).
        scripted_turns = [
            {
                "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "login.py"},
                "reasoning": "Inspect the implicated function before theorizing about the cause.",
            },
            {
                "action": "use_tool", "tool_name": "search_code", "tool_arguments": {"symbol": "users"},
                "reasoning": "Confirm every place the 'users' dict is defined or modified.",
            },
            {
                "action": "use_tool", "tool_name": "run_tests", "tool_arguments": {},
                "reasoning": "Run the existing test to observe the real failure and confirm the hypothesis.",
            },
            {
                "status": "success",
                "error_summary": "KeyError: 'carol' raised because login() indexes the users dict directly "
                "with an unrecognized username instead of checking membership first.",
                "candidate_causes": [
                    {
                        "description": "login() does 'users[username]' without checking 'username in users' first.",
                        "likelihood": 0.95,
                        "supporting_evidence": ["login.py:3"],
                        "ruled_out": False,
                    }
                ],
                "most_probable_cause": "Unrecognized usernames cause a raw dict KeyError instead of a handled login failure.",
                "suggested_fixes": [
                    {
                        "file_path": "login.py",
                        "change_summary": "Use users.get(username) and compare, returning False for unknown users.",
                        "risk": "low",
                    }
                ],
                "confidence": "high",
                "evidence": [{"source": "login.py:3", "reason": "Direct dict indexing with no membership check"}],
                "assumptions": [],
                "warnings": [],
            },
        ]
        config_for_test_exec = AgentConfig(
            tools=ToolConfig(project_root=project_root, enable_terminal_tool=True, enable_test_execution=True,
                              allowed_commands=["pytest"]),
            orchestration=OrchestrationConfig(max_tool_iterations=6),
        )
        llm = FakeOllamaClient(canned_responses=scripted_turns)
        agent = DebuggingAgent(llm_client=llm, config=config_for_test_exec)

        request = AgentRequest(
            query="The login function is failing for some users. Investigate and diagnose the root cause.",
            context=AgentContext(error_logs=STACK_TRACE),
        )
        response = agent.run(request)
        _print_result(response, scripted=True)


def _print_result(response, scripted: bool = False):
    print("=" * 70)
    print(f"DEMO 1: Debugging Agent — autonomous investigation ({'SCRIPTED' if scripted else 'LIVE'} mode)")
    print("=" * 70)
    print()
    print(response.metadata.get("execution_trace", "(no trace)"))
    print()
    print(f"Status: {response.status}")
    print(f"Most probable cause: {getattr(response, 'most_probable_cause', None)}")
    print(f"Confidence: {response.confidence}")
    print(f"Real tool calls made: {[t.tool_name for t in response.tools_used]}")


if __name__ == "__main__":
    if "--scripted" in sys.argv:
        run_scripted()
    else:
        run_live()
