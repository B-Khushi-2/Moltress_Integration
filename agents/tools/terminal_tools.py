"""
agents/tools/terminal_tools.py
=================================

A deliberately restricted terminal-execution tool.

Design constraints (per Moltress security requirements):
  - Disabled by default (`ENABLE_TERMINAL_TOOL=false`).
  - Even when enabled, only commands whose prefix matches an explicit
    allow-list (`ToolConfig.allowed_commands`) may run.
  - No shell metacharacters are honored (`shell=False`); no piping,
    redirection, command chaining (`&&`, `;`, `|`, backticks) or
    environment-variable expansion is possible via this tool.
  - Execution is confined to `ToolConfig.project_root` as the working
    directory.
  - A hard timeout is enforced.

This is intentionally NOT a general-purpose shell — it exists to support
narrow, auditable use cases like running a test suite or a linter.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import List, Optional

from agents.config.agent_config import ToolConfig, get_config
from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult

# Characters/tokens that must never appear in a command we execute, even
# though shell=False already prevents shell interpretation — this is a
# defense-in-depth belt-and-braces check against callers that might later
# change the invocation style.
_FORBIDDEN_TOKENS = ["&&", "||", ";", "|", "`", "$(", ">", "<", "\n"]


class CommandNotAllowedError(Exception):
    pass


class TerminalTool(BaseTool):
    name = "run_command"
    operation_type = ToolOperationType.EXECUTE
    # Terminal commands can have real side effects; require explicit
    # per-request approval even though the command itself is whitelisted.
    requires_approval = True
    description = (
        "Execute a whitelisted, read-only-oriented command (e.g. running tests or a linter) "
        "inside the sandboxed project directory. Disabled by default."
    )

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def _validate(self, command: str) -> List[str]:
        if not self.config.enable_terminal_tool:
            raise CommandNotAllowedError("Terminal tool is disabled (ENABLE_TERMINAL_TOOL=false).")

        for token in _FORBIDDEN_TOKENS:
            if token in command:
                raise CommandNotAllowedError(f"Command contains a forbidden token: '{token}'")

        if not any(command.strip().startswith(prefix) for prefix in self.config.allowed_commands):
            raise CommandNotAllowedError(
                f"Command '{command}' does not match any allowed prefix: {self.config.allowed_commands}"
            )

        return shlex.split(command)

    def run(self, command: str) -> ToolResult:
        try:
            argv = self._validate(command)
        except CommandNotAllowedError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            proc = subprocess.run(
                argv,
                cwd=self.config.project_root,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.config.terminal_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Command timed out after {self.config.terminal_timeout_seconds}s",
            )
        except FileNotFoundError as exc:
            return ToolResult(success=False, error=f"Command not found: {exc}")

        return ToolResult(
            success=proc.returncode == 0,
            data={"stdout": proc.stdout[-10000:], "stderr": proc.stderr[-10000:], "return_code": proc.returncode},
            summary=f"Command exited with code {proc.returncode}",
        )
