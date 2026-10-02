# Moltress — UI + Agent Layer integration

The desktop UI answers chat messages with the **Moltress Agent Layer** (Router →
specialised agents / orchestrator → local Ollama model). No cloud service is involved.

```
USER → Chat UI (renderer, unchanged)
         │ IPC  send-message
         ▼
       Electron main  ── src/main/moltress.ts ──HTTP──►  backend/ (FastAPI)
                                                          │  AgentService
                                                          ▼
                                                        agents/  AgentRouter / AgentOrchestrator
                                                          │  specialised agent + tools + verification
                                                          ▼
                                                        OllamaClient ──► Ollama (qwen2.5-coder:7b)
```

## Quick start

Prerequisites: Node 20+, Python 3.10+, [Ollama](https://ollama.com).

```bash
# 1. Model
ollama serve                      # if it is not already running
ollama pull qwen2.5-coder:7b

# 2. Configuration
cp .env.example .env              # defaults work for a local Ollama

# 3. Python side (agent layer + backend)
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Node side (UI)
npm install

# 5. Run (two terminals)
npm run backend                   # terminal 1: http://127.0.0.1:8765
npm run dev                       # terminal 2: the desktop app
```

Verify the live model chain (no UI needed): `npm run verify:live` (add `-- --backend` to also test through the running backend).

`MOLTRESS_ENABLED=false` turns the integration off and restores stock Hermes Desktop behaviour.

## Configuration (`.env`, see `.env.example`)

| Variable | Default | Used by |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | agent layer (legacy alias `OLLAMA_HOST`) |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | agent layer (legacy alias `MODEL_NAME`) |
| `OLLAMA_TIMEOUT_SECONDS` | `300` | per Ollama call |
| `MOLTRESS_BACKEND_HOST` / `_PORT` | `127.0.0.1` / `8765` | backend bind address |
| `MOLTRESS_BACKEND_URL` | `http://127.0.0.1:8765` | Electron → backend |
| `MOLTRESS_API_TOKEN` | empty | optional bearer token (backend + app) |
| `MOLTRESS_REQUEST_TIMEOUT_MS` | `600000` | how long the UI waits for one answer |
| `MOLTRESS_PROJECT_ROOT` | repo root | default folder the agents may read |
| `MOLTRESS_ALLOW_CONTEXT_FOLDER` | `true` | let the chat's context folder override the root |
| `MOLTRESS_VERIFICATION_ENABLED` | `true` | audit agent claims against real tool results |

Real environment variables always override `.env`. The Electron app only imports `MOLTRESS_*` keys from it.

## Backend API (`backend/`)

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Backend + Ollama + model status. Always HTTP 200; `status` is `ok` or `degraded` with `problems[]`. |
| `GET /api/agents` | The five agents and their tools. |
| `POST /api/agent/chat` | Run a request. Body: `query` (required), `history[]`, `code`, `error_logs`, `files[]`, `agent`, `mode` (`auto`/`pipeline`), `context_folder`, `include_raw`. |

Responses always use one envelope: `ok`, `request_id`, `agent`, `status`, `answer` (Markdown), `routing`,
`verification`, `tools_used[]`, `warnings[]`, `error{type,message,recoverable}`, `execution_time_ms`, `model`.

| HTTP | Meaning |
|---|---|
| 200 | success / partial / needs_input |
| 400 | unknown agent name |
| 401 | missing/invalid `MOLTRESS_API_TOKEN` |
| 422 | invalid input (e.g. empty query) |
| 502 | model output failed the agent's schema |
| 503 | Ollama not reachable / model not pulled |
| 504 | timeout |

In chat, `/pipeline <problem>` runs the Debugging → Developer → Testing orchestrator pipeline.

## Safety

* The backend binds to `127.0.0.1` by default. If you expose it, set `MOLTRESS_API_TOKEN`.
* Agent file tools are read-only, sandboxed to the project root, **refuse `.env`/key files**, and skip `node_modules`/`.git`/virtualenvs.
* Write, terminal and test-execution tools are off by default (`ENABLE_*`) and a network caller can never pre-approve them.

## Tests

```bash
python -m pytest        # agent layer (88) + backend (23) — deterministic, uses FakeOllamaClient
npm test                # UI unit tests (includes tests/moltress-transport.test.ts)
npm run verify:live     # REAL Ollama + model (needs Ollama running)
```

`FakeOllamaClient` (in `agents/tests/conftest.py`) remains the deterministic double; the real `OllamaClient` is used at runtime.

`scripts/e2e/` holds the end-to-end tooling: `ollama_protocol_server.py` (a clearly-labelled **test double** that speaks
Ollama's wire protocol — not a model) and `ui_e2e.js` (drives the real Electron UI over CDP, `ENABLE_CDP=1`).

## Known limitations

* Answers arrive as one message (the agent layer validates a complete JSON object per turn); there is no token streaming.
* Stop/abort stops the UI waiting; the backend finishes the in-flight agent run.
* Agent-layer conversations are not written to the Hermes session database, so they do not appear in the Sessions list.
* Images/binary attachments are not forwarded (the code agents are text-only); text files are.
* The "Intelligence Panel" figures on the Chat screen (confidence %, token counts, "Security Vulnerabilities: None Found", …)
  are static placeholders from the original UI, **not** values from the agent. The API returns real `confidence_score`,
  `verification` and `execution_time_ms` ready to be bound to them.
* `npm run build` runs `tsc` first and stops on 6 pre-existing unused-variable errors in `Discover.tsx`, `Gateway.tsx`
  and `MemoryImages.tsx`; `npx electron-vite build` (no typecheck) builds fine.

## Troubleshooting

| UI message | Fix |
|---|---|
| "Cannot reach the Moltress backend…" | Start it: `npm run backend`; check `MOLTRESS_BACKEND_URL`. |
| "Local LLM (Ollama) is not reachable…" | `ollama serve`; check `OLLAMA_BASE_URL`. |
| "…model may not be pulled…" | `ollama pull qwen2.5-coder:7b` (or set `OLLAMA_MODEL`). |
| "did not answer within …s" | CPU inference is slow; raise `MOLTRESS_REQUEST_TIMEOUT_MS` / `OLLAMA_TIMEOUT_SECONDS`. |
| "Model output did not match the expected schema…" | The model replied off-format; retry, or use a stronger model. |
