"""
backend/settings.py
===================

Backend-level configuration, read from environment variables (optionally
loaded from a ``.env`` file at the repository root).

Ollama / model / tool settings are NOT duplicated here: they belong to the
agent layer (``agents.config.agent_config``) and are read from the same
environment (``OLLAMA_BASE_URL``, ``OLLAMA_MODEL`` ...). This module only
holds what is specific to the HTTP service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

#: Repository root (parent of ``backend/``).
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load ``<repo>/.env`` (if present) without overriding real environment variables."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is optional; real env vars still work
        return
    explicit = os.getenv("MOLTRESS_ENV_FILE", "").strip()
    load_dotenv(explicit or REPO_ROOT / ".env", override=False)


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _csv(name: str) -> Tuple[str, ...]:
    return tuple(p.strip() for p in os.getenv(name, "").split(",") if p.strip())


@dataclass(frozen=True)
class BackendSettings:
    host: str = "127.0.0.1"
    port: int = 8765
    #: Optional shared secret. When set, every /api request must send
    #: ``Authorization: Bearer <token>``.
    api_token: str = ""
    #: Browser origins allowed via CORS (the Electron app does not need this).
    cors_origins: Tuple[str, ...] = ()
    #: Default sandbox root for the agents' file tools.
    project_root: str = str(REPO_ROOT)
    #: Let the UI's "context folder" override the sandbox root per request.
    allow_context_folder: bool = True
    history_max_messages: int = 12
    history_max_chars: int = 4000
    #: Wire agents.verification.CodeFactVerificationProvider into every agent.
    verification_enabled: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "BackendSettings":
        root = os.getenv("MOLTRESS_PROJECT_ROOT", "").strip()
        resolved = Path(root).expanduser()
        if root and not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        return cls(
            host=os.getenv("MOLTRESS_BACKEND_HOST", "").strip() or "127.0.0.1",
            port=_int("MOLTRESS_BACKEND_PORT", 8765),
            api_token=os.getenv("MOLTRESS_API_TOKEN", "").strip(),
            cors_origins=_csv("MOLTRESS_CORS_ORIGINS"),
            project_root=str(resolved.resolve()) if root else str(REPO_ROOT),
            allow_context_folder=_bool("MOLTRESS_ALLOW_CONTEXT_FOLDER", True),
            history_max_messages=max(0, _int("MOLTRESS_HISTORY_MAX_MESSAGES", 12)),
            history_max_chars=max(100, _int("MOLTRESS_HISTORY_MAX_CHARS", 4000)),
            verification_enabled=_bool("MOLTRESS_VERIFICATION_ENABLED", True),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        )
