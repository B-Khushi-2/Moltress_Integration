"""
agents/tools/code_tools.py
=============================

Lightweight, dependency-free code-inspection tools: search_code,
inspect_source (functions/classes via the `ast` module for Python;
regex fallback for other languages), and inspect_project (project-level
summary).

These are intentionally simple static-analysis helpers, not a full
language-server implementation — appropriate for a final-year project
while still being genuinely useful and non-fake.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.config.agent_config import ToolConfig, get_config
from agents.tools.base_tool import BaseTool, ToolOperationType, ToolResult
from agents.tools.file_tools import (
    PathSecurityError,
    is_sensitive_file,
    iter_project_files,
    resolve_safe_path,
)


class InspectSourceTool(BaseTool):
    operation_type = ToolOperationType.READ
    """Extract functions/classes/imports from a source file."""

    name = "inspect_source"
    description = "Parse a source file and list its functions, classes, and imports."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, path: str) -> ToolResult:
        try:
            safe_path = resolve_safe_path(path, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_path.exists() or not safe_path.is_file():
            return ToolResult(success=False, error=f"File not found: {path}")
        if is_sensitive_file(safe_path):
            return ToolResult(
                success=False,
                error=f"Access denied: '{path}' looks like a credentials/secrets file and cannot be read by agents.",
            )

        try:
            source = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not read file: {exc}")

        if safe_path.suffix == ".py":
            return self._inspect_python(source, path)
        return self._inspect_generic(source, path)

    @staticmethod
    def _inspect_python(source: str, path: str) -> ToolResult:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return ToolResult(success=False, error=f"Python syntax error while parsing {path}: {exc}")

        functions: List[Dict[str, Any]] = []
        classes: List[Dict[str, Any]] = []
        imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append(
                    {
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": [a.arg for a in node.args.args],
                        "docstring": ast.get_docstring(node),
                    }
                )
            elif isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append(
                    {
                        "name": node.name,
                        "lineno": node.lineno,
                        "methods": methods,
                        "docstring": ast.get_docstring(node),
                    }
                )
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        data = {"functions": functions, "classes": classes, "imports": sorted(set(imports))}
        return ToolResult(
            success=True,
            data=data,
            summary=f"{path}: {len(functions)} function(s), {len(classes)} class(es), {len(set(imports))} import(s)",
        )

    @staticmethod
    def _inspect_generic(source: str, path: str) -> ToolResult:
        """Regex-based best-effort inspection for non-Python files."""
        func_pattern = re.compile(
            r"\b(?:function|def|func|public|private|protected|static)\s+[\w<>\[\], ]*?(\w+)\s*\("
        )
        class_pattern = re.compile(r"\bclass\s+(\w+)")

        functions = sorted(set(func_pattern.findall(source)))
        classes = sorted(set(class_pattern.findall(source)))

        return ToolResult(
            success=True,
            data={"functions": functions, "classes": classes, "imports": []},
            summary=f"{path}: best-effort scan found {len(functions)} function-like symbol(s), {len(classes)} class(es)",
            metadata={"note": "Non-Python file; used regex-based heuristic scan, not a full parser."},
        )


class SearchCodeTool(BaseTool):
    operation_type = ToolOperationType.READ
    """Search for a symbol (function/class name) across the project."""

    name = "search_code"
    description = "Search the project for a given symbol name (function, class, or identifier)."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, symbol: str, file_glob: str = "*") -> ToolResult:
        root = Path(self.config.project_root).resolve()
        if not root.exists():
            return ToolResult(success=False, error=f"Project root does not exist: {root}")

        pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        matches: List[Dict[str, Any]] = []

        for path in iter_project_files(root, file_glob):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({"file": str(path.relative_to(root)), "line": lineno, "text": line.strip()})
                    if len(matches) >= self.config.max_search_results:
                        break
            if len(matches) >= self.config.max_search_results:
                break

        return ToolResult(
            success=True,
            data=matches,
            summary=f"Found {len(matches)} reference(s) to '{symbol}'",
        )


class InspectProjectTool(BaseTool):
    operation_type = ToolOperationType.READ
    """Produce a high-level structural summary of the project."""

    name = "inspect_project"
    description = "Summarize the project's directory structure and file counts by type."

    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or get_config().tools

    def run(self, directory: str = ".") -> ToolResult:
        try:
            safe_dir = resolve_safe_path(directory, self.config.project_root)
        except PathSecurityError as exc:
            return ToolResult(success=False, error=str(exc))

        if not safe_dir.exists() or not safe_dir.is_dir():
            return ToolResult(success=False, error=f"Directory not found: {directory}")

        extension_counts: Dict[str, int] = {}
        total_files = 0
        top_level_dirs: List[str] = []

        from agents.tools.file_tools import IGNORED_DIR_NAMES

        for entry in safe_dir.iterdir():
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in IGNORED_DIR_NAMES:
                top_level_dirs.append(entry.name)

        for path in iter_project_files(safe_dir, "*"):
            if path.is_file():
                total_files += 1
                ext = path.suffix or "(no extension)"
                extension_counts[ext] = extension_counts.get(ext, 0) + 1

        return ToolResult(
            success=True,
            data={
                "total_files": total_files,
                "extension_counts": extension_counts,
                "top_level_dirs": sorted(top_level_dirs),
            },
            summary=f"Project has {total_files} file(s) across {len(top_level_dirs)} top-level director(y/ies)",
        )
