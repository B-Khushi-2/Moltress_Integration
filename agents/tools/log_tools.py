"""
agents/tools/log_tools.py
============================

Log-reading tool for the Debugging Agent.

Distinct from `read_file` mainly in intent/semantics (and a tail-oriented
default) — logs are often large, append-only files where only the most
recent lines matter for diagnosing a fresh error. Still fully sandboxed
via the same `resolve_safe_path` boundary as the other file tools.
"""

from __future__ import annotations

from typing import Optional

from agents.config.agent_config import ToolConfig, get_config
from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult
from agents.tools.file_tools import PathSecurityError, resolve_safe_path


class ReadLogsTool(BaseTool):
    name = "read_logs"
    operation_type = ToolOperationType.READ
    description = "Read the tail of a log file within the project sandbox (most recent lines first-priority)."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, path: str, max_lines: int = 200) -> ToolResult:
        try:
            safe_path = resolve_safe_path(path, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_path.exists():
            return ToolResult(success=False, error=f"Log file not found: {path}")
        if not safe_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")

        size = safe_path.stat().st_size
        if size > self.config.max_file_read_bytes:
            # Still useful: read only the tail rather than refusing outright,
            # since logs are exactly the case where the tail is what matters.
            try:
                with safe_path.open("rb") as f:
                    f.seek(max(0, size - self.config.max_file_read_bytes))
                    raw = f.read()
                text = raw.decode("utf-8", errors="replace")
                truncated = True
            except OSError as exc:
                return ToolResult(success=False, error=f"Could not read log file: {exc}")
        else:
            try:
                text = safe_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return ToolResult(success=False, error=f"Could not read log file: {exc}")
            truncated = False

        lines = text.splitlines()
        tail = lines[-max_lines:] if max_lines > 0 else lines
        content = "\n".join(tail)

        return ToolResult(
            success=True,
            data=content,
            summary=f"Read last {len(tail)} line(s) of {path}" + (" (file truncated from head)" if truncated else ""),
            metadata={"path": path, "total_lines_in_tail": len(tail), "size_bytes": size},
        )
