"""
backend/service.py
==================

``AgentService`` is the one place where the HTTP layer meets the agent
layer. It is deliberately framework-free (no FastAPI imports) so it can be
unit-tested - with ``FakeOllamaClient`` - and reused from other front ends.

Responsibilities
----------------
* Build a validated ``AgentRequest`` from a ``ChatRequest``
  (history -> memory, files, code, logs, per-request sandbox root).
* Route: ``AgentRouter`` (auto / forced agent) or ``AgentOrchestrator``
  (Debugging -> Developer -> Testing pipeline).
* Wire the real verification provider (and RAG/Graph/Memory providers when
  their feature flags are on).
* Convert the structured ``AgentResponse`` into the stable ``ChatResponse``
  contract and pick an accurate HTTP status for every failure mode.
* Report health of the whole chain (backend -> Ollama -> model).

It never raises for expected failures; unexpected exceptions are logged and
returned as a structured 500.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from agents import AgentRouter, __version__ as AGENT_LAYER_VERSION
from agents.config.agent_config import AgentConfig, get_config
from agents.llm.ollama_client import OllamaClient
from agents.orchestrator import AgentOrchestrator
from agents.providers_impl import (
    ASTGraphProvider,
    CodeFactVerificationProvider,
    InMemoryMemoryProvider,
    LocalCodeRAGProvider,
)
from agents.schemas.common import (
    AgentContext,
    AgentRequest,
    AgentResponse,
    MemoryEntry,
    ProjectInfo,
    RoutingDecision,
    SourceFile,
)

from backend import __version__ as BACKEND_VERSION
from backend.formatting import agent_label, render_answer, render_body
from backend.models import (
    ApiError,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    OllamaHealth,
    RoutingInfo,
    ToolCallSummary,
    VerificationInfo,
)
from backend.settings import BackendSettings

logger = logging.getLogger("moltress.backend.service")

#: agent error_type -> HTTP status.
_ERROR_STATUS = {
    "InvalidInput": 422,
    "LLMUnavailable": 503,
    "Timeout": 504,
    "LLMTimeout": 504,
    "MalformedOutput": 502,
    "LLMExecutionError": 502,
}


def _http_status_for(error_type: Optional[str]) -> int:
    return _ERROR_STATUS.get(error_type or "", 500)


class AgentService:
    def __init__(
        self,
        settings: Optional[BackendSettings] = None,
        config: Optional[AgentConfig] = None,
        llm_client: Optional[OllamaClient] = None,
        max_cached_routers: int = 8,
    ):
        self.settings = settings or BackendSettings.from_env()
        base = config or get_config()
        # The backend owns the default sandbox root (BackendSettings.project_root).
        self.config: AgentConfig = dataclasses.replace(
            base, tools=dataclasses.replace(base.tools, project_root=self.settings.project_root)
        )
        # The REAL OllamaClient unless a test injects FakeOllamaClient.
        self.llm_client: OllamaClient = llm_client or OllamaClient(self.config.ollama)

        self._verification = CodeFactVerificationProvider() if self.settings.verification_enabled else None
        self._rag = LocalCodeRAGProvider() if self.config.rag_enabled else None
        self._graph = ASTGraphProvider() if self.config.graph_enabled else None
        self._memory = InMemoryMemoryProvider() if self.config.memory_enabled else None

        self._routers: "OrderedDict[str, AgentRouter]" = OrderedDict()
        self._max_cached_routers = max_cached_routers
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Router construction (one per sandbox root, small LRU cache)
    # ------------------------------------------------------------------

    def _router_for(self, root: str) -> AgentRouter:
        with self._lock:
            router = self._routers.get(root)
            if router is not None:
                self._routers.move_to_end(root)
                return router
            cfg = dataclasses.replace(self.config, tools=dataclasses.replace(self.config.tools, project_root=root))
            router = AgentRouter(
                llm_client=self.llm_client,
                config=cfg,
                rag_provider=self._rag,
                graph_provider=self._graph,
                memory_provider=self._memory,
                verification_provider=self._verification,
            )
            self._routers[root] = router
            while len(self._routers) > self._max_cached_routers:
                self._routers.popitem(last=False)
            return router

    def _resolve_root(self, requested: Optional[str]) -> Tuple[str, List[str]]:
        default = self.settings.project_root
        if not requested or not requested.strip():
            return default, []
        if not self.settings.allow_context_folder:
            return default, ["The requested context folder was ignored (MOLTRESS_ALLOW_CONTEXT_FOLDER is off)."]
        path = Path(requested).expanduser()
        if path.is_dir():
            return str(path.resolve()), []
        return default, [f"Context folder '{requested}' was not found; the default project root was used instead."]

    # ------------------------------------------------------------------
    # Request building
    # ------------------------------------------------------------------

    def build_agent_request(self, req: ChatRequest, root: str) -> AgentRequest:
        s = self.settings
        turns = [m for m in req.history if m.role in {"user", "assistant"} and m.content.strip()]
        # The UI may already include the message being sent as the last turn.
        if turns and turns[-1].role == "user" and turns[-1].content.strip() == req.query:
            turns = turns[:-1]
        turns = turns[-s.history_max_messages:] if s.history_max_messages else []
        memory = [MemoryEntry(role=m.role, content=m.content.strip()[: s.history_max_chars]) for m in turns]

        return AgentRequest(
            request_id=req.request_id or str(uuid.uuid4()),
            query=req.query,
            context=AgentContext(
                project_info=ProjectInfo(name=Path(root).name or None, root_path=root),
                error_logs=req.error_logs,
                memory=memory,
            ),
            code=req.code,
            files=[SourceFile(path=f.path, content=f.content, language=f.language) for f in req.files],
            # Deliberately never populated from the network: destructive tools
            # (write_file) need an operator-controlled opt-in, not a UI flag.
            approved_actions=[],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, req: ChatRequest) -> Tuple[int, ChatResponse]:
        """Run one request through the agent layer. Returns (http_status, body)."""
        request_id = req.request_id or str(uuid.uuid4())
        req = req.model_copy(update={"request_id": request_id})
        root, notes = self._resolve_root(req.context_folder)
        if req.ignored_attachments:
            notes.append(
                "Attachments not forwarded to the local code agents (only text files are supported): "
                + ", ".join(req.ignored_attachments)
            )
        try:
            agent_request = self.build_agent_request(req, root)
            router = self._router_for(root)

            if req.mode == "pipeline":
                return self._run_pipeline(req, agent_request, router, notes)

            if req.agent:
                try:
                    agent = router.get_agent(req.agent)
                except ValueError as exc:
                    return 400, self._error_body(request_id, "InvalidInput", str(exc), recoverable=True)
                decision = RoutingDecision(
                    agent_name=req.agent,
                    reason="Agent selected explicitly by the caller.",
                    confidence=1.0,
                    matched_rule="explicit",
                )
                response = agent.run(agent_request)
                response.metadata["routing_decision"] = decision.model_dump()
            else:
                response = router.route_and_run(agent_request)

            return self._finish(response, req, notes)
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the UI
            logger.exception("Unhandled error while serving request %s", request_id)
            return 500, self._error_body(
                request_id, "InternalError", f"Unexpected backend error: {type(exc).__name__}: {exc}", recoverable=False
            )

    def health(self) -> HealthResponse:
        oc = self.config.ollama
        problems: List[str] = []
        reachable = False
        models: List[str] = []
        model_available: Optional[bool] = None
        err: Optional[str] = None
        try:
            reachable = bool(self.llm_client.is_available())
            if reachable:
                try:
                    models = list(self.llm_client.list_models())
                    model_available = oc.model in models or f"{oc.model}:latest" in models
                except Exception as exc:  # noqa: BLE001 - tags listing is best-effort
                    err = str(exc)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)

        if not reachable:
            problems.append(f"Ollama is not reachable at {oc.host}. Start it with `ollama serve`.")
        elif model_available is False:
            problems.append(f"Model '{oc.model}' is not pulled in Ollama. Run `ollama pull {oc.model}`.")

        root = Path(self.settings.project_root)
        root_exists = root.is_dir()
        if not root_exists:
            problems.append(f"Project root '{root}' does not exist (MOLTRESS_PROJECT_ROOT).")

        return HealthResponse(
            status="ok" if not problems else "degraded",
            backend_version=BACKEND_VERSION,
            agent_layer_version=AGENT_LAYER_VERSION,
            ollama=OllamaHealth(
                reachable=reachable,
                base_url=oc.host,
                model=oc.model,
                model_available=model_available,
                models=models,
                error=err,
            ),
            project_root=str(root),
            project_root_exists=root_exists,
            agents=self._router_for(self.settings.project_root)._enabled_agent_names(),
            verification_enabled=self._verification is not None,
            problems=problems,
        )

    def agents_info(self) -> List[dict]:
        router = self._router_for(self.settings.project_root)
        out = []
        for name in router._enabled_agent_names():
            agent = router.get_agent(name)
            out.append({"name": name, "label": agent_label(name), "tools": sorted(agent._tools.keys())})
        return out

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _error_body(
        self, request_id: str, error_type: str, message: str, recoverable: bool, agent: Optional[str] = None
    ) -> ChatResponse:
        return ChatResponse(
            ok=False,
            request_id=request_id,
            agent=agent,
            status="error",
            error=ApiError(
                type=error_type,
                message=message,
                recoverable=recoverable,
                details={"ollama_base_url": self.config.ollama.host, "model": self.config.ollama.model},
            ),
            model=self.config.ollama.model,
        )

    def _enrich_error_message(self, error_type: str, message: str) -> str:
        if error_type == "LLMUnavailable" and "(404)" in message:
            return f"{message} The model may not be pulled - run `ollama pull {self.config.ollama.model}`."
        if error_type == "MalformedOutput":
            # Pydantic's raw dump (with doc URLs) is noise for end users.
            kept = [ln for ln in message.splitlines() if "errors.pydantic.dev" not in ln and ln.strip()]
            detail = "\n".join(kept)
            return (
                f"{detail}\n\nThe local model returned a reply the agent could not use. "
                "Retrying often helps; a larger or better instruction-following model improves reliability."
            )
        return message

    def _finish(self, response: AgentResponse, req: ChatRequest, notes: List[str]) -> Tuple[int, ChatResponse]:
        status = str(getattr(response.status, "value", response.status))
        meta = response.metadata or {}
        routing = meta.get("routing_decision")
        verification = meta.get("verification")

        body = ChatResponse(
            ok=status != "error",
            request_id=response.request_id,
            agent=response.agent_name,
            status=status,  # type: ignore[arg-type]
            confidence=str(getattr(response.confidence, "value", response.confidence)),
            confidence_score=response.confidence_score,
            routing=RoutingInfo(**routing) if routing else None,
            verification=VerificationInfo(**verification) if isinstance(verification, dict) else None,
            tools_used=[
                ToolCallSummary(tool_name=t.tool_name, success=t.success, denied=t.denied, summary=t.summary)
                for t in response.tools_used
            ],
            warnings=[*notes, *response.warnings],
            assumptions=list(response.assumptions),
            execution_time_ms=response.execution_time_ms,
            model=self.config.ollama.model,
            raw=response.model_dump(mode="json") if req.include_raw else None,
        )

        if status == "error":
            err = response.error
            etype = err.error_type if err else "AgentError"
            body.error = ApiError(
                type=etype,
                message=self._enrich_error_message(etype, err.message if err else "The agent reported an error."),
                recoverable=err.recoverable if err else True,
                details={
                    **(err.details if err else {}),
                    "ollama_base_url": self.config.ollama.host,
                    "model": self.config.ollama.model,
                },
            )
            return _http_status_for(etype), body

        body.answer = render_answer(response)
        return 200, body

    def _run_pipeline(
        self, req: ChatRequest, agent_request: AgentRequest, router: AgentRouter, notes: List[str]
    ) -> Tuple[int, ChatResponse]:
        orchestrator = AgentOrchestrator(
            llm_client=self.llm_client,
            config=router.config,
            router=router,
            rag_provider=self._rag,
            graph_provider=self._graph,
            memory_provider=self._memory,
            verification_provider=self._verification,
        )
        state = orchestrator.run_debug_fix_test_pipeline(agent_request, auto_approve_dev_write=False)
        request_id = agent_request.request_id

        pipeline = {
            "pipeline_id": state.pipeline_id,
            "status": state.status,
            "steps": list(state.pipeline_steps),
            "handoffs": [{"from": h.from_agent, "to": h.to_agent, "summary": h.summary} for h in state.handoffs],
        }
        failed = next(
            (r for r in state.agent_responses.values() if str(getattr(r.status, "value", r.status)) == "error"),
            None,
        )
        tools = [
            ToolCallSummary(tool_name=t.tool_name, success=t.success, denied=t.denied, summary=t.summary)
            for t in state.cumulative_tools_used
        ]

        if state.status == "failed":
            err = failed.error if failed and failed.error else None
            etype = err.error_type if err else "PipelineFailed"
            body = self._error_body(
                request_id,
                etype,
                self._enrich_error_message(etype, err.message if err else "The multi-agent pipeline failed."),
                recoverable=err.recoverable if err else True,
                agent="orchestrator",
            )
            body.pipeline, body.tools_used, body.warnings = pipeline, tools, notes
            return _http_status_for(etype), body

        sections = [state.final_output or "### Multi-Agent Pipeline Execution Summary"]
        for i, name in enumerate(state.pipeline_steps, start=1):
            resp = state.agent_responses[name]
            content = render_body(resp) or "_No content._"
            sections.append(f"### {i}. {agent_label(name)}\n\n{content}")
        footer = f"*{agent_label('orchestrator')} · {' → '.join(agent_label(s) for s in state.pipeline_steps)}*"

        body = ChatResponse(
            ok=True,
            request_id=request_id,
            agent="orchestrator",
            status="needs_input" if state.status == "needs_approval" else "success",
            answer="\n\n".join(sections) + "\n\n" + footer,
            tools_used=tools,
            warnings=[*notes, *state.cumulative_warnings],
            model=self.config.ollama.model,
            pipeline=pipeline,
            raw=state.model_dump(mode="json") if req.include_raw else None,
        )
        return 200, body
