"""
agents/router.py
==================

A simple, modular router that decides which specialized agent should
handle a given AgentRequest.

Design: a lightweight keyword/heuristic classifier by default (fast,
free, fully local, deterministic, no extra LLM call required), with an
optional LLM-based fallback for ambiguous queries. This keeps the router
itself simple and dependency-light per the project's "do not
overcomplicate the router" requirement, while still being genuinely
useful — and it now returns a full RoutingDecision (agent, reason,
confidence) rather than a bare string, so routing behavior is auditable.

Adding a new agent later only requires:
  1. Implementing the new agent (subclassing BaseAgent).
  2. Adding one entry to `_AGENT_REGISTRY` and a keyword rule below.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Type

from agents.base_agent import BaseAgent
from agents.config.agent_config import AgentConfig, get_config
from agents.debugging_agent import DebuggingAgent
from agents.developer_agent import DeveloperAgent
from agents.documentation_agent import DocumentationAgent
from agents.llm.ollama_client import LLMMessage, OllamaClient, get_llm_client
from agents.providers import GraphProvider, MemoryProvider, RAGProvider, VerificationProvider
from agents.schemas.common import AgentRequest, AgentResponse, RoutingDecision
from agents.security_agent import SecurityAgent
from agents.testing_agent import TestingAgent

logger = logging.getLogger("moltress.agents.router")

# Ordered by specificity: more specific/high-signal keyword sets should be
# checked before more generic ones (e.g. "test" keywords before generic
# "write" keywords that might overlap with the Developer Agent).
_KEYWORD_RULES: List[tuple] = [
    (
        "security_agent",
        re.compile(
            r"\b(vulnerabilit\w*|security|secrets?|exploit|insecure|cve|owasp|"
            r"sql injection|xss|csrf|hardcoded (password|credential|key)|penetration)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "debugging_agent",
        re.compile(
            r"\b(bug|error|exception|traceback|stack trace|crash(?:es|ing|ed)?|"
            r"fails?|failing|failure|debug\w*|root cause|why is this|500\b|not working)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "testing_agent",
        re.compile(
            r"\b(unit tests?|integration tests?|test cases?|write tests?|edge cases?|"
            r"test coverage|pytest|failing tests?|assert\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "documentation_agent",
        re.compile(
            r"\b(document\w*|docstring\w*|readme|api docs?|explain (this|the) (module|class|function)|"
            r"generate docs?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "developer_agent",
        re.compile(
            r"\b(refactor|implement|write a function|write a class|generate code|"
            r"create a (function|class|module|endpoint)|improve this code|design approach)\b",
            re.IGNORECASE,
        ),
    ),
]

_AGENT_REGISTRY: Dict[str, Type[BaseAgent]] = {
    "developer_agent": DeveloperAgent,
    "debugging_agent": DebuggingAgent,
    "testing_agent": TestingAgent,
    "security_agent": SecurityAgent,
    "documentation_agent": DocumentationAgent,
}

_DEFAULT_AGENT = "developer_agent"

_ROUTING_SYSTEM_PROMPT = """
You are a routing classifier for the Moltress multi-agent system. Given a
user's request, respond with ONLY one of these exact labels, nothing else:
developer_agent, debugging_agent, testing_agent, security_agent, documentation_agent
""".strip()


class AgentRouter:
    """
    Routes an AgentRequest to the most appropriate specialized agent.

    Usage
    -----
        router = AgentRouter()
        response = router.route_and_run(request)          # execute directly

        decision = router.route(request.query)             # just the decision
        print(decision.agent_name, decision.reason, decision.confidence)

        agent_name = router.classify(request.query)         # v1-compatible: bare string
    """

    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        config: Optional[AgentConfig] = None,
        use_llm_fallback: bool = True,
        rag_provider: Optional[RAGProvider] = None,
        graph_provider: Optional[GraphProvider] = None,
        memory_provider: Optional[MemoryProvider] = None,
        verification_provider: Optional[VerificationProvider] = None,
    ):
        self.llm_client = llm_client or get_llm_client()
        self.config = config or get_config()
        self.use_llm_fallback = use_llm_fallback

        # Providers are constructed once here and shared across every agent
        # instance the router creates, so a FastAPI app can wire real
        # RAG/Graph/Memory/Verification providers into a single AgentRouter
        # and have them apply consistently to every routed request.
        self.rag_provider = rag_provider
        self.graph_provider = graph_provider
        self.memory_provider = memory_provider
        self.verification_provider = verification_provider

        self._agent_instances: Dict[str, BaseAgent] = {}

    def register_agent(self, name: str, agent_cls: Type[BaseAgent]) -> None:
        """Allow callers to add/override agents in the registry at runtime."""
        _AGENT_REGISTRY[name] = agent_cls

    def _enabled_agent_names(self) -> List[str]:
        """Respect AgentConfig.enabled_agents, if the operator set one."""
        if self.config.enabled_agents is None:
            return list(_AGENT_REGISTRY.keys())
        return [name for name in _AGENT_REGISTRY.keys() if name in self.config.enabled_agents]

    def route(self, query: str) -> RoutingDecision:
        """
        Classify `query` and return a full RoutingDecision (agent name,
        human-readable reason, and a confidence score) rather than a bare
        string, so the decision can be logged/audited/surfaced to a caller.
        """
        enabled = self._enabled_agent_names()

        for agent_name, pattern in _KEYWORD_RULES:
            if agent_name not in enabled:
                continue
            match = pattern.search(query)
            if match:
                logger.debug("Router matched '%s' via keyword rule", agent_name)
                return RoutingDecision(
                    agent_name=agent_name,
                    reason=f"Query matched the '{agent_name}' keyword pattern (e.g. '{match.group(0)}').",
                    confidence=0.9,
                    matched_rule="keyword",
                )

        if self.use_llm_fallback and self.llm_client.is_available():
            try:
                result = self.llm_client.chat(
                    system_prompt=_ROUTING_SYSTEM_PROMPT,
                    messages=[LLMMessage(role="user", content=query)],
                    json_mode=False,
                    temperature=0.0,
                )
                candidate = result.text.strip().lower()
                if candidate in enabled:
                    logger.debug("Router matched '%s' via LLM fallback", candidate)
                    return RoutingDecision(
                        agent_name=candidate,
                        reason="No keyword rule matched; the local LLM classified this query as best "
                        f"suited to '{candidate}'.",
                        confidence=0.6,
                        matched_rule="llm_fallback",
                    )
            except Exception as exc:  # noqa: BLE001 - routing fallback must never crash the app
                logger.warning("LLM routing fallback failed, defaulting to %s: %s", _DEFAULT_AGENT, exc)

        default_agent = _DEFAULT_AGENT if _DEFAULT_AGENT in enabled else (enabled[0] if enabled else _DEFAULT_AGENT)
        return RoutingDecision(
            agent_name=default_agent,
            reason="No keyword rule matched and no confident LLM classification was available; "
            f"falling back to the general-purpose '{default_agent}'.",
            confidence=0.3,
            matched_rule="default",
        )

    def classify(self, query: str) -> str:
        """v1-compatible: return just the agent_name that should handle `query`."""
        return self.route(query).agent_name

    def get_agent(self, agent_name: str) -> BaseAgent:
        """Get (and cache) an instance of the named agent."""
        if agent_name not in _AGENT_REGISTRY:
            raise ValueError(f"Unknown agent '{agent_name}'. Known agents: {list(_AGENT_REGISTRY.keys())}")
        if self.config.enabled_agents is not None and agent_name not in self.config.enabled_agents:
            raise ValueError(
                f"Agent '{agent_name}' is disabled by configuration (ENABLED_AGENTS={self.config.enabled_agents})."
            )
        if agent_name not in self._agent_instances:
            self._agent_instances[agent_name] = _AGENT_REGISTRY[agent_name](
                llm_client=self.llm_client,
                config=self.config,
                rag_provider=self.rag_provider,
                graph_provider=self.graph_provider,
                memory_provider=self.memory_provider,
                verification_provider=self.verification_provider,
            )
        return self._agent_instances[agent_name]

    def route_and_run(self, request: AgentRequest) -> AgentResponse:
        """Classify the request, run it against the chosen agent, and return its response."""
        decision = self.route(request.query)
        agent = self.get_agent(decision.agent_name)
        logger.info(
            "Routed request %s to %s (confidence=%.2f, rule=%s)",
            request.request_id, decision.agent_name, decision.confidence, decision.matched_rule,
        )
        response = agent.run(request)
        response.metadata["routing_decision"] = decision.model_dump()
        return response
