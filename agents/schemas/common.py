"""
agents/schemas/common.py
==========================

Common request/response data structures shared by every agent in the
Moltress agent layer.

Design notes
------------
- Uses `pydantic` for validation, JSON (de)serialization, and easy FastAPI
  integration later (FastAPI can use these models directly as
  request/response bodies).
- `AgentRequest` is intentionally generic enough to carry code, files,
  logs, and forward-looking integration context (RAG, Knowledge Graph,
  Memory) without the agents needing to know how that context was
  produced.
- `AgentResponse` is the base response envelope. Individual agents extend
  it with specialized fields (see agents/schemas/<agent>.py) rather than
  overloading this class with agent-specific concerns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    """Standard status values every agent response must use."""

    SUCCESS = "success"
    PARTIAL = "partial"          # Agent produced a best-effort result but was missing context
    NEEDS_INPUT = "needs_input"  # Agent cannot proceed without more information
    ERROR = "error"              # Agent failed (see AgentError)


class ConfidenceLevel(str, Enum):
    """Coarse-grained confidence bucket, paired with a numeric score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Context / integration-point payloads
# ---------------------------------------------------------------------------

class RetrievedDocument(BaseModel):
    """A single piece of context retrieved by the (external) RAG system."""

    source: str = Field(..., description="File path, URL, or identifier of the source document/chunk")
    content: str = Field(..., description="The retrieved text/code chunk")
    score: Optional[float] = Field(None, description="Relevance score from the retriever, if available")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphRelationship(BaseModel):
    """A single relationship edge retrieved from the (external) Knowledge Graph."""

    subject: str = Field(..., description="e.g. 'FunctionA'")
    relation: str = Field(..., description="e.g. 'calls', 'depends_on', 'worked_on'")
    target: str = Field(..., description="e.g. 'FunctionB'")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(BaseModel):
    """A single piece of memory/context supplied by the (external) Memory system."""

    role: str = Field(..., description="e.g. 'user', 'assistant', 'system', 'prior_decision'")
    content: str
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceFile(BaseModel):
    """A source file supplied directly in the request (as opposed to via RAG)."""

    path: str
    content: str
    language: Optional[str] = None


class ProjectInfo(BaseModel):
    """High-level information about the project the agent is operating on."""

    name: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    description: Optional[str] = None
    root_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentContext(BaseModel):
    """
    Aggregated context passed to an agent for a single request.

    This is the single integration surface for RAG, Knowledge Graph, and
    Memory. The concrete providers (vector DB, Neo4j, memory store) live
    outside this package; they only need to populate these fields.
    """

    project_info: Optional[ProjectInfo] = None
    source_files: List[SourceFile] = Field(default_factory=list)
    error_logs: Optional[str] = None

    retrieved_documents: List[RetrievedDocument] = Field(
        default_factory=list, description="Context supplied by the external RAG system"
    )
    graph_context: List[GraphRelationship] = Field(
        default_factory=list, description="Context supplied by the external Knowledge Graph system"
    )
    memory: List[MemoryEntry] = Field(
        default_factory=list, description="Context supplied by the external Memory system"
    )

    extra: Dict[str, Any] = Field(default_factory=dict, description="Escape hatch for forward-compatible context")


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    """
    Standard input structure accepted by every Moltress agent.

    The main Moltress backend constructs one of these (typically after
    running retrieval/graph lookups) and calls `agent.run(request)`.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str = Field(..., description="The user's natural-language request")
    context: AgentContext = Field(default_factory=AgentContext)

    # Convenience passthroughs — many callers won't want to construct a full
    # AgentContext just to pass a snippet of code or a stack trace.
    code: Optional[str] = Field(None, description="Primary code snippet under discussion, if any")
    files: List[SourceFile] = Field(default_factory=list, description="Alias/merge target for context.source_files")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Explicit, per-request approval for destructive/high-risk tool actions
    # (e.g. "write_file"). Tools flagged `requires_approval=True` are only
    # executed if their `name` appears in this list — this is the mechanism
    # by which a human/caller grants one-time permission for an otherwise
    # blocked action, per the "explicit approval before destructive
    # operations" requirement.
    approved_actions: List[str] = Field(
        default_factory=list, description="Tool names explicitly approved for this request (e.g. 'write_file')"
    )

    # Optional override of the orchestration loop's iteration ceiling for
    # this specific request. If None, the agent falls back to its
    # configured default (agents.config.OrchestrationConfig.max_tool_iterations).
    max_tool_iterations: Optional[int] = Field(None, ge=1, le=50)

    def merged_source_files(self) -> List[SourceFile]:
        """Combine `files` and `context.source_files` without duplicating paths."""
        seen = set()
        merged: List[SourceFile] = []
        for f in [*self.files, *self.context.source_files]:
            if f.path not in seen:
                seen.add(f.path)
                merged.append(f)
        return merged


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    """A single piece of evidence backing a claim made by the agent."""

    source: str = Field(..., description="File path, log line, tool name, or retrieved doc id")
    excerpt: Optional[str] = Field(None, description="Short excerpt supporting the claim")
    reason: Optional[str] = Field(None, description="Why this evidence is relevant")


class ToolInvocationRecord(BaseModel):
    """A record of a tool call made during agent execution, for auditability."""

    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    success: bool
    summary: Optional[str] = Field(None, description="Short, non-sensitive summary of the tool result")
    iteration: Optional[int] = Field(None, description="Which loop iteration this call happened in")
    duration_ms: Optional[float] = Field(None, description="Wall-clock time the call took")
    denied: bool = Field(False, description="True if the call was blocked (permission/approval), not executed")
    operation_type: Optional[str] = Field(
        None, description="'read' | 'write' | 'execute' | 'destructive' — see tools.base_tool.ToolOperationType"
    )


class AgentError(BaseModel):
    """Structured error payload returned when status == ERROR."""

    error_type: str = Field(..., description="e.g. 'LLMUnavailable', 'InvalidInput', 'ToolFailure', 'Timeout'")
    message: str
    recoverable: bool = Field(True, description="Whether the caller can retry")
    details: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """
    Base structured response returned by every agent.

    Specialized agents (Security, Debugging, etc.) extend this via
    composition/subclassing in their own schema modules, adding fields
    like `findings` or `root_cause` while keeping this common envelope.
    """

    agent_name: str
    request_id: str
    status: AgentStatus

    result: Optional[str] = Field(None, description="Primary result: generated code, explanation, fix, etc.")
    explanation: Optional[str] = Field(None, description="Reasoning behind the result, in plain language")

    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    evidence: List[Evidence] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made due to missing context")
    warnings: List[str] = Field(default_factory=list)

    tools_used: List[ToolInvocationRecord] = Field(default_factory=list)
    error: Optional[AgentError] = None

    execution_time_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class RoutingDecision(BaseModel):
    """
    The AgentRouter's explanation of which agent it selected and why —
    returned alongside (or instead of) the bare agent name so a caller
    (or a human) can audit routing behavior.
    """

    agent_name: str
    reason: str = Field(..., description="Human-readable justification for this routing decision")
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_rule: Optional[str] = Field(None, description="'keyword', 'llm_fallback', or 'default'")
