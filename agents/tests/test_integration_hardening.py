"""
agents/tests/test_integration_hardening.py

Covers the two small, additive changes made when the agent layer was wired
into the Moltress UI/backend:

  1. Portable env names: OLLAMA_BASE_URL / OLLAMA_MODEL (preferred) with the
     original OLLAMA_HOST / MODEL_NAME still honoured.
  2. Read-tool hardening: credential files are never readable by agents and
     recursive tools prune node_modules / .git / virtualenvs.
"""

from __future__ import annotations

from agents.config.agent_config import OllamaConfig, ToolConfig
from agents.tools.code_tools import InspectProjectTool, InspectSourceTool, SearchCodeTool
from agents.tools.file_tools import (
    ListFilesTool,
    ReadFileTool,
    SearchFilesTool,
    is_sensitive_file,
)


# --------------------------------------------------------------------------
# Env aliases
# --------------------------------------------------------------------------

def _clear(monkeypatch):
    for name in ("OLLAMA_BASE_URL", "OLLAMA_HOST", "OLLAMA_MODEL", "MODEL_NAME"):
        monkeypatch.delenv(name, raising=False)


def test_ollama_defaults_are_local_qwen_coder(monkeypatch):
    _clear(monkeypatch)
    cfg = OllamaConfig()
    assert cfg.host == "http://localhost:11434"
    assert cfg.model == "qwen2.5-coder:7b"


def test_preferred_env_names_are_used(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.internal:9999")
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model:1b")
    cfg = OllamaConfig()
    assert cfg.host == "http://ollama.internal:9999"
    assert cfg.model == "custom-model:1b"


def test_legacy_env_names_still_work(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OLLAMA_HOST", "http://legacy:1234")
    monkeypatch.setenv("MODEL_NAME", "legacy-model")
    cfg = OllamaConfig()
    assert cfg.host == "http://legacy:1234"
    assert cfg.model == "legacy-model"


def test_preferred_env_names_win_over_legacy(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OLLAMA_HOST", "http://legacy:1234")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://new:1")
    monkeypatch.setenv("MODEL_NAME", "legacy-model")
    monkeypatch.setenv("OLLAMA_MODEL", "new-model")
    cfg = OllamaConfig()
    assert (cfg.host, cfg.model) == ("http://new:1", "new-model")


def test_blank_preferred_env_falls_back_to_legacy(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OLLAMA_BASE_URL", "   ")
    monkeypatch.setenv("OLLAMA_HOST", "http://legacy:1234")
    assert OllamaConfig().host == "http://legacy:1234"


# --------------------------------------------------------------------------
# Sensitive-file guard
# --------------------------------------------------------------------------

def test_is_sensitive_file_classification():
    for name in (".env", ".env.local", ".env.production", "server.pem", "id_rsa", "private.key", ".npmrc"):
        assert is_sensitive_file(name), name
    for name in (".env.example", ".env.sample", "app.py", "README.md", "environment.py", "keyboard.ts"):
        assert not is_sensitive_file(name), name


def _project(tmp_path):
    (tmp_path / "app.py").write_text("def hello():\n    return 'hi'\n")
    (tmp_path / ".env").write_text("SECRET_TOKEN=hunter2\n")
    (tmp_path / ".env.example").write_text("SECRET_TOKEN=changeme\n")
    nm = tmp_path / "node_modules" / "dep"
    nm.mkdir(parents=True)
    (nm / "index.py").write_text("def hello():\n    return 'vendored'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("def hello():\n    return 'mod'\n")
    return ToolConfig(project_root=str(tmp_path))


def test_read_file_denies_env_but_allows_example(tmp_path):
    cfg = _project(tmp_path)
    denied = ReadFileTool(cfg).run(".env")
    assert denied.success is False
    assert "Access denied" in (denied.error or "")
    assert "hunter2" not in str(denied.__dict__)

    allowed = ReadFileTool(cfg).run(".env.example")
    assert allowed.success is True


def test_inspect_source_denies_secret_files(tmp_path):
    cfg = _project(tmp_path)
    (tmp_path / "creds.key").write_text("-----BEGIN PRIVATE KEY-----")
    res = InspectSourceTool(cfg).run("creds.key")
    assert res.success is False
    assert "Access denied" in (res.error or "")


def test_list_and_search_skip_secrets_and_vendored_dirs(tmp_path):
    cfg = _project(tmp_path)

    listed = ListFilesTool(cfg).run(directory=".", pattern="*", recursive=True).data
    assert "app.py" in listed
    assert ".env" not in listed
    assert not any(p.startswith("node_modules") for p in listed)

    found = SearchFilesTool(cfg).run(query="hunter2", directory=".", file_glob="*").data
    assert found == []

    code = SearchCodeTool(cfg).run(symbol="hello", file_glob="*.py").data
    files = {m["file"].replace("\\", "").replace("/", "") for m in code}
    assert "app.py" in files
    assert "srcmod.py" in files


def test_inspect_project_ignores_vendored_dirs(tmp_path):
    cfg = _project(tmp_path)
    data = InspectProjectTool(cfg).run().data
    assert "node_modules" not in data["top_level_dirs"]
    assert "src" in data["top_level_dirs"]
    # app.py, src/mod.py, .env.example  (.env and node_modules/** excluded)
    assert data["total_files"] == 3
