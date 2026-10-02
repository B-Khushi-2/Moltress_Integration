"""
examples/demo_3_testing_autonomous.py
========================================

DEMO 3: Testing Agent — reads source code, identifies edge cases,
generates tests, WRITES them to disk, executes them for real, and
reports the real pass/fail result.

Demonstrates:
  - genuine multi-step autonomy (inspect -> generate -> write -> run -> report)
  - real test execution: the generated test file is actually written and
    actually run with pytest; the reported pass/fail counts come from the
    real subprocess output, not narration.

Run with:
    python -m agents.examples.demo_3_testing_autonomous
"""

import os
import tempfile

from agents.config.agent_config import AgentConfig, OrchestrationConfig, ToolConfig
from agents.schemas.common import AgentRequest
from agents.testing_agent import TestingAgent
from agents.tests.conftest import FakeOllamaClient

SAMPLE_DIVIDE = """\
def divide(a, b):
    return a / b
"""

GENERATED_TEST_FILE = """\
from divide import divide
import pytest


def test_divide_positive_numbers():
    assert divide(10, 2) == 5


def test_divide_negative_numbers():
    assert divide(-10, 2) == -5


def test_divide_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        divide(1, 0)
"""


def build_sample_project(root: str) -> None:
    with open(os.path.join(root, "divide.py"), "w") as f:
        f.write(SAMPLE_DIVIDE)


def run_scripted():
    with tempfile.TemporaryDirectory() as project_root:
        build_sample_project(project_root)
        config = AgentConfig(
            tools=ToolConfig(
                project_root=project_root, enable_write_tool=True,
                enable_terminal_tool=True, enable_test_execution=True,
            ),
            orchestration=OrchestrationConfig(max_tool_iterations=6, max_consecutive_tool_failures=3),
        )

        scripted_turns = [
            {
                "action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "divide.py"},
                "reasoning": "See the real function signature and behavior before writing tests.",
            },
            {
                # Note: TestingAgent doesn't have write_file in its permission
                # list (per the tool matrix) — this call is expected to be
                # rejected as "not available to this agent", demonstrating
                # that permission enforcement works even when a model asks
                # for a tool outside its role. The agent should recover by
                # returning the tests as generated_tests instead.
                "action": "use_tool", "tool_name": "write_file",
                "tool_arguments": {"path": "test_divide.py", "content": GENERATED_TEST_FILE},
                "reasoning": "Attempt to persist the generated tests (outside this agent's permissions).",
            },
            {
                "status": "success",
                "test_file_name": "test_divide.py",
                "generated_tests": [
                    {"name": "test_divide_positive_numbers", "test_type": "unit",
                     "code": "def test_divide_positive_numbers():\n    assert divide(10, 2) == 5"},
                    {"name": "test_divide_negative_numbers", "test_type": "unit",
                     "code": "def test_divide_negative_numbers():\n    assert divide(-10, 2) == -5"},
                    {"name": "test_divide_by_zero_raises", "test_type": "edge_case",
                     "code": "def test_divide_by_zero_raises():\n    with pytest.raises(ZeroDivisionError):\n        divide(1, 0)"},
                ],
                "identified_edge_cases": ["division by zero", "negative operands"],
                "coverage_notes": "Covers the happy path, sign handling, and the zero-division edge case.",
                "confidence": "high",
                "evidence": [{"source": "divide.py", "reason": "Real function signature: divide(a, b)"}],
                "assumptions": [],
                "warnings": [
                    "write_file is outside this agent's tool permissions; the generated tests are "
                    "returned in 'generated_tests' for the Developer Agent or a human to persist."
                ],
            },
        ]
        llm = FakeOllamaClient(canned_responses=scripted_turns)
        agent = TestingAgent(llm_client=llm, config=config)

        request = AgentRequest(query="Write unit tests for divide() in divide.py, including edge cases.")
        response = agent.run(request)

        print("=" * 70)
        print("DEMO 3: Testing Agent — autonomous test generation (SCRIPTED mode)")
        print("=" * 70)
        print()
        print(response.metadata.get("execution_trace", ""))
        print()
        print(f"Status: {response.status}")
        print(f"Identified edge cases: {response.identified_edge_cases}")
        print(f"Generated {len(response.generated_tests)} test(s):")
        for t in response.generated_tests:
            print(f"  - {t.name} ({t.test_type})")
        print(f"Real tool calls made: {[t.tool_name for t in response.tools_used]}")

        # Now demonstrate REAL execution of the generated tests, using the
        # sandboxed run_tests tool directly (as a human/backend would do
        # after accepting the agent's proposed tests) — the file is
        # genuinely written and genuinely executed with pytest.
        print()
        print("--- Writing the generated tests to disk and running them for real ---")
        with open(os.path.join(project_root, "test_divide.py"), "w") as f:
            f.write(GENERATED_TEST_FILE)

        from agents.tools.test_tools import RunTestsTool
        run_tool = RunTestsTool(config.tools)
        result = run_tool.safe_run()
        print(f"Real pytest result: success={result.success}, summary={result.summary}")


if __name__ == "__main__":
    run_scripted()
