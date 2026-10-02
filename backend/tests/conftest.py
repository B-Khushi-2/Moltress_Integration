"""
Shared fixtures for the backend tests.

All tests here use FakeOllamaClient (from the agent layer's own test
conftest) so they are deterministic and need no Ollama. The *live* path is
exercised separately by scripts/verify_live_ollama.py and the end-to-end run.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agents.config.agent_config import AgentConfig, ToolConfig
from agents.tests.conftest import FakeOllamaClient  # noqa: F401  (re-exported for tests)
from backend.app import create_app
from backend.service import AgentService
from backend.settings import BackendSettings

OK_DEV = {
    "status": "success",
    "result": "This is a desktop chat application that routes requests to local coding agents.",
    "explanation": "Derived from the project structure.",
    "confidence": "high",
    "confidence_score": 0.9,
}


class FakeWithModels(FakeOllamaClient):
    """FakeOllamaClient plus the /api/tags listing used by health checks."""

    def __init__(self, *a, models=("qwen2.5-coder:7b",), **kw):
        super().__init__(*a, **kw)
        self._models = list(models)

    def list_models(self):
        return list(self._models)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / ".env").write_text("API_KEY=super-secret-value\n")
    return tmp_path


@pytest.fixture
def make_client(project):
    """make_client(fake_llm, **settings_overrides) -> (TestClient, AgentService)"""

    def _make(llm, token="", **overrides):
        settings = BackendSettings(project_root=str(project), api_token=token, **overrides)
        cfg = AgentConfig(tools=ToolConfig(project_root=str(project)))
        service = AgentService(settings=settings, config=cfg, llm_client=llm)
        return TestClient(create_app(service=service)), service

    return _make
