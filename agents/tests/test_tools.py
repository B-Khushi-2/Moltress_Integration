"""
agents/tests/test_tools.py

Tests for the shared tool layer, especially the sandboxing/security
guarantees of the file tools and the restrictions on the terminal tool.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from agents.config.agent_config import ToolConfig
from agents.tools.file_tools import ReadFileTool, ListFilesTool, WriteFileTool, PathSecurityError, resolve_safe_path
from agents.tools.log_tools import ReadLogsTool
from agents.tools.terminal_tools import TerminalTool


@pytest.fixture
def sandbox_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "sample.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b\n")
        os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
        with open(os.path.join(tmp, "sub", "nested.py"), "w") as f:
            f.write("x = 1\n")
        yield tmp


def test_resolve_safe_path_blocks_traversal(sandbox_dir):
    with pytest.raises(PathSecurityError):
        resolve_safe_path("../../etc/passwd", sandbox_dir)


def test_read_file_tool_reads_within_sandbox(sandbox_dir):
    tool = ReadFileTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="sample.py")
    assert result.success
    assert "def add" in result.data


def test_read_file_tool_rejects_outside_sandbox(sandbox_dir):
    tool = ReadFileTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="../outside.py")
    assert not result.success
    assert "outside" in result.error.lower() or "not found" in result.error.lower()


def test_list_files_tool_finds_nested_files(sandbox_dir):
    tool = ListFilesTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(directory=".", pattern="*.py", recursive=True)
    assert result.success
    assert any("nested.py" in p for p in result.data)


def test_terminal_tool_disabled_by_default(sandbox_dir):
    tool = TerminalTool(ToolConfig(project_root=sandbox_dir, enable_terminal_tool=False))
    result = tool.safe_run(command="pytest -q")
    assert not result.success
    assert "disabled" in result.error.lower()


def test_terminal_tool_rejects_non_whitelisted_command(sandbox_dir):
    tool = TerminalTool(ToolConfig(project_root=sandbox_dir, enable_terminal_tool=True, allowed_commands=["pytest"]))
    result = tool.safe_run(command="rm -rf /")
    assert not result.success


def test_terminal_tool_rejects_shell_metacharacters(sandbox_dir):
    tool = TerminalTool(ToolConfig(project_root=sandbox_dir, enable_terminal_tool=True, allowed_commands=["pytest"]))
    result = tool.safe_run(command="pytest -q && rm -rf /")
    assert not result.success


def test_write_file_tool_requires_approval_flag_is_set(sandbox_dir):
    tool = WriteFileTool(ToolConfig(project_root=sandbox_dir))
    assert tool.requires_approval is True


def test_write_file_tool_creates_file_within_sandbox(sandbox_dir):
    tool = WriteFileTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="new_file.py", content="x = 1\n")
    assert result.success
    with open(os.path.join(sandbox_dir, "new_file.py")) as f:
        assert f.read() == "x = 1\n"


def test_write_file_tool_rejects_path_outside_sandbox(sandbox_dir):
    tool = WriteFileTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="../escape.py", content="x = 1\n")
    assert not result.success


def test_read_logs_tool_reads_tail_of_log_file(sandbox_dir):
    log_path = os.path.join(sandbox_dir, "app.log")
    with open(log_path, "w") as f:
        for i in range(10):
            f.write(f"line {i}\n")
    tool = ReadLogsTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="app.log", max_lines=3)
    assert result.success
    assert "line 9" in result.data
    assert "line 7" in result.data
    assert "line 0" not in result.data


def test_read_logs_tool_rejects_missing_file(sandbox_dir):
    tool = ReadLogsTool(ToolConfig(project_root=sandbox_dir))
    result = tool.safe_run(path="missing.log")
    assert not result.success
