"""
agents/tools/base_tool.py
============================

Common interface for all tools usable by Moltress agents.

Every tool:
  - has a stable `name` and `description` (used for LLM tool-calling /
    routing, and for logging),
  - exposes a synchronous `run(**kwargs) -> ToolResult` method,
  - never raises raw exceptions to the agent — it catches internal
    errors and returns a ToolResult with success=False instead, so the
    BaseAgent can handle tool failures gracefully and uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ToolOperationType(str, Enum):
    """
    Classifies what kind of effect a tool has, per the "clearly distinguish
    READ / WRITE / EXECUTION / DESTRUCTIVE operations" requirement.

    This is informational/auditing metadata (surfaced in execution traces
    and ToolInvocationRecord) — the actual safety GATE is still
    `BaseTool.requires_approval`; a tool's operation_type does not by
    itself change execution behavior. In practice: READ tools never
    require approval; WRITE and EXECUTE tools that can cause real
    side-effects (write_file, run_command) set requires_approval=True;
    DESTRUCTIVE is reserved for tools that remove/overwrite data
    irreversibly and MUST always require approval.
    """

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DESTRUCTIVE = "destructive"


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseTool:
    name: str = "base_tool"
    description: str = "Base tool. Override in subclasses."

    # What kind of operation this tool performs — see ToolOperationType.
    operation_type: ToolOperationType = ToolOperationType.READ

    # Destructive/high-risk tools (e.g. writing files, running terminal
    # commands) must set this True. BaseAgent will refuse to execute such
    # a tool unless its name appears in the current
    # AgentRequest.approved_actions — i.e. explicit, per-request approval
    # is required before any such operation.
    requires_approval: bool = False

    def run(self, **kwargs) -> ToolResult:  # pragma: no cover - interface only
        raise NotImplementedError("Tools must implement run()")

    def safe_run(self, **kwargs) -> ToolResult:
        """Wraps run() so tool exceptions never propagate as raw exceptions."""
        try:
            return self.run(**kwargs)
        except Exception as exc:  # noqa: BLE001 - intentional catch-all boundary
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
