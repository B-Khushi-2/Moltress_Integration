"""
agents/orchestrator.py
========================

Multi-Agent Pipeline Orchestrator for Moltress Agent Layer.

Enables collaborative multi-agent workflows (e.g. Debugging -> Developer -> Testing)
with shared task state, handoff protocols, and verification checks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agents.config.agent_config import AgentConfig, get_config
from agents.debugging_agent import DebuggingAgent
from agents.developer_agent import DeveloperAgent
from agents.documentation_agent import DocumentationAgent
from agents.handoff import HandoffPayload, OrchestrationTaskState
from agents.llm.ollama_client import OllamaClient, get_llm_client
from agents.providers import (
    GraphProvider,
    MemoryProvider,
    RAGProvider,
    VerificationProvider,
)
from agents.router import AgentRouter
from agents.schemas.common import AgentContext, AgentRequest, AgentResponse, SourceFile
from agents.security_agent import SecurityAgent
from agents.testing_agent import TestingAgent

logger = logging.getLogger("moltress.agents.orchestrator")


class AgentOrchestrator:
    """
    Coordinates multi-agent workflows, managing handoffs, shared task state,
    and verification across collaborating specialized agents.
    """

    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        config: Optional[AgentConfig] = None,
        router: Optional[AgentRouter] = None,
        rag_provider: Optional[RAGProvider] = None,
        graph_provider: Optional[GraphProvider] = None,
        memory_provider: Optional[MemoryProvider] = None,
        verification_provider: Optional[VerificationProvider] = None,
    ):
        self.config = config or get_config()
        self.llm_client = llm_client or get_llm_client()
        self.router = router or AgentRouter(
            llm_client=self.llm_client,
            config=self.config,
            rag_provider=rag_provider,
            graph_provider=graph_provider,
            memory_provider=memory_provider,
            verification_provider=verification_provider,
        )

        self.rag_provider = rag_provider
        self.graph_provider = graph_provider
        self.memory_provider = memory_provider
        self.verification_provider = verification_provider

    def run_debug_fix_test_pipeline(
        self,
        request: AgentRequest,
        auto_approve_dev_write: bool = False,
    ) -> OrchestrationTaskState:
        """
        Executes the flagship multi-agent workflow:
            DebuggingAgent (Root cause analysis)
                   ↓ [Handoff]
            DeveloperAgent (Code refactoring / fix)
                   ↓ [Handoff]
            TestingAgent   (Test generation & verification)
        """
        orch_state = OrchestrationTaskState(original_query=request.query)
        logger.info("Starting Debugging -> Developer -> Testing pipeline for request %s", request.request_id)

        # -------------------------------------------------------------------
        # Step 1: Debugging Agent
        # -------------------------------------------------------------------
        debugger = self.router.get_agent("debugging_agent")
        debug_response = debugger.run(request)
        orch_state.record_agent_execution("debugging_agent", debug_response)

        # Build handoff payload from DebuggingAgent -> DeveloperAgent
        root_cause = getattr(debug_response, "root_cause", None) or debug_response.explanation
        suggested_fix = getattr(debug_response, "suggested_fix", None)
        debug_evidence = debug_response.evidence

        handoff_to_dev = orch_state.create_handoff(
            from_agent="debugging_agent",
            to_agent="developer_agent",
            summary=debug_response.result or "Investigated error and identified root cause.",
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            evidence=debug_evidence,
        )

        # -------------------------------------------------------------------
        # Step 2: Developer Agent
        # -------------------------------------------------------------------
        dev_query = (
            f"Fix the issue identified by the Debugging Agent: {handoff_to_dev.summary}\n"
            f"Root Cause: {handoff_to_dev.root_cause or 'See error context'}\n"
            f"Suggested Fix: {handoff_to_dev.suggested_fix or 'Implement appropriate resolution'}"
        )

        approved_actions = list(request.approved_actions)
        if auto_approve_dev_write and "write_file" not in approved_actions:
            approved_actions.append("write_file")

        dev_request = AgentRequest(
            query=dev_query,
            context=request.context,
            code=request.code,
            files=request.files,
            approved_actions=approved_actions,
        )

        developer = self.router.get_agent("developer_agent")
        dev_response = developer.run(dev_request)
        orch_state.record_agent_execution("developer_agent", dev_response)

        generated_code = getattr(dev_response, "generated_code", None) or dev_response.result
        proposed_changes = getattr(dev_response, "proposed_changes", [])

        handoff_to_test = orch_state.create_handoff(
            from_agent="developer_agent",
            to_agent="testing_agent",
            summary=dev_response.explanation or "Applied code modifications to resolve root cause.",
            proposed_code=generated_code,
            evidence=dev_response.evidence,
        )

        # -------------------------------------------------------------------
        # Step 3: Testing Agent
        # -------------------------------------------------------------------
        test_query = (
            f"Write and run unit tests for the code modified by the Developer Agent.\n"
            f"Developer summary: {handoff_to_test.summary}\n"
            f"Original task: {request.query}"
        )

        test_request = AgentRequest(
            query=test_query,
            context=request.context,
            code=generated_code or request.code,
            files=request.files,
            approved_actions=approved_actions,
        )

        tester = self.router.get_agent("testing_agent")
        test_response = tester.run(test_request)
        orch_state.record_agent_execution("testing_agent", test_response)

        # -------------------------------------------------------------------
        # Pipeline Finalization
        # -------------------------------------------------------------------
        if test_response.status == "error" or debug_response.status == "error":
            orch_state.status = "failed"
        elif dev_response.status == "needs_input":
            orch_state.status = "needs_approval"
        else:
            orch_state.status = "completed"

        dbg_st = getattr(debug_response.status, "value", str(debug_response.status))
        dev_st = getattr(dev_response.status, "value", str(dev_response.status))
        tst_st = getattr(test_response.status, "value", str(test_response.status))

        orch_state.final_output = (
            f"### Multi-Agent Pipeline Execution Summary\n\n"
            f"1. **Debugging Agent**: {dbg_st} — {debug_response.result[:150] if debug_response.result else 'Diagnosis finished.'}\n"
            f"2. **Developer Agent**: {dev_st} — {dev_response.explanation or 'Code modification attempted.'}\n"
            f"3. **Testing Agent**: {tst_st} — {test_response.result[:150] if test_response.result else 'Testing finished.'}\n"
        )

        logger.info("Finished Debugging -> Developer -> Testing pipeline with status %s", orch_state.status)
        return orch_state
