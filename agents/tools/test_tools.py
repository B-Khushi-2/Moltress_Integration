"""
agents/tools/test_tools.py
=============================

Testing-related tools: running a pytest suite (if explicitly enabled)
and collecting results in a structured form.

Test execution reuses the sandboxed TerminalTool rather than duplicating
subprocess logic, and is gated by BOTH `enable_terminal_tool` and the
more specific `enable_test_execution` flag.
"""

from __future__ import annotations

import re
from typing import Optional

from agents.config.agent_config import ToolConfig, get_config
from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult
from agents.tools.terminal_tools import TerminalTool

_SUMMARY_RE = re.compile(
    r"(?P<passed>\d+) passed"
    r"(?:, (?P<failed>\d+) failed)?"
    r"(?:, (?P<errors>\d+) error)?"
)


class RunTestsTool(BaseTool):
    operation_type = ToolOperationType.EXECUTE
    """Run the project's pytest suite (or a specific test file) and parse results."""

    name = "run_tests"
    description = "Run pytest against the project or a specific test file, if test execution is enabled."

    def __init__(self, config: Optional[ToolConfig] = None, terminal_tool: Optional[TerminalTool] = None):
        self.config = config or get_config().tools
        self.terminal_tool = terminal_tool or TerminalTool(self.config)

    def run(self, test_path: Optional[str] = None) -> ToolResult:
        if not self.config.enable_test_execution:
            return ToolResult(
                success=False,
                error="Test execution is disabled (ENABLE_TEST_EXECUTION=false). "
                "The agent can still generate tests without running them.",
            )

        command = "pytest -q" if not test_path else f"pytest -q {test_path}"
        result = self.terminal_tool.safe_run(command=command)

        if not result.success and result.error:
            # Terminal-level failure (disabled, not whitelisted, timeout, etc.)
            return result

        stdout = result.data.get("stdout", "") if result.data else ""
        match = _SUMMARY_RE.search(stdout)

        parsed = {
            "passed": int(match.group("passed")) if match and match.group("passed") else 0,
            "failed": int(match.group("failed")) if match and match.group("failed") else 0,
            "errors": int(match.group("errors")) if match and match.group("errors") else 0,
            "raw_output_tail": stdout[-2000:],
        }

        overall_success = result.data.get("return_code") == 0 if result.data else False

        return ToolResult(
            success=overall_success,
            data=parsed,
            summary=f"pytest: {parsed['passed']} passed, {parsed['failed']} failed, {parsed['errors']} error(s)",
        )
