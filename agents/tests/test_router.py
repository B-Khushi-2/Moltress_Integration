"""
agents/tests/test_router.py

Tests for the AgentRouter: keyword-based classification, the v2
RoutingDecision (reason + confidence), enabled_agents restriction, and
route_and_run's routing-metadata attachment.
"""

from __future__ import annotations

import pytest

from agents.config.agent_config import AgentConfig
from agents.router import AgentRouter
from agents.schemas.common import AgentRequest


def test_router_routes_debugging_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("Why is this API returning 500?") == "debugging_agent"


def test_router_routes_testing_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("Write unit tests for this function.") == "testing_agent"


def test_router_routes_security_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("Check this code for security vulnerabilities.") == "security_agent"


def test_router_routes_documentation_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("Generate documentation for this module.") == "documentation_agent"


def test_router_routes_developer_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("Refactor this class.") == "developer_agent"


def test_router_defaults_to_developer_agent_for_ambiguous_query():
    router = AgentRouter(use_llm_fallback=False)
    assert router.classify("hello there") == "developer_agent"


def test_router_route_returns_full_decision_with_reason_and_confidence():
    router = AgentRouter(use_llm_fallback=False)
    decision = router.route("Why is this API returning 500?")
    assert decision.agent_name == "debugging_agent"
    assert decision.matched_rule == "keyword"
    assert 0.0 <= decision.confidence <= 1.0
    assert "debugging_agent" in decision.reason


def test_router_route_default_has_lower_confidence_than_keyword_match():
    router = AgentRouter(use_llm_fallback=False)
    keyword_decision = router.route("Write unit tests for this function.")
    default_decision = router.route("asdkj qwoiej")
    assert keyword_decision.confidence > default_decision.confidence
    assert default_decision.matched_rule == "default"


def test_router_respects_enabled_agents_config():
    cfg = AgentConfig(enabled_agents=["developer_agent", "testing_agent"])
    router = AgentRouter(use_llm_fallback=False, config=cfg)

    decision = router.route("Check this code for security vulnerabilities.")
    assert decision.agent_name != "security_agent"  # security_agent disabled, falls through


def test_router_get_agent_raises_for_disabled_agent():
    cfg = AgentConfig(enabled_agents=["developer_agent"])
    router = AgentRouter(use_llm_fallback=False, config=cfg)
    with pytest.raises(ValueError):
        router.get_agent("security_agent")


def test_route_and_run_attaches_routing_decision_to_response_metadata(fake_llm_factory):
    canned = {"status": "success", "result": "ok", "confidence": "high", "evidence": [], "assumptions": [], "warnings": []}
    router = AgentRouter(llm_client=fake_llm_factory(canned), use_llm_fallback=False)

    response = router.route_and_run(AgentRequest(query="Refactor this class."))

    assert response.agent_name == "developer_agent"
    assert "routing_decision" in response.metadata
    assert response.metadata["routing_decision"]["agent_name"] == "developer_agent"
