"""
Moltress Custom AI Agent Layer (v2)
======================================

A privacy-preserving, local-LLM-backed multi-agent layer for enterprise
software engineering assistance.

This package exposes five specialized agents (Developer, Debugging,
Testing, Security, Documentation) that all share a common BaseAgent
architecture, a common local LLM client (Ollama), and a controlled,
iterative tool-use loop with per-agent tool permissions and
approval-gated destructive actions.

Public API
----------
    from agents import (
        DeveloperAgent,
        DebuggingAgent,
        TestingAgent,
        SecurityAgent,
        DocumentationAgent,
        AgentRouter,
    )
    from agents.schemas.common import AgentRequest

    agent = DeveloperAgent()
    response = agent.run(AgentRequest(query="..."))

    # Or route automatically:
    router = AgentRouter()
    response = router.route_and_run(AgentRequest(query="..."))

See README.md for full documentation, architecture diagrams, tool
permissions, and integration instructions for the main Moltress backend.
"""

from agents.developer_agent import DeveloperAgent
from agents.debugging_agent import DebuggingAgent
from agents.testing_agent import TestingAgent
from agents.security_agent import SecurityAgent
from agents.documentation_agent import DocumentationAgent
from agents.router import AgentRouter
from agents.state import AgentTaskState
from agents.executor import AgentExecutionLoop

__all__ = [
    "DeveloperAgent",
    "DebuggingAgent",
    "TestingAgent",
    "SecurityAgent",
    "DocumentationAgent",
    "AgentRouter",
    "AgentTaskState",
    "AgentExecutionLoop",
]

__version__ = "0.3.0"
