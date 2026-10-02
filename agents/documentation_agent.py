"""
agents/documentation_agent.py

Documentation Agent: generates accurate technical documentation derived
from actual source code and project context.

Tool permissions (per Moltress SRS section 4):
    read_file, search_code, inspect_project, inspect_source (extra,
    read-only).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from agents.base_agent import BaseAgent
from agents.prompts.documentation_prompt import DOCUMENTATION_SYSTEM_PROMPT
from agents.schemas.documentation import DocumentationAgentResponse
from agents.tools.base_tool import BaseTool
from agents.tools.code_tools import InspectProjectTool, InspectSourceTool, SearchCodeTool
from agents.tools.file_tools import ReadFileTool


class DocumentationAgent(BaseAgent):
    agent_name = "documentation_agent"
    system_prompt = DOCUMENTATION_SYSTEM_PROMPT
    response_model = DocumentationAgentResponse

    allowed_tool_names: ClassVar[Optional[List[str]]] = [
        "read_file",
        "search_code",
        "inspect_project",
        "inspect_source",
    ]

    def default_tools(self) -> List[BaseTool]:
        return [
            ReadFileTool(self.config.tools),
            SearchCodeTool(self.config.tools),
            InspectProjectTool(self.config.tools),
            InspectSourceTool(self.config.tools),
        ]
