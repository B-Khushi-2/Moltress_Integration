"""
agents/debugging_agent.py

Debugging Agent: root-cause analysis of errors, stack traces, and logs.

Tool permissions (per Moltress SRS section 4/5):
    read_file, search_code, inspect_project, read_logs, run_tests (to
    confirm/reproduce a suspected failure), and an OPTIONAL controlled
    terminal tool (only registered when ToolConfig.enable_terminal_tool
    is True — off by default; even then only whitelisted, non-shell
    commands may run, see tools/terminal_tools.py).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from agents.base_agent import BaseAgent
from agents.prompts.debugging_prompt import DEBUGGING_SYSTEM_PROMPT
from agents.schemas.debugging import DebuggingAgentResponse
from agents.tools.base_tool import BaseTool
from agents.tools.code_tools import InspectProjectTool, InspectSourceTool, SearchCodeTool
from agents.tools.file_tools import ReadFileTool, SearchFilesTool
from agents.tools.log_tools import ReadLogsTool
from agents.tools.terminal_tools import TerminalTool
from agents.tools.test_tools import RunTestsTool


class DebuggingAgent(BaseAgent):
    agent_name = "debugging_agent"
    system_prompt = DEBUGGING_SYSTEM_PROMPT
    response_model = DebuggingAgentResponse

    allowed_tool_names: ClassVar[Optional[List[str]]] = [
        "read_file",
        "search_files",
        "search_code",
        "inspect_project",
        "inspect_source",
        "read_logs",
        "run_tests",
        "run_command",  # optional; only registered if enable_terminal_tool=True
    ]

    def default_tools(self) -> List[BaseTool]:
        tools: List[BaseTool] = [
            ReadFileTool(self.config.tools),
            SearchFilesTool(self.config.tools),
            SearchCodeTool(self.config.tools),
            InspectProjectTool(self.config.tools),
            InspectSourceTool(self.config.tools),
            ReadLogsTool(self.config.tools),
            RunTestsTool(self.config.tools),
        ]
        if self.config.tools.enable_terminal_tool:
            tools.append(TerminalTool(self.config.tools))
        return tools
