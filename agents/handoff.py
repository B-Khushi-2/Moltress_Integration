"""
agents/handoff.py
===================

Inter-Agent Handoff Protocol & Shared Task State for Moltress Multi-Agent Workflows.

Provides:
  1. `HandoffPayload`: Data structure passed from an upstream agent to a downstream agent.
  2. `OrchestrationTaskState`: Shared multi-agent task state tracking progress,
     agent outputs, handoffs, and cumulative findings across an entire pipeline execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agents.schemas.common import AgentResponse, Evidence, ToolInvocationRecord
from agents.state import AgentTaskState


class HandoffPayload(BaseModel):
    """
    Structured payload passed from an upstream agent to a downstream agent.
    
    Example: DebuggingAgent -> DeveloperAgent
      from_agent: "debugging_agent"
      to_agent: "developer_agent"
      summary: "KeyError in login.py due to un-guarded dict lookup"
      root_cause: "users[username] raises KeyError when username is not in users"
      suggested_fix: "Use users.get(username) or check username in users"
      affected_files: ["login.py"]
    """

    handoff_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str
    to_agent: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    summary: str = Field(..., description="High-level summary of what the upstream agent discovered or accomplished")
    root_cause: Optional[str] = Field(None, description="Identified root cause (if originating from DebuggingAgent)")
    suggested_fix: Optional[str] = Field(None, description="Suggested code fix or approach")
    proposed_code: Optional[str] = Field(None, description="Generated code snippet or full file content")
    affected_files: List[str] = Field(default_factory=list, description="List of file paths involved")
    modified_files: Dict[str, str] = Field(default_factory=dict, description="Map of path -> content for files modified by upstream agent")

    evidence: List[Evidence] = Field(default_factory=list)
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="Additional context or metadata")


class OrchestrationTaskState(BaseModel):
    """
    Shared state across a multi-agent orchestration pipeline.
    
    Maintains an audit trail of all agent responses, intermediate handoffs,
    and cumulative findings throughout the pipeline lifecycle.
    """

    pipeline_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_query: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    pipeline_steps: List[str] = Field(default_factory=list, description="Ordered list of agent names executed so far")
    handoffs: List[HandoffPayload] = Field(default_factory=list, description="Chain of handoff payloads between agents")

    agent_responses: Dict[str, AgentResponse] = Field(default_factory=dict, description="Map of agent_name -> final AgentResponse")
    cumulative_findings: List[str] = Field(default_factory=list)
    cumulative_tools_used: List[ToolInvocationRecord] = Field(default_factory=list)
    cumulative_warnings: List[str] = Field(default_factory=list)

    status: str = Field("in_progress", description="'in_progress' | 'completed' | 'failed' | 'needs_approval'")
    final_output: Optional[str] = Field(None, description="Final overall summary or result of the pipeline")

    def record_agent_execution(self, agent_name: str, response: AgentResponse) -> None:
        """Record the execution result of an individual agent in the pipeline."""
        self.pipeline_steps.append(agent_name)
        self.agent_responses[agent_name] = response
        self.cumulative_tools_used.extend(response.tools_used)
        self.cumulative_warnings.extend(response.warnings)
        
        if response.explanation:
            self.cumulative_findings.append(f"[{agent_name}] {response.explanation}")
        elif response.result:
            self.cumulative_findings.append(f"[{agent_name}] {response.result[:200]}")

    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        summary: str,
        root_cause: Optional[str] = None,
        suggested_fix: Optional[str] = None,
        proposed_code: Optional[str] = None,
        affected_files: Optional[List[str]] = None,
        modified_files: Optional[Dict[str, str]] = None,
        evidence: Optional[List[Evidence]] = None,
    ) -> HandoffPayload:
        """Helper to build, record, and return a new HandoffPayload."""
        payload = HandoffPayload(
            from_agent=from_agent,
            to_agent=to_agent,
            summary=summary,
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            proposed_code=proposed_code,
            affected_files=affected_files or [],
            modified_files=modified_files or {},
            evidence=evidence or [],
        )
        self.handoffs.append(payload)
        return payload

    def latest_handoff(self) -> Optional[HandoffPayload]:
        """Return the most recent handoff payload, if any."""
        return self.handoffs[-1] if self.handoffs else None
