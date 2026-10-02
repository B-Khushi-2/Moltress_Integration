"""
backend/models.py
=================

The HTTP contract between the UI and the backend. These models are the
*only* shape the UI depends on; the agent layer's richer ``AgentResponse``
is flattened into ``ChatResponse`` (and optionally attached verbatim as
``raw``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_QUERY_CHARS = 50_000


class ChatMessage(BaseModel):
    """One prior turn of the conversation (supplied by the UI)."""

    role: str
    content: str

    @field_validator("role")
    @classmethod
    def _normalize_role(cls, v: str) -> str:
        v = (v or "").strip().lower()
        # The desktop UI calls the model's turns "agent".
        return {"agent": "assistant", "ai": "assistant", "bot": "assistant"}.get(v, v)


class ChatFile(BaseModel):
    path: str
    content: str
    language: Optional[str] = None


class ChatRequest(BaseModel):
    query: str = Field(..., description="The user's request.")
    history: List[ChatMessage] = Field(default_factory=list)
    code: Optional[str] = None
    error_logs: Optional[str] = None
    files: List[ChatFile] = Field(default_factory=list)
    #: Force a specific agent (e.g. "security_agent") instead of routing.
    agent: Optional[str] = None
    #: "auto" = AgentRouter; "pipeline" = Debugging -> Developer -> Testing.
    mode: Literal["auto", "pipeline"] = "auto"
    #: Overrides the agents' sandbox root for this request (UI "context folder").
    context_folder: Optional[str] = None
    #: Names of attachments the UI could not forward (images/binaries).
    ignored_attachments: List[str] = Field(default_factory=list)
    request_id: Optional[str] = None
    #: Attach the full, unflattened AgentResponse as ``raw``.
    include_raw: bool = False

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > MAX_QUERY_CHARS:
            raise ValueError(f"query is too long ({len(v)} chars; max {MAX_QUERY_CHARS})")
        return v


class ApiError(BaseModel):
    type: str
    message: str
    recoverable: bool = True
    details: Dict[str, Any] = Field(default_factory=dict)


class ToolCallSummary(BaseModel):
    tool_name: str
    success: bool
    denied: bool = False
    summary: Optional[str] = None


class RoutingInfo(BaseModel):
    agent_name: str
    reason: str
    confidence: float
    matched_rule: Optional[str] = None


class VerificationInfo(BaseModel):
    verified: Optional[bool] = None
    notes: Optional[str] = None


class ChatResponse(BaseModel):
    ok: bool
    request_id: str
    #: Agent (or "orchestrator") that produced the answer.
    agent: Optional[str] = None
    status: Literal["success", "partial", "needs_input", "error"]
    #: Markdown, ready to render. Empty only when ``ok`` is false.
    answer: str = ""
    confidence: Optional[str] = None
    confidence_score: Optional[float] = None
    routing: Optional[RoutingInfo] = None
    verification: Optional[VerificationInfo] = None
    tools_used: List[ToolCallSummary] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    error: Optional[ApiError] = None
    execution_time_ms: Optional[float] = None
    model: Optional[str] = None
    pipeline: Optional[Dict[str, Any]] = None
    raw: Optional[Dict[str, Any]] = None


class OllamaHealth(BaseModel):
    reachable: bool
    base_url: str
    model: str
    #: None when it could not be determined (Ollama unreachable).
    model_available: Optional[bool] = None
    models: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class HealthResponse(BaseModel):
    #: "ok" when the whole chain can serve requests, otherwise "degraded".
    status: Literal["ok", "degraded"]
    backend_version: str
    agent_layer_version: str
    ollama: OllamaHealth
    project_root: str
    project_root_exists: bool
    agents: List[str]
    verification_enabled: bool
    problems: List[str] = Field(default_factory=list)
