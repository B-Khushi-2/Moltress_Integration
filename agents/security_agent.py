"""
agents/security_agent.py

Security Agent: vulnerability identification, secret detection, and
remediation guidance with severity/confidence scoring.

Tool permissions (per Moltress SRS section 4):
    read_file, search_code, inspect_project, plus the security scanning
    tools (scan_for_secrets, scan_insecure_patterns).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

from agents.base_agent import BaseAgent
from agents.prompts.security_prompt import SECURITY_SYSTEM_PROMPT
from agents.schemas.security import SecurityAgentResponse
from agents.tools.base_tool import BaseTool
from agents.tools.code_tools import InspectProjectTool, SearchCodeTool
from agents.tools.file_tools import ReadFileTool
from agents.tools.security_tools import InsecurePatternScanTool, SecretScanTool


class SecurityAgent(BaseAgent):
    agent_name = "security_agent"
    system_prompt = SECURITY_SYSTEM_PROMPT
    response_model = SecurityAgentResponse

    allowed_tool_names: ClassVar[Optional[List[str]]] = [
        "read_file",
        "search_code",
        "inspect_project",
        "scan_for_secrets",
        "scan_insecure_patterns",
    ]

    def default_tools(self) -> List[BaseTool]:
        return [
            ReadFileTool(self.config.tools),
            SearchCodeTool(self.config.tools),
            InspectProjectTool(self.config.tools),
            SecretScanTool(),
            InsecurePatternScanTool(),
        ]
