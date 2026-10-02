from __future__ import annotations

from agents.tests.conftest import FakeOllamaClient
from backend.tests.conftest import FakeWithModels, OK_DEV

CHAT = "/api/agent/chat"


# ---------------------------------------------------------------- success --

def test_successful_request_returns_real_agent_answer(make_client):
    llm = FakeWithModels(canned_response=OK_DEV)
    client, _ = make_client(llm)
    r = client.post(CHAT, json={"query": "Explain the purpose of this application."})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "success"
    assert body["agent"] == "developer_agent"          # default route (no keyword match)
    assert "desktop chat application" in body["answer"]
    assert body["routing"]["matched_rule"] in {"default", "llm_fallback"}
    assert body["verification"] is not None            # real verifier is wired in
    assert body["model"] == "qwen2.5-coder:7b"
    assert llm.call_count >= 1                         # the (fake) LLM was genuinely invoked


def test_keyword_routing_reaches_specialised_agent(make_client):
    canned = {
        "status": "success",
        "result": "One hardcoded credential found.",
        "findings": [{
            "vulnerability": "Hardcoded credential", "severity": "high", "affected_area": "app.py",
            "explanation": "A password literal is committed.", "recommended_fix": "Move to env.",
            "confidence": 0.9, "cwe_reference": "CWE-798",
        }],
    }
    client, _ = make_client(FakeWithModels(canned_response=canned))
    body = client.post(CHAT, json={"query": "Scan this for security vulnerabilities"}).json()
    assert body["agent"] == "security_agent"
    assert body["routing"]["matched_rule"] == "keyword"
    assert "[HIGH] Hardcoded credential" in body["answer"]
    assert "CWE-798" in body["answer"]


def test_forced_agent_overrides_routing(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    body = client.post(CHAT, json={"query": "hello", "agent": "documentation_agent"}).json()
    assert body["agent"] == "documentation_agent"
    assert body["routing"]["matched_rule"] == "explicit"


def test_unknown_forced_agent_is_400(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    r = client.post(CHAT, json={"query": "hello", "agent": "nope_agent"})
    assert r.status_code == 400
    assert r.json()["error"]["type"] == "InvalidInput"


def test_history_is_forwarded_as_memory_and_current_turn_not_duplicated(make_client):
    llm = FakeWithModels(canned_response=OK_DEV)
    client, _ = make_client(llm)
    client.post(CHAT, json={
        "query": "and what about tests?",
        "history": [
            {"role": "user", "content": "Explain the app"},
            {"role": "agent", "content": "It is a chat app."},       # UI role name
            {"role": "user", "content": "and what about tests?"},    # current turn echoed by UI
        ],
    })
    prompt = llm.call_log[-1]["messages"][0].content
    assert "[user] Explain the app" in prompt
    assert "[assistant] It is a chat app." in prompt
    assert prompt.count("and what about tests?") == 1               # only the User Query section


def test_include_raw_attaches_full_agent_response(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    body = client.post(CHAT, json={"query": "hi", "include_raw": True}).json()
    assert body["raw"]["agent_name"] == "developer_agent"


def test_ignored_attachments_surface_as_warning(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    body = client.post(CHAT, json={"query": "hi", "ignored_attachments": ["photo.png"]}).json()
    assert any("photo.png" in w for w in body["warnings"])


# --------------------------------------------------------------- failures --

def test_empty_query_is_rejected_with_422(make_client):
    llm = FakeWithModels(canned_response=OK_DEV)
    client, _ = make_client(llm)
    for payload in ({"query": ""}, {"query": "   \n "}, {}):
        r = client.post(CHAT, json=payload)
        assert r.status_code == 422, payload
        body = r.json()
        assert body["ok"] is False and body["error"]["type"] == "InvalidInput"
    assert llm.call_count == 0                                      # never reached the model


def test_ollama_unavailable_is_503_with_actionable_message(make_client):
    client, _ = make_client(FakeWithModels(available=False))
    r = client.post(CHAT, json={"query": "hello"})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["type"] == "LLMUnavailable"
    assert "Ollama" in err["message"]
    assert err["details"]["model"] == "qwen2.5-coder:7b"


def test_agent_schema_validation_failure_is_502(make_client):
    bad = {"status": "success", "result": "x", "findings": "this should be a list"}
    client, _ = make_client(FakeWithModels(canned_response=bad))
    r = client.post(CHAT, json={"query": "Scan for security vulnerabilities"})
    assert r.status_code == 502
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["type"] == "MalformedOutput"
    assert "errors.pydantic.dev" not in body["error"]["message"]      # no raw library noise
    assert "Retrying often helps" in body["error"]["message"]


def test_unexpected_exception_is_500_not_a_traceback(make_client):
    client, service = make_client(FakeWithModels(canned_response=OK_DEV))
    service.build_agent_request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    r = client.post(CHAT, json={"query": "hello"})
    assert r.status_code == 500
    assert r.json()["error"]["type"] == "InternalError"
    assert "Traceback" not in r.text


# ------------------------------------------------------------------ tools --

def test_agent_cannot_read_env_secrets_through_the_tool_loop(make_client):
    llm = FakeWithModels(canned_responses=[
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": ".env"}, "reasoning": "look"},
        {"status": "partial", "result": "Could not read the file."},
    ])
    client, _ = make_client(llm)
    body = client.post(CHAT, json={"query": "implement a function that reads config", "include_raw": True}).json()
    assert "super-secret-value" not in str(llm.call_log)            # never reached the model
    assert "super-secret-value" not in client.post(CHAT, json={"query": "x"}).text
    read = [t for t in body["tools_used"] if t["tool_name"] == "read_file"]
    assert read and read[0]["success"] is False


def test_agent_reads_real_project_files_via_tool_loop(make_client):
    llm = FakeWithModels(canned_responses=[
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "look"},
        OK_DEV,
    ])
    client, _ = make_client(llm)
    body = client.post(CHAT, json={"query": "explain app.py", "agent": "developer_agent"}).json()
    assert body["status"] == "success"
    assert body["tools_used"][0]["tool_name"] == "read_file" and body["tools_used"][0]["success"]
    # the REAL file contents were fed back to the model on the next turn
    assert "def add(a, b)" in str(llm.call_log[-1]["messages"])


# ---------------------------------------------------------- context folder --

def test_context_folder_changes_sandbox_root(make_client, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    (other / "special.py").write_text("MARKER = 1\n")
    llm = FakeWithModels(canned_responses=[
        {"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "special.py"}, "reasoning": "r"},
        OK_DEV,
    ])
    client, _ = make_client(llm)
    body = client.post(CHAT, json={"query": "explain special.py", "agent": "developer_agent", "context_folder": str(other)}).json()
    assert body["tools_used"][0]["success"] is True
    assert "MARKER = 1" in str(llm.call_log[-1]["messages"])


def test_missing_context_folder_falls_back_with_warning(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    body = client.post(CHAT, json={"query": "hi", "context_folder": "/definitely/not/here"}).json()
    assert body["ok"] is True
    assert any("not found" in w for w in body["warnings"])


def test_context_folder_can_be_disabled(make_client, tmp_path):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV), allow_context_folder=False)
    body = client.post(CHAT, json={"query": "hi", "context_folder": str(tmp_path)}).json()
    assert any("ignored" in w for w in body["warnings"])


# --------------------------------------------------------------- pipeline --

def test_pipeline_mode_runs_debug_dev_test_chain(make_client):
    llm = FakeWithModels(canned_responses=[
        {"status": "success", "result": "Root cause: KeyError.", "most_probable_cause": "unguarded lookup"},
        {"status": "success", "result": "Fixed.", "generated_code": "def f():\n    return 1"},
        {"status": "success", "result": "Tests written."},
    ])
    client, _ = make_client(llm)
    body = client.post(CHAT, json={"query": "KeyError in login", "mode": "pipeline"}).json()
    assert body["ok"] and body["agent"] == "orchestrator"
    assert body["pipeline"]["steps"] == ["debugging_agent", "developer_agent", "testing_agent"]
    assert len(body["pipeline"]["handoffs"]) == 2
    assert "### 1. Debugging Agent" in body["answer"]


def test_pipeline_failure_when_ollama_down_is_503(make_client):
    client, _ = make_client(FakeWithModels(available=False))
    r = client.post(CHAT, json={"query": "KeyError in login", "mode": "pipeline"})
    assert r.status_code == 503
    assert r.json()["agent"] == "orchestrator"


# ----------------------------------------------------------- health / auth --

def test_health_ok(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["ollama"]["model_available"] is True
    assert h["verification_enabled"] is True
    assert "developer_agent" in h["agents"]


def test_health_reports_ollama_down(make_client):
    client, _ = make_client(FakeWithModels(available=False))
    r = client.get("/api/health")
    assert r.status_code == 200                                     # health itself never 5xx
    h = r.json()
    assert h["status"] == "degraded" and h["ollama"]["reachable"] is False
    assert any("ollama serve" in p for p in h["problems"])


def test_health_reports_model_not_pulled(make_client):
    client, _ = make_client(FakeWithModels(models=("llama3:8b",)))
    h = client.get("/api/health").json()
    assert h["status"] == "degraded" and h["ollama"]["model_available"] is False
    assert any("ollama pull qwen2.5-coder:7b" in p for p in h["problems"])


def test_agents_endpoint_lists_all_five_agents(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV))
    names = {a["name"] for a in client.get("/api/agents").json()}
    assert names == {"developer_agent", "debugging_agent", "testing_agent", "security_agent", "documentation_agent"}


def test_token_auth(make_client):
    client, _ = make_client(FakeWithModels(canned_response=OK_DEV), token="s3cret")
    assert client.post(CHAT, json={"query": "hi"}).status_code == 401
    assert client.post(CHAT, json={"query": "hi"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.post(CHAT, json={"query": "hi"}, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert client.get("/api/health").status_code == 401
