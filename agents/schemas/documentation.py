"""
agents/schemas/documentation.py
==================================

Specialized response structure for the Documentation Agent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from agents.schemas.common import AgentResponse


class DocumentedSymbol(BaseModel):
    name: str
    kind: str = Field(..., description="'function', 'class', 'module', 'endpoint'")
    summary: str
    parameters: List[str] = Field(default_factory=list)
    returns: Optional[str] = None
    source_file: Optional[str] = None


class DocumentationAgentResponse(AgentResponse):
    """Response returned by DocumentationAgent.run()."""

    documentation_markdown: Optional[str] = Field(None, description="Full generated documentation, in Markdown")
    documented_symbols: List[DocumentedSymbol] = Field(default_factory=list)
    doc_format: str = Field("markdown", description="'markdown', 'docstring', 'readme_section', 'api_doc'")
