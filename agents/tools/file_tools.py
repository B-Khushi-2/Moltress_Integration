"""
agents/tools/file_tools.py
=============================

File-system tools available to agents: read_file, list_files, search_files.

Safety
------
All paths are resolved against `ToolConfig.project_root` and validated to
ensure they never escape that root (no `..` traversal, no absolute paths
outside the sandbox, no symlink escapes). This is the primary safety
boundary for the whole tool layer — agents must never be able to read
arbitrary files on the host machine.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import List, Optional

from agents.config.agent_config import ToolConfig, get_config
from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult


class PathSecurityError(Exception):
    """Raised when a requested path would escape the sandboxed project root."""


def resolve_safe_path(relative_or_absolute_path: str, root: str) -> Path:
    """
    Resolve a user/agent-supplied path against `root`, raising
    PathSecurityError if the resolved path is not inside `root`.
    """
    root_path = Path(root).resolve()
    candidate = (root_path / relative_or_absolute_path).resolve() \
        if not os.path.isabs(relative_or_absolute_path) \
        else Path(relative_or_absolute_path).resolve()

    try:
        candidate.relative_to(root_path)
    except ValueError:
        raise PathSecurityError(
            f"Path '{relative_or_absolute_path}' resolves outside the sandboxed project root '{root_path}'."
        )
    return candidate


# ---------------------------------------------------------------------------
# Integration hardening (added when the agent layer was wired to a UI/backend)
#
# The sandbox above stops path ESCAPES, but inside the root the model could
# still read credential files (e.g. a developer's local `.env`) or burn its
# whole context budget walking `node_modules`. These helpers are additive:
# they only ever make read-only tools MORE conservative.
# ---------------------------------------------------------------------------

#: Directory names never descended into by the recursive read tools.
IGNORED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "out",
    "build", ".next", ".cache", ".idea", ".vscode",
})

#: Filename patterns that commonly hold secrets. `.env.example`-style
#: templates are explicitly allowed (see `_SENSITIVE_ALLOW`).
_SENSITIVE_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
                       ".npmrc", ".pypirc", ".netrc", "credentials*", "*.keystore")
_SENSITIVE_ALLOW = (".env.example", ".env.sample", ".env.template", ".env.dist")


def is_sensitive_file(path) -> bool:
    """True if `path` looks like a credential/secret file the agents must not read."""
    name = Path(path).name.lower()
    if name in _SENSITIVE_ALLOW:
        return False
    return any(fnmatch.fnmatch(name, pat) for pat in _SENSITIVE_PATTERNS)


def iter_project_files(base: Path, pattern: str = "*"):
    """
    Yield files under `base` matching `pattern` (same semantics as
    `Path.rglob(pattern)` for simple name globs), pruning IGNORED_DIR_NAMES.
    Sensitive files are NOT yielded.
    """
    base = Path(base)
    # A pattern containing a path separator is matched against the path
    # relative to `base`; otherwise against the bare file name.
    match_relative = "/" in pattern
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIR_NAMES)
        for fname in sorted(filenames):
            full = Path(dirpath) / fname
            if is_sensitive_file(full):
                continue
            target = full.relative_to(base).as_posix() if match_relative else fname
            if fnmatch.fnmatch(target, pattern):
                yield full


class ReadFileTool(BaseTool):
    name = "read_file"
    operation_type = ToolOperationType.READ
    description = "Read the contents of a single file within the project sandbox."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, path: str) -> ToolResult:
        try:
            safe_path = resolve_safe_path(path, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if not safe_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")
        if is_sensitive_file(safe_path):
            return ToolResult(
                success=False,
                error=f"Access denied: '{path}' looks like a credentials/secrets file and cannot be read by agents.",
            )

        size = safe_path.stat().st_size
        if size > self.config.max_file_read_bytes:
            return ToolResult(
                success=False,
                error=(
                    f"File '{path}' is {size} bytes, exceeding the "
                    f"max_file_read_bytes limit of {self.config.max_file_read_bytes}."
                ),
            )

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not read file: {exc}")

        return ToolResult(
            success=True,
            data=content,
            summary=f"Read {len(content)} chars from {path}",
            metadata={"path": path, "size_bytes": size},
        )


class ListFilesTool(BaseTool):
    name = "list_files"
    operation_type = ToolOperationType.READ
    description = "List files under a directory within the project sandbox, optionally filtered by glob pattern."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, directory: str = ".", pattern: str = "*", recursive: bool = True) -> ToolResult:
        try:
            safe_dir = resolve_safe_path(directory, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_dir.exists() or not safe_dir.is_dir():
            return ToolResult(success=False, error=f"Directory not found: {directory}")

        results: List[str] = []
        walker = (
            iter_project_files(safe_dir, pattern)
            if recursive
            else (q for q in safe_dir.glob(pattern) if not is_sensitive_file(q))
        )
        for p in walker:
            if p.is_file():
                results.append(str(p.relative_to(Path(self.config.project_root).resolve())))
                if len(results) >= self.config.max_search_results:
                    break

        return ToolResult(
            success=True,
            data=results,
            summary=f"Found {len(results)} file(s) matching '{pattern}' in {directory}",
        )


class SearchFilesTool(BaseTool):
    name = "search_files"
    operation_type = ToolOperationType.READ
    description = "Search for a text pattern across files within the project sandbox."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, query: str, directory: str = ".", file_glob: str = "*.py") -> ToolResult:
        try:
            safe_dir = resolve_safe_path(directory, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_dir.exists() or not safe_dir.is_dir():
            return ToolResult(success=False, error=f"Directory not found: {directory}")

        matches = []
        for path in iter_project_files(safe_dir, file_glob):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    rel = str(path.relative_to(Path(self.config.project_root).resolve()))
                    matches.append({"file": rel, "line": lineno, "text": line.strip()})
                    if len(matches) >= self.config.max_search_results:
                        break
            if len(matches) >= self.config.max_search_results:
                break

        return ToolResult(
            success=True,
            data=matches,
            summary=f"Found {len(matches)} match(es) for '{query}' under {directory}",
        )


class WriteFileTool(BaseTool):
    """
    Write (create or overwrite) a single file within the project sandbox.

    This is a DESTRUCTIVE operation: `requires_approval = True` means
    BaseAgent will refuse to execute it unless the current AgentRequest
    explicitly includes "write_file" in `approved_actions`. It is also
    gated at registration time by `ToolConfig.enable_write_tool`
    (default False) — even agents that list it in `allowed_tool_names`
    (currently only DeveloperAgent) won't actually get it registered
    unless an operator has opted in via ENABLE_WRITE_TOOL=true.
    """

    name = "write_file"
    operation_type = ToolOperationType.DESTRUCTIVE
    description = (
        "Create or overwrite a single file within the project sandbox. "
        "Destructive — requires explicit per-request approval."
    )
    requires_approval = True

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, path: str, content: str) -> ToolResult:
        try:
            safe_path = resolve_safe_path(path, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if len(content.encode("utf-8", errors="replace")) > self.config.max_file_read_bytes:
            return ToolResult(
                success=False,
                error=(
                    f"Refusing to write {len(content)} chars to '{path}': exceeds "
                    f"max_file_read_bytes limit of {self.config.max_file_read_bytes}."
                ),
            )

        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            existed = safe_path.exists()
            safe_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not write file: {exc}")

        return ToolResult(
            success=True,
            data={"path": path, "bytes_written": len(content.encode("utf-8"))},
            summary=f"{'Overwrote' if existed else 'Created'} {path} ({len(content)} chars)",
            metadata={"path": path, "overwritten": existed},
        )
