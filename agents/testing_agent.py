"""
agents/testing_agent.py

Testing Agent: unit/integration test generation, edge-case identification,
failure analysis, and coverage guidance.

Tool permissions (per Moltress SRS section 4):
    read_file, search_code, inspect_project, inspect_source (extra,
    read-only), run_tests (which returns parsed test results directly,
    covering "read_test_results" without a redundant separate tool).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from agents.base_agent import BaseAgent
from agents.prompts.testing_prompt import TESTING_SYSTEM_PROMPT
from agents.schemas.testing import TestingAgentResponse
from agents.tools.base_tool import BaseTool
from agents.tools.code_tools import InspectProjectTool, InspectSourceTool, SearchCodeTool
from agents.tools.file_tools import ReadFileTool
from agents.tools.test_tools import RunTestsTool


class TestingAgent(BaseAgent):
    agent_name = "testing_agent"
    system_prompt = TESTING_SYSTEM_PROMPT
    response_model = TestingAgentResponse

    allowed_tool_names: ClassVar[Optional[List[str]]] = [
        "read_file",
        "search_code",
        "inspect_project",
        "inspect_source",
        "run_tests",
    ]

    def default_tools(self) -> List[BaseTool]:
        return [
            ReadFileTool(self.config.tools),
            SearchCodeTool(self.config.tools),
            InspectProjectTool(self.config.tools),
            InspectSourceTool(self.config.tools),
            RunTestsTool(self.config.tools),
        ]
