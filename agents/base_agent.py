"""
agents/base_agent.py
======================

BaseAgent: the shared architecture underlying all five Moltress agents.

    Agent = Role + System Instructions + Tools + Context + Workflow + Structured Output

BaseAgent implements everything that is common across agents, including a
genuine, controlled tool-use loop:

    User Request
        |
    Context Retrieval (RAG / Knowledge Graph / Memory, if configured)
        |
    LLM turn
        |
    Does the model request a tool?
        |-- NO  -> validate as final structured response -> Verification -> done
        |-- YES -> check permission -> check approval (if destructive)
                    -> execute with a timeout -> feed real result back -> loop

BaseAgent implements everything that is common across agents:
  - LLM communication (via the shared OllamaClient)
  - System prompt handling (+ the shared tool-use protocol, appended only
    when the agent actually has tools registered)
  - Building the initial user-facing prompt from an AgentRequest (code,
    files, logs, RAG/graph/memory context)
  - Context enrichment via optional RAGProvider/GraphProvider/MemoryProvider
    (no-ops by default; see agents/providers.py)
  - Tool registration WITH PERMISSION ENFORCEMENT (`allowed_tool_names`)
  - A bounded, iterative tool-use loop with:
      * a maximum number of iterations (agents.config.OrchestrationConfig)
      * a maximum number of consecutive tool failures before stopping
      * a per-call wall-clock timeout independent of any tool-internal timeout
      * duplicate-call detection
      * explicit approval gating for tools marked `requires_approval=True`
  - Explicit, structured task-state tracking (agents.state.AgentTaskState)
    rather than relying on conversation text alone
  - Structured output parsing/validation (into a Pydantic AgentResponse
    subclass)
  - An optional VerificationProvider hook run on every completed response
    (no-op by default; see agents/providers.py)
  - Error handling (LLM unavailable, timeout, malformed output, tool
    failure, invalid input) -> always returns a structured AgentResponse,
    never raises to the caller for expected failure modes
  - Logging (metadata only; payload redaction by default)
  - Configuration (via agents.config)

Specialized agents subclass BaseAgent and provide:
  - `agent_name`
  - `system_prompt`
  - `response_model` (a subclass of AgentResponse)
  - `allowed_tool_names` (the tool permission list for this agent)
  - `default_tools()` (the concrete tool instances, constrained to the
    same set named in `allowed_tool_names`)

Public interface (used by the main Moltress application) is unchanged
from v1:

    agent = DeveloperAgent()
    response = agent.run(request)   # request: AgentRequest, response: AgentResponse subclass
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar, Dict, List, Optional, Type

from pydantic import ValidationError

from agents.config.agent_config import AgentConfig, get_config
from agents.executor import AgentExecutionLoop, LoopLLMError
from agents.llm.ollama_client import OllamaClient, get_llm_client
from agents.prompts.tool_protocol import TOOL_USE_PROTOCOL
from agents.providers import (
    GraphProvider,
    MemoryProvider,
    NullGraphProvider,
    NullMemoryProvider,
    NullRAGProvider,
    NullVerificationProvider,
    RAGProvider,
    VerificationProvider,
)
from agents.schemas.common import (
    AgentError,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ConfidenceLevel,
    ToolInvocationRecord,
)
from agents.state import AgentTaskState
from agents.tools.base_tool import BaseTool

logger = logging.getLogger("moltress.agents")


class BaseAgent:
    """
    Shared base class for all Moltress specialized agents.

    Subclasses MUST set:
        agent_name: str
        system_prompt: str
        response_model: Type[AgentResponse]

    Subclasses SHOULD set:
        allowed_tool_names: Optional[List[str]]  (the tool permission list;
            None means "no restriction beyond whatever default_tools()
            returns", but every shipped agent sets this explicitly)

    Subclasses MAY override:
        default_tools() -> List[BaseTool]
        build_user_prompt(request) -> str          (default provided, usually sufficient)
        postprocess(response, request) -> AgentResponse   (agent-specific tweaks)
    """

    agent_name: str = "base_agent"
    system_prompt: str = "You are a helpful assistant."
    response_model: Type[AgentResponse] = AgentResponse

    # Tool permission list for this agent. None = unrestricted (not used by
    # any of the five shipped agents — they all declare an explicit list).
    allowed_tool_names: ClassVar[Optional[List[str]]] = None

    def __init__(
        self,
        llm_client: Optional[OllamaClient] = None,
        config: Optional[AgentConfig] = None,
        tools: Optional[List[BaseTool]] = None,
        rag_provider: Optional[RAGProvider] = None,
        graph_provider: Optional[GraphProvider] = None,
        memory_provider: Optional[MemoryProvider] = None,
        verification_provider: Optional[VerificationProvider] = None,
    ):
        self.config = config or get_config()
        self.llm_client = llm_client or get_llm_client()

        # Integration-point providers. All default to no-op implementations
        # so the agent runs standalone until the real RAG/Graph/Memory/
        # Verification modules are wired in by another Moltress team.
        self.rag_provider = rag_provider or NullRAGProvider()
        self.graph_provider = graph_provider or NullGraphProvider()
        self.memory_provider = memory_provider or NullMemoryProvider()
        self.verification_provider = verification_provider or NullVerificationProvider()

        self._tools: Dict[str, BaseTool] = {}
        for tool in (tools if tools is not None else self.default_tools()):
            self.register_tool(tool)

    # -- Extension points for subclasses -------------------------------

    def default_tools(self) -> List[BaseTool]:
        """Override in subclasses to provide the agent's default tool set."""
        return []

    def build_user_prompt(self, request: AgentRequest) -> str:
        """
        Build the INITIAL user-turn prompt text from a structured
        AgentRequest. Subsequent turns (tool results) are appended
        separately by the tool-use loop in `run()`.
        """
        sections: List[str] = []

        sections.append(f"## User Query\n{request.query}")

        if request.context.project_info:
            pi = request.context.project_info
            sections.append(
                "## Project Info\n"
                f"- name: {pi.name}\n- language: {pi.language}\n"
                f"- framework: {pi.framework}\n- description: {pi.description}"
            )

        source_files = request.merged_source_files()
        if source_files:
            file_blocks = "\n\n".join(
                f"### File: {f.path}\n```{f.language or ''}\n{f.content}\n```" for f in source_files
            )
            sections.append(f"## Supplied Source Files (user-provided context)\n{file_blocks}")

        if request.code:
            sections.append(f"## Primary Code Snippet (user-provided context)\n```\n{request.code}\n```")

        if request.context.error_logs:
            sections.append(f"## Error Logs / Stack Trace (user-provided context)\n```\n{request.context.error_logs}\n```")

        if request.context.retrieved_documents:
            docs = "\n\n".join(
                f"[{d.source}] (score={d.score}):\n{d.content}" for d in request.context.retrieved_documents
            )
            sections.append(f"## Retrieved Context (RAG — retrieved by the system, not user-authored)\n{docs}")

        if request.context.graph_context:
            rels = "\n".join(
                f"- {r.subject} --{r.relation}--> {r.target}" for r in request.context.graph_context
            )
            sections.append(f"## Knowledge Graph Context (retrieved by the system)\n{rels}")

        if request.context.memory:
            mem = "\n".join(f"[{m.role}] {m.content}" for m in request.context.memory)
            sections.append(f"## Memory / Prior Context (retrieved by the system)\n{mem}")

        if self._tools:
            tool_desc = "\n".join(f"- {t.name}: {t.description}" for t in self._tools.values())
            sections.append(f"## Available Tools\n{tool_desc}")
            sections.append(
                "## Required Output Format\n"
                "Follow the TOOL USE PROTOCOL above: either request one tool call, or, once you "
                "have enough evidence, respond with a SINGLE JSON object (no markdown fences, no "
                f"prose outside the JSON) matching this schema: {self._schema_hint()}"
            )
        else:
            sections.append(
                "## Required Output Format\n"
                "Respond with a SINGLE JSON object only (no markdown fences, no prose outside the JSON) "
                f"matching this schema: {self._schema_hint()}"
            )

        return "\n\n".join(sections)

    def postprocess(self, response: AgentResponse, request: AgentRequest) -> AgentResponse:
        """Hook for agent-specific post-processing of the validated response. No-op by default."""
        return response

    # -- Tool registration & permissions ---------------------------------

    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a tool, enforcing this agent's permission list
        (`allowed_tool_names`) and any process-wide `enabled_tools`
        allow-list from configuration. Tools that fail either check are
        silently NOT registered (logged at WARNING) rather than raising,
        so a misconfiguration fails safe (tool simply unavailable) rather
        than crashing agent construction.
        """
        if self.allowed_tool_names is not None and tool.name not in self.allowed_tool_names:
            logger.warning(
                "[%s] Refusing to register tool '%s': not in this agent's allowed_tool_names %s",
                self.agent_name, tool.name, self.allowed_tool_names,
            )
            return
        if self.config.enabled_tools is not None and tool.name not in self.config.enabled_tools:
            logger.warning(
                "[%s] Refusing to register tool '%s': not in process-wide ENABLED_TOOLS %s",
                self.agent_name, tool.name, self.config.enabled_tools,
            )
            return
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def invoke_tool(self, name: str, **kwargs) -> ToolInvocationRecord:
        """
        Directly invoke a registered tool by name (bypassing the LLM loop)
        and return an auditable record. Kept for callers/tests that want
        to exercise a single tool call without a full agent.run() cycle.
        Does NOT enforce approval gating — callers using this directly are
        assumed to already be an authorized caller (e.g. a test, or the
        main Moltress backend acting on a human-approved action).
        """
        tool = self.get_tool(name)
        if tool is None:
            return ToolInvocationRecord(tool_name=name, arguments=kwargs, success=False, summary="Tool not registered")
        result = tool.safe_run(**kwargs)
        return ToolInvocationRecord(
            tool_name=name,
            arguments=kwargs,
            success=result.success,
            summary=result.summary or result.error,
        )

    # -- Core public interface -------------------------------------------

    def run(self, request: AgentRequest) -> AgentResponse:
        """
        Execute the agent against a request. This is the ONLY method the
        main Moltress application needs to call. It never raises for
        expected failure modes (LLM unavailable, timeout, malformed
        output, invalid input, tool failure) — those are converted into a
        structured AgentResponse (status=ERROR/PARTIAL/NEEDS_INPUT).

        The actual DECISION -> TOOL -> OBSERVATION -> DECISION loop is
        delegated to `AgentExecutionLoop` (agents/executor.py) — a
        reusable component decoupled from BaseAgent. This method's job is
        everything AROUND that loop: prompt construction, context
        retrieval, response validation, and verification.
        """
        start = time.monotonic()
        request_id = request.request_id

        try:
            self._validate_request(request)
        except ValueError as exc:
            return self._error_response(request_id, "InvalidInput", str(exc), recoverable=True, start=start)

        if not self.llm_client.is_available():
            return self._error_response(
                request_id,
                "LLMUnavailable",
                f"Local LLM (Ollama) is not reachable at {self.config.ollama.host}. "
                "Ensure the Ollama server is running and the configured model is pulled.",
                recoverable=True,
                start=start,
            )

        # Context Retrieval: RAG / Knowledge Graph / Memory (no-ops unless
        # both the relevant config flag AND a real provider are supplied).
        self._enrich_context(request)

        self._log_invocation(request)

        loop = AgentExecutionLoop(
            llm_client=self.llm_client, tools=self._tools, config=self.config, agent_name=self.agent_name,
        )
        try:
            state = loop.execute(
                request,
                system_prompt=self._effective_system_prompt(),
                initial_user_prompt=self.build_user_prompt(request),
            )
        except LoopLLMError as exc:
            return self._error_response(request_id, exc.error_type, exc.message, recoverable=True, start=start)

        if state.final_result is not None:
            response = self._parse_response(state.final_result, request_id, start)
            if response.status == AgentStatus.ERROR:
                return response
        else:
            response = self._build_stopped_response(state, request_id, start)

        response = self.postprocess(response, request)
        response.tools_used = list(state.tools_used)
        if state.assumptions:
            response.assumptions = list(dict.fromkeys([*response.assumptions, *state.assumptions]))
        response.metadata["task_state"] = state.to_metadata()
        response.metadata["execution_trace"] = state.render_trace(agent_name=self.agent_name)

        self._verify(response, request)

        response.execution_time_ms = (time.monotonic() - start) * 1000
        self._log_completion(request, response)
        return response

    # -- Context enrichment (RAG / Graph / Memory) ------------------------

    def _enrich_context(self, request: AgentRequest) -> None:
        """
        Populate request.context from the configured providers when the
        caller hasn't already supplied that context directly and the
        corresponding feature flag is enabled. No-op providers make this
        a cheap no-op by default; real providers plug in here without any
        change to agent logic.
        """
        cfg = self.config
        ctx = request.context

        if cfg.rag_enabled and not ctx.retrieved_documents:
            try:
                docs = self.rag_provider.retrieve(request.query, project_root=cfg.tools.project_root)
                if docs:
                    ctx.retrieved_documents = docs
            except Exception as exc:  # noqa: BLE001 - provider failures must never break the agent
                logger.warning("[%s] RAG retrieval failed: %s", self.agent_name, exc)

        if cfg.graph_enabled and not ctx.graph_context:
            try:
                rels = self.graph_provider.get_relationships(request.query)
                if rels:
                    ctx.graph_context = rels
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] Knowledge Graph retrieval failed: %s", self.agent_name, exc)

        if cfg.memory_enabled and not ctx.memory:
            try:
                session_id = ctx.extra.get("session_id", request.request_id)
                mem = self.memory_provider.get_recent(session_id)
                if mem:
                    ctx.memory = mem
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] Memory retrieval failed: %s", self.agent_name, exc)

    # -- Verification ------------------------------------------------------

    def _verify(self, response: AgentResponse, request: AgentRequest) -> None:
        """
        Run the configured VerificationProvider over the draft response.
        Never raises — a failing/unavailable verification layer degrades
        to an "unverified" note rather than breaking the agent's response.
        """
        try:
            result = self.verification_provider.verify(response, request.context)
            response.metadata["verification"] = {"verified": result.verified, "notes": result.notes}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] Verification provider raised an error: %s", self.agent_name, exc)
            response.metadata["verification"] = {"verified": False, "notes": f"Verification layer error: {exc}"}

    # -- Internal helpers --------------------------------------------------

    def _effective_system_prompt(self) -> str:
        """The specialized prompt, plus the shared tool-use protocol when tools exist."""
        if self._tools:
            return f"{self.system_prompt}\n\n{TOOL_USE_PROTOCOL}"
        return self.system_prompt

    def _validate_request(self, request: AgentRequest) -> None:
        if not isinstance(request, AgentRequest):
            raise ValueError("request must be an instance of AgentRequest")
        if not request.query or not request.query.strip():
            raise ValueError("request.query must be a non-empty string")

    def _schema_hint(self) -> str:
        """Human/LLM-readable summary of required top-level JSON fields."""
        fields = self.response_model.model_fields
        # Keep this compact — full pydantic schema is often too verbose for
        # small local models to reliably follow.
        names = [name for name in fields.keys() if name not in {"agent_name", "request_id"}]
        return "{" + ", ".join(f'"{n}": ...' for n in names) + "}"

    def _normalize_raw_response(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerce common real-LLM output deviations so downstream Pydantic
        validation succeeds instead of raising MalformedOutput.
        """
        # 1. Status normalization - real model uses non-standard strings like "request_tool_call"
        _valid_statuses = {"success", "partial", "needs_input", "error"}
        status = str(raw.get("status", "success")).lower()
        if status not in _valid_statuses:
            raw["status"] = "success"

        # 2. confidence_score & confidence enum normalization
        _valid_confidences = {"high", "medium", "low", "unknown"}
        conf = str(raw.get("confidence") or "unknown").lower()
        if conf not in _valid_confidences:
            conf = "unknown"
        raw["confidence"] = conf

        cs = raw.get("confidence_score")
        if isinstance(cs, (int, float)) and cs > 1:
            raw["confidence_score"] = round(cs / 100.0, 2)

        # 3. List fields that are None → replace with []
        _list_fields = [
            "evidence", "assumptions", "warnings", "tools_used", "proposed_changes",
            "design_notes", "generated_tests", "candidate_causes", "identified_edge_cases",
            "follow_up_suggestions", "steps", "findings",
        ]
        for fld in _list_fields:
            if raw.get(fld) is None:
                raw[fld] = []

        # 4. evidence: plain string → single Evidence dict
        if isinstance(raw.get("evidence"), str):
            raw["evidence"] = [{"source": "model_output", "reason": raw["evidence"]}]

        # 5. evidence: list items that are plain strings → Evidence dicts
        if isinstance(raw.get("evidence"), list):
            raw["evidence"] = [
                item if isinstance(item, dict) else {"source": "model_output", "reason": str(item)}
                for item in raw["evidence"]
            ]

        # 6. tools_used: entries that are plain strings → ToolInvocationRecord dicts
        if isinstance(raw.get("tools_used"), list):
            raw["tools_used"] = [
                item if isinstance(item, dict) else {"tool_name": str(item), "success": True, "arguments": {}}
                for item in raw["tools_used"]
            ]

        # 7. candidate_causes: normalize strings and dicts to valid SuspectedCause objects
        if isinstance(raw.get("candidate_causes"), list):
            norm_causes = []
            for cause in raw["candidate_causes"]:
                if isinstance(cause, str):
                    norm_causes.append({"description": cause, "likelihood": 0.5, "supporting_evidence": []})
                elif isinstance(cause, dict):
                    desc = cause.get("description") or cause.get("cause") or cause.get("title") or "Unspecified cause"
                    lh = cause.get("likelihood")
                    if isinstance(lh, (int, float)):
                        lh_val = float(lh / 100.0) if lh > 1 else float(lh)
                    elif isinstance(lh, str):
                        lh_map = {"high": 0.8, "medium": 0.5, "low": 0.2, "possible": 0.5}
                        lh_val = lh_map.get(lh.lower(), 0.5)
                    else:
                        lh_val = 0.5

                    ev = cause.get("supporting_evidence")
                    if isinstance(ev, str):
                        ev_list = [ev]
                    elif isinstance(ev, list):
                        ev_list = [str(x) for x in ev]
                    else:
                        ev_list = []

                    norm_causes.append({
                        "description": str(desc),
                        "likelihood": max(0.0, min(1.0, lh_val)),
                        "supporting_evidence": ev_list,
                        "ruled_out": bool(cause.get("ruled_out", False)),
                        "ruled_out_reason": cause.get("ruled_out_reason"),
                    })
            raw["candidate_causes"] = norm_causes

        # 8. suggested_fixes: ensure change_summary field is present
        if isinstance(raw.get("suggested_fixes"), list):
            norm_fixes = []
            for fix in raw["suggested_fixes"]:
                if isinstance(fix, str):
                    norm_fixes.append({"change_summary": fix})
                elif isinstance(fix, dict):
                    cs = (
                        fix.get("change_summary") or
                        fix.get("summary") or
                        fix.get("description") or
                        fix.get("fix") or
                        fix.get("title") or
                        fix.get("diff_or_content") or
                        "Proposed code fix"
                    )
                    norm_fixes.append({
                        "file_path": fix.get("file_path"),
                        "change_summary": str(cs),
                        "diff_or_content": fix.get("diff_or_content"),
                        "risk": fix.get("risk"),
                    })
            raw["suggested_fixes"] = norm_fixes

        # 9. assumptions: plain string → [string]; list of non-strings → stringified
        if isinstance(raw.get("assumptions"), str):
            raw["assumptions"] = [raw["assumptions"]]
        elif isinstance(raw.get("assumptions"), list):
            raw["assumptions"] = [
                item if isinstance(item, str) else str(item)
                for item in raw["assumptions"]
            ]

        # 10. metadata: if None or not a dict → {}
        if not isinstance(raw.get("metadata"), dict):
            raw["metadata"] = {}

        # 11. error field: if model outputs string instead of AgentError dict
        err_val = raw.get("error")
        if isinstance(err_val, str):
            if raw.get("status") == "error":
                raw["error"] = {"error_type": "LLMExecutionError", "message": err_val}
            else:
                if not raw.get("error_summary"):
                    raw["error_summary"] = err_val
                raw["error"] = None

        return raw

    def _parse_response(self, raw: Dict[str, Any], request_id: str, start: float) -> AgentResponse:
        raw = dict(raw)  # avoid mutating caller data
        raw.setdefault("agent_name", self.agent_name)
        raw["request_id"] = request_id
        raw.setdefault("status", AgentStatus.SUCCESS.value)
        raw.setdefault("confidence", ConfidenceLevel.UNKNOWN.value)

        # Coerce common real-LLM schema deviations before strict Pydantic validation
        raw = self._normalize_raw_response(raw)

        try:
            return self.response_model.model_validate(raw)
        except ValidationError as exc:
            logger.error("Response validation failed for %s: %s", self.agent_name, exc)
            return self._error_response(
                request_id,
                "MalformedOutput",
                f"Model output did not match the expected schema: {exc}",
                recoverable=True,
                start=start,
            )

    def _build_stopped_response(self, state: AgentTaskState, request_id: str, start: float) -> AgentResponse:
        """
        Construct a best-effort, structured response when the tool-use
        loop stopped WITHOUT the model producing a final answer (max
        iterations reached, repeated tool failures, or repeated approval
        denials). Per the "no fake autonomy" / "stop conditions"
        requirements, this must clearly explain what was determined and
        what prevented completion — never silently return an empty or
        misleading result.
        """
        steps_summary = "; ".join(state.steps[-5:]) if state.steps else "No steps were recorded."
        findings_summary = "; ".join(state.findings[-5:]) if state.findings else "No findings were gathered."

        if state.status == "stopped_needs_approval":
            status = AgentStatus.NEEDS_INPUT
            explanation = (
                f"Stopped because the action(s) needed to proceed require explicit user approval "
                f"that this request did not grant. Steps taken: {steps_summary} "
                f"Findings so far: {findings_summary}"
            )
            warning = "User approval is required for at least one action before this task can complete."
        elif state.status == "stopped_tool_failures":
            status = AgentStatus.PARTIAL
            explanation = (
                f"Stopped after {state.consecutive_tool_failures()} consecutive tool call failure(s) "
                f"and could not complete the task. Steps taken: {steps_summary} "
                f"Findings so far: {findings_summary}"
            )
            warning = "Repeated tool failures prevented task completion; see tools_used for details."
        else:
            status = AgentStatus.PARTIAL
            explanation = (
                f"Reached the maximum of {state.iteration} tool-use iteration(s) without producing a "
                f"final answer. Steps taken: {steps_summary} Findings so far: {findings_summary}"
            )
            warning = "Maximum tool-iteration limit reached before the task could be completed."

        logger.warning("[%s] %s", self.agent_name, explanation)

        return self.response_model(
            agent_name=self.agent_name,
            request_id=request_id,
            status=status,
            explanation=explanation,
            confidence=ConfidenceLevel.LOW,
            assumptions=list(state.assumptions),
            warnings=[warning],
            tools_used=list(state.tools_used),
            execution_time_ms=(time.monotonic() - start) * 1000,
            metadata={"task_state": state.to_metadata(), "execution_trace": state.render_trace(agent_name=self.agent_name)},
        )

    def _error_response(
        self, request_id: str, error_type: str, message: str, recoverable: bool, start: float
    ) -> AgentResponse:
        logger.error("[%s] %s: %s", self.agent_name, error_type, message)
        return self.response_model(
            agent_name=self.agent_name,
            request_id=request_id,
            status=AgentStatus.ERROR,
            error=AgentError(error_type=error_type, message=message, recoverable=recoverable),
            execution_time_ms=(time.monotonic() - start) * 1000,
        )

    def _log_invocation(self, request: AgentRequest) -> None:
        if self.config.logging.redact_payloads:
            logger.info("[%s] invoked | request_id=%s", self.agent_name, request.request_id)
        else:
            logger.info(
                "[%s] invoked | request_id=%s | query=%s", self.agent_name, request.request_id, request.query
            )

    def _log_completion(self, request: AgentRequest, response: AgentResponse) -> None:
        logger.info(
            "[%s] completed | request_id=%s | status=%s | iterations=%s | tool_calls=%s | duration_ms=%.1f",
            self.agent_name,
            request.request_id,
            response.status,
            response.metadata.get("task_state", {}).get("iterations"),
            len(response.tools_used),
            response.execution_time_ms or 0.0,
        )
