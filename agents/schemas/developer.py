"""
agents/schemas/developer.py
=============================

Specialized response structure for the Developer Agent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from agents.schemas.common import AgentResponse


class CodeChange(BaseModel):
    """A single proposed or applied code change."""

    file_path: str
    change_type: str = Field(..., description="'create', 'modify', or 'suggestion_only'")
    diff_or_content: str = Field(..., description="Unified diff, or full new file content")
    rationale: Optional[str] = None


class DeveloperAgentResponse(AgentResponse):
    """
    Response returned by DeveloperAgent.run().

    Adds implementation-specific fields on top of the common AgentResponse
    envelope (result/explanation/confidence/evidence/etc.).
    """

    generated_code: Optional[str] = Field(None, description="Primary generated/refactored code block")
    language: Optional[str] = None
    proposed_changes: List[CodeChange] = Field(default_factory=list)
    design_notes: List[str] = Field(default_factory=list, description="Design/architecture considerations")
    follow_up_suggestions: List[str] = Field(default_factory=list)
