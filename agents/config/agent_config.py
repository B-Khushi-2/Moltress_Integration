"""
agents/config/agent_config.py
==============================

Centralized, environment-driven configuration for the Moltress Agent Layer.

Nothing in the agents package should hard-code model names, hosts, ports,
paths, or tool settings. Everything flows through this module, which reads
from environment variables (optionally loaded from a `.env` file) and
falls back to sane local-first defaults.

This keeps the agent layer:
  - Privacy-preserving (no cloud endpoints by default)
  - Portable (swap models/hosts without touching agent code)
  - Easy to integrate into a FastAPI backend (just set env vars)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    # Optional dependency. If python-dotenv isn't installed, we simply skip
    # .env loading and rely on real environment variables.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - purely an optional convenience
    pass


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _first_env(*names: str, default: str = "") -> str:
    """Return the first non-empty environment variable among `names`.

    Used so the preferred, portable names (OLLAMA_BASE_URL / OLLAMA_MODEL)
    work alongside the original agent-layer names (OLLAMA_HOST / MODEL_NAME),
    which remain fully supported for backward compatibility.
    """
    for name in names:
        val = os.getenv(name)
        if val is not None and val.strip():
            return val.strip()
    return default


def _get_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    val = os.getenv(name)
    if not val:
        return default or []
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass(frozen=True)
class OllamaConfig:
    """Configuration for the local Ollama LLM runtime."""

    # Preferred: OLLAMA_BASE_URL / OLLAMA_MODEL. Legacy aliases OLLAMA_HOST /
    # MODEL_NAME are still honoured so existing deployments keep working.
    host: str = field(
        default_factory=lambda: _first_env("OLLAMA_BASE_URL", "OLLAMA_HOST", default="http://localhost:11434")
    )
    model: str = field(default_factory=lambda: _first_env("OLLAMA_MODEL", "MODEL_NAME", default="qwen2.5-coder:7b"))
    temperature: float = field(default_factory=lambda: float(os.getenv("MODEL_TEMPERATURE", "0.2")))
    top_p: float = field(default_factory=lambda: float(os.getenv("MODEL_TOP_P", "0.9")))
    max_tokens: int = field(default_factory=lambda: _get_int("MODEL_MAX_TOKENS", 2048))
    request_timeout_seconds: int = field(default_factory=lambda: _get_int("OLLAMA_TIMEOUT_SECONDS", 300))
    num_retries: int = field(default_factory=lambda: _get_int("OLLAMA_NUM_RETRIES", 2))
    json_mode: bool = field(default_factory=lambda: _get_bool("MODEL_JSON_MODE", True))


@dataclass(frozen=True)
class ToolConfig:
    """Configuration for the sandboxed tool layer."""

    # Root directory that all file/code tools are restricted to. This is the
    # single most important safety boundary in the tool layer: no file tool
    # may read or write outside this directory.
    project_root: str = field(default_factory=lambda: os.getenv("MOLTRESS_PROJECT_ROOT", os.getcwd()))

    # Whether terminal command execution is permitted at all.
    enable_terminal_tool: bool = field(default_factory=lambda: _get_bool("ENABLE_TERMINAL_TOOL", False))

    # Whitelist of terminal command prefixes that MAY be executed when the
    # terminal tool is enabled. Anything not matching this list is rejected.
    allowed_commands: List[str] = field(
        default_factory=lambda: _get_list(
            "ALLOWED_TERMINAL_COMMANDS",
            ["pytest", "python -m pytest", "python -m pyflakes", "python -m py_compile"],
        )
    )

    terminal_timeout_seconds: int = field(default_factory=lambda: _get_int("TERMINAL_TIMEOUT_SECONDS", 30))

    # Whether test-execution tooling is permitted.
    enable_test_execution: bool = field(default_factory=lambda: _get_bool("ENABLE_TEST_EXECUTION", False))

    max_file_read_bytes: int = field(default_factory=lambda: _get_int("MAX_FILE_READ_BYTES", 200_000))
    max_search_results: int = field(default_factory=lambda: _get_int("MAX_SEARCH_RESULTS", 25))

    # Whether the (destructive) write_file tool may be registered at all.
    # Even when enabled, WriteFileTool.requires_approval=True means a
    # request must still explicitly approve the write via
    # AgentRequest.approved_actions.
    enable_write_tool: bool = field(default_factory=lambda: _get_bool("ENABLE_WRITE_TOOL", False))

    # Per-call wall-clock timeout enforced by BaseAgent around every tool
    # invocation, independent of any timeout the tool enforces internally
    # (e.g. TerminalTool has its own subprocess timeout; this is a second,
    # outer safety net for tools that don't manage their own timeout).
    tool_call_timeout_seconds: int = field(default_factory=lambda: _get_int("TOOL_CALL_TIMEOUT_SECONDS", 30))


@dataclass(frozen=True)
class OrchestrationConfig:
    """Configuration for the controlled, iterative tool-use loop inside BaseAgent.run()."""

    # Hard ceiling on how many LLM turns / tool calls a single agent.run()
    # invocation may take before it is forced to stop and return whatever
    # it has (per the "controlled autonomy" requirement — never unbounded).
    max_tool_iterations: int = field(default_factory=lambda: _get_int("MAX_TOOL_ITERATIONS", 6))

    # If the same tool fails (or is denied approval) this many times in a
    # row, the loop stops early rather than retrying indefinitely.
    max_consecutive_tool_failures: int = field(
        default_factory=lambda: _get_int("MAX_CONSECUTIVE_TOOL_FAILURES", 2)
    )


@dataclass(frozen=True)
class LoggingConfig:
    level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: Optional[str] = field(default_factory=lambda: os.getenv("LOG_FILE") or None)
    # If True, request/response payloads (which may contain source code) are
    # never written to logs, only metadata (agent name, duration, status).
    redact_payloads: bool = field(default_factory=lambda: _get_bool("LOG_REDACT_PAYLOADS", True))


@dataclass(frozen=True)
class AgentConfig:
    """Top-level configuration object aggregating all sub-configs."""

    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Global feature flags for the integration points described in the
    # Moltress SRS. These default to False/None because the real RAG,
    # Knowledge Graph, Memory, and Verification modules are integrated
    # later by other teams.
    rag_enabled: bool = field(default_factory=lambda: _get_bool("RAG_ENABLED", False))
    graph_enabled: bool = field(default_factory=lambda: _get_bool("GRAPH_ENABLED", False))
    memory_enabled: bool = field(default_factory=lambda: _get_bool("MEMORY_ENABLED", False))

    # Optional global allow-lists. None means "no additional restriction
    # beyond each agent's own default tool/permission set". When set, these
    # further narrow what is enabled process-wide — useful for e.g. a
    # locked-down demo/CI profile.
    enabled_agents: Optional[List[str]] = field(
        default_factory=lambda: _get_list("ENABLED_AGENTS", None) or None
    )
    enabled_tools: Optional[List[str]] = field(
        default_factory=lambda: _get_list("ENABLED_TOOLS", None) or None
    )


# Module-level singleton. Agents/tools should import `get_config()` rather
# than instantiating AgentConfig() directly, so that a single consistent
# configuration is shared across the process (while still remaining easy
# to override in tests via `get_config.cache_clear()` style patterns or by
# constructing AgentConfig() explicitly with overrides).
_default_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """Return the process-wide AgentConfig singleton, creating it if needed."""
    global _default_config
    if _default_config is None:
        _default_config = AgentConfig()
    return _default_config


def reset_config() -> None:
    """Reset the cached singleton (mainly useful in tests)."""
    global _default_config
    _default_config = None
