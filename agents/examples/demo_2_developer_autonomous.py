"""
examples/demo_2_developer_autonomous.py
==========================================

DEMO 2: Developer Agent — inspects the project, proposes a code change,
requires explicit user approval before writing it, applies the change
once approved, then runs the relevant tests and reports the result.

Demonstrates:
  - genuine multi-step autonomy (inspect -> plan -> write -> test -> report)
  - the approval gate for a destructive/write operation (section 8): the
    SAME scripted request run WITHOUT approval is shown first (denied),
    then WITH approval (executes) — to make the safety boundary visible.

Run with:
    python -m agents.examples.demo_2_developer_autonomous
"""

import os
import tempfile

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.developer_agent import DeveloperAgent
from agents.schemas.common import AgentRequest
from agents.tests.conftest import FakeOllamaClient

SAMPLE_REGISTRATION = """\
def register_user(username, password, email):
    # TODO: add validation
    return {"username": username, "password": password, "email": email}
"""

SAMPLE_TEST = """\
from registration import register_user

def test_register_user_basic():
    user = register_user("alice", "hunter2", "alice@example.com")
    assert user["username"] == "alice"
"""

FIXED_REGISTRATION = """\
def register_user(username, password, email):
    if not username or not isinstance(username, str):
        raise ValueError("username is required")
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    if not email or "@" not in email:
        raise ValueError("a valid email is required")
    return {"username": username, "password": password, "email": email}
"""


def build_sample_project(root: str) -> None:
    with open(os.path.join(root, "registration.py"), "w") as f:
        f.write(SAMPLE_REGISTRATION)
    with open(os.path.join(root, "test_registration.py"), "w") as f:
        f.write(SAMPLE_TEST)


def _scripted_turns(approved: bool):
    tool_turns = [
        {
            "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "registration.py"},
            "reasoning": "See the current implementation before changing it.",
        },
        {
            "action": "use_tool", "tool_name": "write_file",
            "tool_arguments": {"path": "registration.py", "content": FIXED_REGISTRATION},
            "reasoning": "Apply input validation for username, password, and email.",
        },
        {
            "action": "use_tool", "tool_name": "run_tests", "tool_arguments": {},
            "reasoning": "Confirm the existing tests still pass after the change.",
        },
    ]

    if approved:
        # write_file actually executes -> the stricter validation is now live,
        # and the REAL test run genuinely fails against the old, shorter
        # test password ("hunter2", 7 chars) — the agent must report this
        # honestly rather than claiming unqualified success.
        final_turn = {
            "status": "partial",
            "result": FIXED_REGISTRATION,
            "generated_code": FIXED_REGISTRATION,
            "design_notes": ["Added explicit checks for username, password length, and a basic email shape check."],
            "confidence": "medium",
            "evidence": [{"source": "registration.py", "reason": "Original function had a TODO for validation"}],
            "assumptions": ["Password minimum length of 8 chosen as a reasonable default; adjust to org policy."],
            "warnings": [
                "Running the existing test suite after this change showed a real failure: "
                "test_register_user_basic uses a 7-character password ('hunter2'), which the new "
                "8-character minimum now rejects. The test fixture needs updating to match the new "
                "validation rule before this change is considered complete."
            ],
        }
    else:
        # write_file was denied -> the file on disk is unchanged, so the
        # (still real) test run genuinely passes against the original,
        # unvalidated function.
        final_turn = {
            "status": "needs_input",
            "result": FIXED_REGISTRATION,
            "generated_code": FIXED_REGISTRATION,
            "design_notes": ["Proposed validation could not be applied: write_file was not approved for this request."],
            "confidence": "medium",
            "evidence": [{"source": "registration.py", "reason": "Original function had a TODO for validation"}],
            "assumptions": [],
            "warnings": [
                "The proposed fix was not written to disk because write_file requires explicit "
                "approval, which this request did not grant. The existing tests still pass only "
                "because the (unvalidated) original function is unchanged."
            ],
        }

    return [*tool_turns, final_turn]


def run_without_approval():
    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)
        config = AgentConfig(
            tools=ToolConfig(project_root=project_root, enable_write_tool=True, enable_terminal_tool=True, enable_test_execution=True),
            orchestration=OrchestrationConfig(max_tool_iterations=6, max_consecutive_tool_failures=3),
        )
        llm = FakeOllamaClient(canned_responses=_scripted_turns(approved=False))
        agent = DeveloperAgent(llm_client=llm, config=config)

        request = AgentRequest(
            query="Add input validation to register_user in registration.py.",
            # NOTE: no approved_actions — write_file will be denied.
        )
        response = agent.run(request)

        print("=" * 70)
        print("DEMO 2a: Developer Agent — WITHOUT approval (write_file denied)")
        print("=" * 70)
        print()
        print(response.metadata.get("execution_trace", ""))
        print()
        print(f"Status: {response.status}")
        with open(os.path.join(project_root, "registration.py")) as f:
            unchanged = f.read()
        print(f"File on disk unchanged: {unchanged == SAMPLE_REGISTRATION}")
        print()


def run_with_approval():
    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)
        config = AgentConfig(
            tools=ToolConfig(project_root=project_root, enable_write_tool=True, enable_terminal_tool=True, enable_test_execution=True),
            orchestration=OrchestrationConfig(max_tool_iterations=6, max_consecutive_tool_failures=3),
        )
        llm = FakeOllamaClient(canned_responses=_scripted_turns(approved=True))
        agent = DeveloperAgent(llm_client=llm, config=config)

        request = AgentRequest(
            query="Add input validation to register_user in registration.py.",
            approved_actions=["write_file"],  # explicit user approval for the destructive action
        )
        response = agent.run(request)

        print("=" * 70)
        print("DEMO 2b: Developer Agent — WITH approval (write_file executes)")
        print("=" * 70)
        print()
        print(response.metadata.get("execution_trace", ""))
        print()
        print(f"Status: {response.status}")
        with open(os.path.join(project_root, "registration.py")) as f:
            changed = f.read()
        print(f"File on disk was modified: {changed != SAMPLE_REGISTRATION}")
        print(f"Real tool calls made: {[t.tool_name for t in response.tools_used]}")


if __name__ == "__main__":
    run_without_approval()
    run_with_approval()
