"""
backend/app.py
==============

FastAPI application exposing the agent layer to the desktop UI.

Endpoints
---------
GET  /api/health       Whole-chain health (backend, Ollama, model). Always 200.
GET  /api/agents       Available agents and their tool permissions.
POST /api/agent/chat   Run a request through router/orchestrator -> agent -> Ollama.

Every response body, success or failure, is JSON. Chat failures use the
``ChatResponse`` envelope (``ok: false`` + ``error``) with a meaningful
HTTP status: 401 bad token, 422 invalid input, 502 malformed model output,
503 Ollama unavailable, 504 timeout, 500 anything else.
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import __version__
from backend.models import ApiError, ChatRequest, ChatResponse, HealthResponse
from backend.service import AgentService
from backend.settings import BackendSettings, load_env
from pydantic import BaseModel

logger = logging.getLogger("moltress.backend")

class IngestRequest(BaseModel):
    path: str
    workspace: str = "default"


def create_app(service: Optional[AgentService] = None, settings: Optional[BackendSettings] = None) -> FastAPI:
    """
    Build the app. Tests inject an ``AgentService`` wired to
    ``FakeOllamaClient``; production uses the real ``OllamaClient``.
    """
    if service is None:
        load_env()
        settings = settings or BackendSettings.from_env()
        logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
        service = AgentService(settings=settings)
    settings = service.settings

    # Database Initialization
    from backend.database import Base, engine
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title="Moltress Backend", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.service = service

    origins = list(settings.cors_origins) if settings.cors_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_token(authorization: Optional[str] = Header(default=None)) -> None:
        if not settings.api_token:
            return
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not secrets.compare_digest(supplied, settings.api_token):
            raise HTTPException(status_code=401, detail="Missing or invalid API token.")

    # ---- consistent JSON errors ------------------------------------------

    def _err(status: int, etype: str, message: str, request_id: str = "") -> JSONResponse:
        body = ChatResponse(
            ok=False,
            request_id=request_id,
            status="error",
            error=ApiError(type=etype, message=message, recoverable=status < 500),
        )
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", ()) if p != "body")
            msg = str(e.get("msg", "invalid")).removeprefix("Value error, ")
            parts.append(f"{loc}: {msg}" if loc else msg)
        return _err(422, "InvalidInput", "; ".join(parts) or "Invalid request.")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        etype = "Unauthorized" if exc.status_code == 401 else "HttpError"
        return _err(exc.status_code, etype, str(exc.detail))

    # ---- routes ------------------------------------------------------------

    @app.get("/api/health", response_model=HealthResponse, dependencies=[Depends(require_token)])
    def health() -> HealthResponse:
        return service.health()

    @app.get("/api/agents", dependencies=[Depends(require_token)])
    def agents() -> list:
        return service.agents_info()

    @app.post("/api/rag/ingest", dependencies=[Depends(require_token)])
    def ingest_knowledge(req: IngestRequest) -> JSONResponse:
        import sys
        from pathlib import Path
        import subprocess
        
        try:
            target_path = Path(req.path).expanduser().resolve()
            if not target_path.exists():
                return _err(400, "InvalidPath", f"Path does not exist: {target_path}")
            
            moltress_rag_path = Path(__file__).parent.parent.parent / "Moltress_RAG" if Path(__file__).parent.parent.parent.joinpath("Moltress_RAG").exists() else Path(__file__).parent.parent / "Moltress_RAG"
            
            # Execute exactly identically to CLI workflow
            cmd = [sys.executable, str(moltress_rag_path / "main.py"), "learn", str(target_path), "-w", req.workspace]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(moltress_rag_path))
            
            if result.returncode == 0:
                chunks = 0
                for line in result.stdout.splitlines():
                    if "chunks indexed" in line.lower():
                        try:
                            # Try to extract a total chunk count approximation from the log
                            import re
                            if match := re.search(r'(\d+)', line):
                                chunks += int(match.group(1))
                        except Exception:
                            pass
                return JSONResponse(status_code=200, content={"ok": True, "workspace": req.workspace, "chunks": chunks, "log": result.stdout})
            else:
                return _err(500, "IngestionError", f"Failed to ingest: {result.stderr or result.stdout}")
                
        except Exception as e:
            logger.error("Ingestion subprocess error: %s", str(e))
            return _err(500, "InternalError", str(e))

    @app.get("/api/sessions", dependencies=[Depends(require_token)])
    def get_sessions() -> JSONResponse:
        try:
            from backend.database import SessionLocal
            from backend.db_models import ChatSession, ChatMessage
            from sqlalchemy import func
            with SessionLocal() as db:
                sessions = db.query(
                    ChatSession.id,
                    ChatSession.created_at,
                    func.count(ChatMessage.id).label("message_count")
                ).outerjoin(ChatMessage).group_by(ChatSession.id).order_by(ChatSession.created_at.desc()).all()

                result = [
                    {
                        "sessionId": s.id,
                        "title": f"Moltress Session {s.id[:6]}",
                        "source": "moltress",
                        "startedAt": int(s.created_at.timestamp() * 1000) if s.created_at else 0,
                        "messageCount": s.message_count,
                        "model": "qwen2.5-coder:7b",
                        "preview": "Moltress Desktop conversation"
                    }
                    for s in sessions
                ]
                return JSONResponse(status_code=200, content=result)
        except Exception as e:
            return _err(500, "DatabaseError", str(e))

    @app.get("/api/sessions/{session_id}/messages", dependencies=[Depends(require_token)])
    def get_session_messages(session_id: str) -> JSONResponse:
        try:
            from backend.database import SessionLocal
            from backend.db_models import ChatMessage
            with SessionLocal() as db:
                messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
                result = [
                    {
                        "kind": m.role if m.role in ["user", "assistant"] else "assistant",
                        "id": m.id,
                        "content": m.content,
                        "timestamp": int(m.created_at.timestamp() * 1000) if m.created_at else 0,
                    }
                    for m in messages
                ]
                return JSONResponse(status_code=200, content=result)
        except Exception as e:
            return _err(500, "DatabaseError", str(e))

    @app.post("/api/agent/chat", response_model=ChatResponse, dependencies=[Depends(require_token)])
    def chat(req: ChatRequest) -> JSONResponse:
        # Sync endpoint: FastAPI runs it in a worker thread, so a slow local
        # LLM never blocks health checks or other requests.
        status, body = service.chat(req)
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    return app


def get_app() -> FastAPI:
    """ASGI factory for ``uvicorn backend.app:get_app --factory``."""
    return create_app()
