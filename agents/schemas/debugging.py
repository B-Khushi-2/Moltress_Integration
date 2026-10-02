"""
agents/schemas/debugging.py
==============================

Specialized response structure for the Debugging Agent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from agents.schemas.common import AgentResponse


class SuspectedCause(BaseModel):
    """One candidate root cause considered by the agent, ranked by likelihood."""

    description: str
    likelihood: float = Field(..., ge=0.0, le=1.0)
    supporting_evidence: List[str] = Field(default_factory=list)
    ruled_out: bool = False
    ruled_out_reason: Optional[str] = None


class SuggestedFix(BaseModel):
    file_path: Optional[str] = None
    change_summary: str
    diff_or_content: Optional[str] = None
    risk: Optional[str] = Field(None, description="'low', 'medium', 'high' — risk of this fix causing regressions")


class DebuggingAgentResponse(AgentResponse):
    """Response returned by DebuggingAgent.run()."""

    error_summary: Optional[str] = None
    candidate_causes: List[SuspectedCause] = Field(default_factory=list)
    most_probable_cause: Optional[str] = None
    suggested_fixes: List[SuggestedFix] = Field(default_factory=list)
    reproduction_notes: Optional[str] = Field(
        None, description="How the error could be reproduced/verified, if determinable from context"
    )
