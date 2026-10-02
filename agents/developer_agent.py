"""
agents/developer_agent.py

Developer Agent: code generation, explanation, refactoring, and
implementation guidance, grounded in project context.

Tool permissions (per Moltress SRS section 4/5):
    read_file, search_code, inspect_project, inspect_source (extra,
    read-only), an OPTIONAL approval-gated write_file, and OPTIONAL
    controlled test execution (run_tests).

write_file is destructive (BaseTool.requires_approval=True) and is only
even registered when ToolConfig.enable_write_tool is True (operator
opt-in, default False) — even then, BaseAgent will refuse to execute it
unless the specific request explicitly approves it via
AgentRequest.approved_actions=["write_file"].

run_tests is only registered when ToolConfig.enable_test_execution is
True (operator opt-in, default False); it does not require per-request
approval since running the existing test suite is not a destructive
action, but it is still fully sandboxed to the project root and subject
to the terminal command whitelist inside RunTestsTool.
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from agents.base_agent import BaseAgent
from agents.prompts.developer_prompt import DEVELOPER_SYSTEM_PROMPT
from agents.schemas.developer import DeveloperAgentResponse
from agents.tools.base_tool import BaseTool
from agents.tools.code_tools import InspectProjectTool, InspectSourceTool, SearchCodeTool
from agents.tools.file_tools import ReadFileTool, WriteFileTool
from agents.tools.test_tools import RunTestsTool


class DeveloperAgent(BaseAgent):
    agent_name = "developer_agent"
    system_prompt = DEVELOPER_SYSTEM_PROMPT
    response_model = DeveloperAgentResponse

    allowed_tool_names: ClassVar[Optional[List[str]]] = [
        "read_file",
        "search_code",
        "inspect_project",
        "inspect_source",
        "write_file",  # destructive; approval-gated, see module docstring
        "run_tests",   # optional; only registered if enable_test_execution=True
    ]

    def default_tools(self) -> List[BaseTool]:
        tools: List[BaseTool] = [
            ReadFileTool(self.config.tools),
            SearchCodeTool(self.config.tools),
            InspectProjectTool(self.config.tools),
            InspectSourceTool(self.config.tools),
        ]
        if self.config.tools.enable_write_tool:
            tools.append(WriteFileTool(self.config.tools))
        if self.config.tools.enable_test_execution:
            tools.append(RunTestsTool(self.config.tools))
        return tools
