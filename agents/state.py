"""
agents/state.py
=================

AgentTaskState: explicit, in-memory state tracking for a single agent.run()
invocation.

Per the "agent state" requirement, an autonomous agent must not rely on
conversation text alone to know what it has already done. This object is
threaded through the tool-use loop in BaseAgent and records, as plain
structured data (not prose the LLM has to re-derive):

  - the original request and (once known) the working objective
  - each step taken, in order
  - every tool call attempted, with its outcome
  - assumptions the agent has made
  - errors encountered
  - intermediate findings
  - the final result, once produced

This is intentionally a plain Python object (not a Pydantic schema) since
it is internal bookkeeping for a single `run()` call and is never returned
directly to the caller — relevant parts of it are surfaced via
`AgentResponse.tools_used`, `.assumptions`, `.warnings`, and
`.metadata["task_state"]`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.schemas.common import ToolInvocationRecord


@dataclass
class AgentTaskState:
    request_id: str
    original_query: str

    objective: Optional[str] = None
    iteration: int = 0
    status: str = "in_progress"  # in_progress | completed | stopped_max_iterations |
    #                              stopped_tool_failures | stopped_needs_approval | error

    steps: List[str] = field(default_factory=list)
    tools_used: List[ToolInvocationRecord] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    final_result: Optional[Dict[str, Any]] = None

    _consecutive_tool_failures: int = 0
    _seen_tool_calls: set = field(default_factory=set)
    _started_at: float = field(default_factory=time.monotonic)

    # -- Mutators ---------------------------------------------------------

    def record_step(self, description: str) -> None:
        self.steps.append(description)

    def record_tool_call(self, record: ToolInvocationRecord, arguments_key: Optional[str] = None) -> None:
        self.tools_used.append(record)
        if arguments_key is not None:
            self._seen_tool_calls.add(arguments_key)
        if record.success:
            self._consecutive_tool_failures = 0
        else:
            self._consecutive_tool_failures += 1

    def record_finding(self, finding: str) -> None:
        self.findings.append(finding)

    def record_assumption(self, assumption: str) -> None:
        if assumption not in self.assumptions:
            self.assumptions.append(assumption)

    def record_error(self, error: str) -> None:
        self.errors.append(error)

    def has_seen_tool_call(self, arguments_key: str) -> bool:
        return arguments_key in self._seen_tool_calls

    # -- Queries ------------------------------------------------------------

    def consecutive_tool_failures(self) -> int:
        return self._consecutive_tool_failures

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._started_at

    def to_metadata(self) -> Dict[str, Any]:
        """Compact, JSON-safe summary suitable for AgentResponse.metadata['task_state']."""
        return {
            "objective": self.objective,
            "iterations": self.iteration,
            "status": self.status,
            "steps": list(self.steps),
            "tool_call_count": len(self.tools_used),
            "findings": list(self.findings),
            "errors": list(self.errors),
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
        }

    def render_trace(self, agent_name: str) -> str:
        """
        Render a plain-text execution trace in the style requested for
        the LLMOps dashboard, e.g.:

            Task Started
            Agent: DebuggingAgent

            Step 1
            Action: search_code
            Status: success

            Step 2
            Action: read_file
            Status: success

            Final
            Status: completed

        Deliberately excludes tool arguments/data (which may contain
        source code) — only action names and outcomes, matching the
        "do not log sensitive source code or secrets unnecessarily"
        requirement.
        """
        lines = ["Task Started", f"Agent: {agent_name}", ""]
        for i, record in enumerate(self.tools_used, start=1):
            outcome = "denied" if record.denied else ("success" if record.success else "failed")
            lines.append(f"Step {i}")
            lines.append(f"Action: {record.tool_name}")
            lines.append(f"Status: {outcome}")
            lines.append("")
        lines.append("Final")
        lines.append(f"Status: {self.status}")
        return "\n".join(lines)
