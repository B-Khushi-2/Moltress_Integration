# Moltress — Custom AI Agent Layer (v3)

A privacy-preserving, local-LLM-backed multi-agent layer for intelligent
software engineering assistance. This package is the **AI Agent Layer**
of the Moltress Final Year B.Tech CSE project — five specialized agents
built around a single local LLM (via Ollama), each capable of genuine,
controlled, multi-step autonomous execution, ready to be dropped into
the main Moltress backend.

> **This is not five separate LLMs.** All five agents share one local
> model (e.g. `qwen3` via Ollama). What differs between agents is their
> **role, system prompt, tool permissions, and expected output
> structure** — not the underlying model.

> **v3 note:** this is an upgrade of the existing agent layer, not a
> rebuild. Every agent, prompt, tool, schema, and test from prior
> versions is preserved. v3 adds a genuine, reusable, controlled
> autonomous execution engine (`AgentExecutionLoop`), explicit tool
> operation typing, a `NEEDS_INPUT` stop condition distinct from generic
> failure, human-readable execution traces, an AI response-quality
> evaluation framework (separate from unit tests), and three runnable
> autonomy demos. See [§18 What Changed in v3](#18-what-changed-in-v3).

---

## 1. What This Is

```
Agent = Role + System Instructions + Tools + Context + Workflow + Structured Output
```

Five specialized agents, all built on a common `BaseAgent`, all driven by
one reusable autonomous execution engine:

| Agent | Specialization |
|---|---|
| **Developer Agent** | Code generation, explanation, refactoring, implementation guidance |
| **Debugging Agent** | Root-cause analysis of errors, stack traces, and logs |
| **Testing Agent** | Unit/integration test generation, edge cases, coverage, failure analysis |
| **Security Agent** | Vulnerability identification, secret detection, severity-scored findings |
| **Documentation Agent** | Accurate technical documentation derived from real source code |

An **Agent Router** inspects an incoming request and dispatches it to
the right specialized agent, returning a full `RoutingDecision` (agent,
reason, confidence).

---

## 2. Architecture

```
User Request
    |
    v
+------------------+
|   AgentRouter     |   keyword rules -> LLM fallback -> safe default
+---------+---------+
          |
          v
+-------------------------------------------------------------+
|                     Specialized Agent                        |
|      (Developer / Debugging / Testing / Security / Docs)     |
|   -- builds prompt, resolves its permitted tools --          |
+-------------------------------------------------------------+
          |
          v
+-------------------------------------------------------------+
|                  Context Retrieval (optional)                |
|   RAGProvider        GraphProvider        MemoryProvider     |
|   -- no-ops by default; real providers plug straight in --   |
+-------------------------------------------------------------+
          |
          v
+===============================================================+
|              AgentExecutionLoop  (agents/executor.py)          |
|         THE REUSABLE, CONTROLLED AUTONOMOUS EXECUTION ENGINE   |
|                                                                 |
|   Understand Task -> Determine Next Action (LLM turn)          |
|       |                                                        |
|       v                                                        |
|   Does the model request a tool?                               |
|       |-- NO  --> raw final answer returned -----------+       |
|       |-- YES                                          |       |
|            v                                            |       |
|       VALIDATE: exists? permitted? approved? well-formed?|       |
|            v                                            |       |
|       EXECUTE (REAL, timeout-wrapped)                     |       |
|            v                                            |       |
|       OBSERVE real result -> UPDATE TASK STATE             |       |
|            v                                            |       |
|       Determine Next Action  <---(repeat, bounded)---+    |       |
|                                                          |       |
+----------------------------------------------------------+       |
          |                                                        |
          v  (raw final JSON)                                      |
+-------------------------------------------------------------+
|            Structured Output Validation (Pydantic)           |
+-------------------------------------------------------------+
          |
          v
+-------------------------------------------------------------+
|                   VerificationProvider                       |
|        (no-op by default; real verifier plugs in later)      |
+-------------------------------------------------------------+
          |
          v
   Final AgentResponse (result, evidence, confidence,
   assumptions, warnings, tools_used, execution_trace, metadata)
```

**Integration points** (clean interfaces, not full implementations — see
`agents/providers.py`): `RAGProvider`, `GraphProvider`, `MemoryProvider`,
`VerificationProvider`. Each ships with a `Null*Provider` no-op so the
agent layer runs standalone today, and each is passed straight into
`BaseAgent`/`AgentRouter` constructors — no agent code changes needed
when a real implementation is ready.

---

## 3. Final Directory Structure

```
agents/
|
├── __init__.py                 # Public API
├── base_agent.py                 # Shared BaseAgent: prompts, permissions,
│                                  #   context enrichment, verification, logging
├── executor.py                   # AgentExecutionLoop — the reusable autonomous engine (v3)
├── state.py                      # AgentTaskState — explicit execution state + trace rendering
├── providers.py                  # RAG/Graph/Memory/Verification interfaces + Null stubs
├── developer_agent.py
├── debugging_agent.py
├── testing_agent.py
├── security_agent.py
├── documentation_agent.py
├── router.py                     # AgentRouter: RoutingDecision, keyword + LLM fallback
│
├── prompts/
│   ├── developer_prompt.py
│   ├── debugging_prompt.py
│   ├── testing_prompt.py
│   ├── security_prompt.py
│   ├── documentation_prompt.py
│   └── tool_protocol.py            # Shared tool-calling JSON protocol
│
├── schemas/
│   ├── common.py                   # AgentRequest, AgentResponse, RoutingDecision,
│   │                                #   ToolInvocationRecord (+ operation_type), etc.
│   ├── developer.py
│   ├── debugging.py
│   ├── testing.py
│   ├── security.py
│   └── documentation.py
│
├── tools/
│   ├── base_tool.py                # BaseTool, ToolResult, ToolOperationType (v3),
│   │                                #   requires_approval flag
│   ├── file_tools.py                # read_file, list_files, search_files, write_file
│   ├── code_tools.py                # search_code, inspect_source, inspect_project
│   ├── terminal_tools.py            # whitelisted, approval-gated command execution
│   ├── test_tools.py                # run_tests (pytest wrapper)
│   ├── security_tools.py            # scan_for_secrets, scan_insecure_patterns
│   └── log_tools.py                 # read_logs
│
├── llm/
│   └── ollama_client.py             # Shared, reusable Ollama HTTP client
│
├── config/
│   └── agent_config.py              # Env-driven config, incl. OrchestrationConfig
│
├── evaluation/                      # AI response QUALITY evaluation (v3) — NOT unit tests
│   ├── __init__.py
│   ├── dataset.py                    # Representative cases for all 5 agents
│   └── harness.py                    # Runs cases, produces objective checks + review sheet
│
├── tests/                           # pytest suite — software correctness, mocked LLM
│   ├── conftest.py                    # FakeOllamaClient: single-shot AND multi-turn
│   ├── test_developer_agent.py
│   ├── test_debugging_agent.py
│   ├── test_testing_agent.py
│   ├── test_security_agent.py
│   ├── test_documentation_agent.py
│   ├── test_router.py
│   ├── test_tools.py
│   ├── test_orchestration.py          # loop, permissions, approvals, providers
│   └── test_executor.py               # AgentExecutionLoop, NEEDS_INPUT, operation types, trace (v3)
│
├── examples/
│   ├── developer_example.py
│   ├── debugging_example.py
│   ├── testing_example.py
│   ├── security_example.py
│   ├── documentation_example.py
│   ├── full_pipeline_example.py       # Router -> Agent -> Tool -> LLM -> Response
│   ├── demo_1_debugging_autonomous.py # DEMO 1 (v3): multi-step debugging investigation
│   ├── demo_2_developer_autonomous.py # DEMO 2 (v3): write with/without approval
│   └── demo_3_testing_autonomous.py   # DEMO 3 (v3): generate + execute tests
│
├── requirements.txt
├── .env.example
├── pytest.ini
└── README.md
```

---

## 4. What Was Already Present vs. What Was Added in v3

**Already present and preserved unchanged in spirit:**
- All five agents, their specialization boundaries, and their five
  hand-written system prompts (only minimal additions to "must not
  invent" sections across all versions — never rewritten).
- `BaseAgent`'s public interface: `agent.run(request) -> AgentResponse`.
- The tool layer's sandboxing model (`resolve_safe_path`), terminal
  whitelisting, and security scanners.
- The Pydantic request/response schemas and `AgentStatus`/
  `ConfidenceLevel` vocabulary.
- `AgentRouter.classify(query) -> str` and `route_and_run`.
- `RAGProvider` / `GraphProvider` / `MemoryProvider` / `VerificationProvider`
  interfaces, unchanged.
- The full existing test suite — every test from before still passes
  unmodified.

**Added in v3 (this round):**
1. **`AgentExecutionLoop`** (`agents/executor.py`) — the DECISION → TOOL
   → OBSERVATION → DECISION loop extracted into its own standalone,
   reusable class, decoupled from `BaseAgent` (constructible with just
   an LLM client, a tool dict, and a config — see §5).
2. **`ToolOperationType`** (READ / WRITE / EXECUTE / DESTRUCTIVE) on
   every tool, surfaced on every `ToolInvocationRecord`, satisfying the
   "clearly distinguish operation types" requirement explicitly rather
   than only via the `requires_approval` boolean.
3. **`TerminalTool` now requires approval** — running any whitelisted
   shell command is still gated by explicit per-request approval, not
   just the config opt-in flag, closing a gap from the prior version.
4. **`AgentStatus.NEEDS_INPUT`** is now used distinctly from
   `AgentStatus.PARTIAL`: if the loop stops because the model kept
   requesting actions that need approval it wasn't given, the response
   says so explicitly (`NEEDS_INPUT`) rather than reporting a generic
   technical failure (`PARTIAL`).
5. **Human-readable execution trace** (`AgentTaskState.render_trace()`),
   attached to every response at `metadata["execution_trace"]` — the
   "Task Started / Agent: X / Step 1 / Action: ... / Status: ... / Final"
   format requested for the LLMOps dashboard, deliberately excluding
   tool arguments/data.
6. **Simplified tool-call protocol alias support** — the loop now also
   recognizes `{"action": "tool", "tool": ..., "arguments": ...}` and
   `{"action": "final", "answer": ...}` alongside the existing
   `{"action": "use_tool", "tool_name": ..., "tool_arguments": ...}`
   shape, for robustness across differently-tuned local models.
7. **Tool permission matrix updated** to match the requested table
   exactly: `run_tests` added to Debugging Agent and (config-gated)
   Developer Agent; see §6.
8. **`agents/evaluation/`** — a small, honest AI response-quality
   evaluation framework, explicitly separate from `agents/tests/`; see
   §14.
9. **Three demo scripts** (`examples/demo_1..3_*.py`) showing genuine,
   non-hard-coded multi-step autonomy with real tool execution; see §12.
10. **30 new tests** (`test_executor.py` + additions), all passing
    alongside the full pre-existing suite; see §13.

---

## 5. The Autonomous Execution Loop (`AgentExecutionLoop`)

This is the concrete, reusable implementation of the requested pattern:

```
Understand Task
    |
Determine Next Action    <-- the LLM decides; nothing is hard-coded
    |
Select Tool
    |
Validate Tool              (exists? permitted? approved? well-formed?)
    |
Execute Tool                REAL execution, wall-clock timeout
    |
Observe Tool Result         the REAL result is fed back to the model
    |
Update Task State
    |
Determine Next Action  ---(repeat, bounded)---+
    |                                          |
Task Complete <----------------------------------+
```

It lives in `agents/executor.py` as `AgentExecutionLoop` — a class that
is **decoupled from `BaseAgent`**: it only needs an LLM client, a dict of
already permission-filtered tools, and a config object. Any future agent
(even one that doesn't subclass `BaseAgent`) can reuse it directly:

```python
from agents.executor import AgentExecutionLoop
from agents.config.agent_config import get_config
from agents.llm.ollama_client import get_llm_client

loop = AgentExecutionLoop(
    llm_client=get_llm_client(),
    tools={"read_file": ReadFileTool()},
    config=get_config(),
    agent_name="my_custom_agent",
)
state = loop.execute(request, system_prompt="...", initial_user_prompt="...")
```

`BaseAgent.run()` is the only current caller: it builds the initial
prompt, resolves which tools the agent may use, hands off to the loop,
then parses the loop's raw final answer into a structured
`AgentResponse` and runs verification.

**Tool-call protocol.** On each turn, the model responds with either a
tool request or a final answer:

```json
{"action": "use_tool", "tool_name": "read_file", "tool_arguments": {"path": "app.py"}, "reasoning": "..."}
```
```json
{"action": "tool", "tool": "read_file", "arguments": {"path": "app.py"}}
```

Both shapes are recognized (the second is folded into the first
internally). A final answer is any other JSON object; the simplified
`{"action": "final", "answer": "...", "confidence": ...}` shape is also
accepted, with `"answer"` folded into the schema's `"result"` field.

**No fake autonomy.** When the model requests a tool, `AgentExecutionLoop`
actually calls `tool.safe_run(**arguments)` in a real, timeout-wrapped
execution and feeds the real `ToolResult` back into the conversation.
There is no code path that produces "the agent inspected the file" text
without a matching real call — verified directly in
`test_executor.py::test_execution_loop_actually_calls_the_tool`, which
asserts the real file content appears in the next LLM turn's prompt.

---

## 6. Tool Permission Matrix

Each agent declares an explicit `allowed_tool_names` class attribute;
`BaseAgent.register_tool()` refuses to register anything outside that
list (or outside the optional process-wide `ENABLED_TOOLS` allow-list):

| Agent | Tools |
|---|---|
| **Developer** | `read_file`, `search_code`, `inspect_project`, `inspect_source`, `write_file` *(opt-in + approval)*, `run_tests` *(opt-in)* |
| **Debugging** | `read_file`, `search_files`, `search_code`, `inspect_project`, `inspect_source`, `read_logs`, `run_tests`, `run_command` *(opt-in + approval)* |
| **Testing** | `read_file`, `search_code`, `inspect_project`, `inspect_source`, `run_tests` |
| **Security** | `read_file`, `search_code`, `inspect_project`, `scan_for_secrets`, `scan_insecure_patterns` |
| **Documentation** | `read_file`, `search_code`, `inspect_project`, `inspect_source` |

**Two extra gates on top of per-agent permission:**
- **`write_file`** — only registered if `ENABLE_WRITE_TOOL=true`; even
  then requires `"write_file"` in `AgentRequest.approved_actions` for
  every individual request.
- **`run_command`** — only registered if `ENABLE_TERMINAL_TOOL=true`;
  even then requires `"run_command"` in `approved_actions` (v3: this
  used to be opt-in-only, now also approval-gated).
- **`run_tests`** — only registered if `ENABLE_TEST_EXECUTION=true`
  (and, since it uses the terminal internally, `ENABLE_TERMINAL_TOOL=true`
  too). Does NOT require per-request approval — running the existing
  test suite is READ/EXECUTE, not destructive — but stays fully
  sandboxed and command-whitelisted.

```python
from agents.schemas.common import AgentRequest

request = AgentRequest(
    query="Apply the fix and write it to app.py",
    approved_actions=["write_file"],   # explicit, per-request approval
)
```


---

## 7. Tool Operation Types (READ / WRITE / EXECUTE / DESTRUCTIVE)

Every tool declares a `ToolOperationType` (`agents/tools/base_tool.py`),
surfaced on every `ToolInvocationRecord.operation_type` for auditing:

| Type | Meaning | Examples |
|---|---|---|
| `read` | No side effects | `read_file`, `search_code`, `inspect_project`, `scan_for_secrets` |
| `write` | Creates/modifies data | (reserved for future non-file write tools) |
| `execute` | Runs a process | `run_tests`, `run_command` |
| `destructive` | Overwrites/removes data irreversibly | `write_file` |

`operation_type` is informational/auditing metadata; the actual safety
GATE is still `BaseTool.requires_approval` — a tool's type does not by
itself change execution behavior, but it does make the nature of every
recorded action explicit rather than only inferable from a boolean.

---

## 8. Safety Mechanisms

| Safeguard | Config | Default |
|---|---|---|
| Max LLM turns / tool calls per request | `MAX_TOOL_ITERATIONS` | 6 |
| Max consecutive tool failures/denials before stopping | `MAX_CONSECUTIVE_TOOL_FAILURES` | 2 |
| Per-tool-call wall-clock timeout | `TOOL_CALL_TIMEOUT_SECONDS` | 30s |
| Duplicate identical tool call | rejected automatically, always on | — |
| Destructive/high-risk tool execution | requires `AgentRequest.approved_actions` | denied by default |
| Path traversal (`../../etc/passwd` etc.) | `resolve_safe_path()` sandboxing | always on |
| Shell metacharacters in terminal commands | rejected regardless of whitelist | always on |
| Tool permitted for this agent at all | `allowed_tool_names` | enforced always |

**Stop conditions** (never infinite):
- Model produces a final answer → `completed`.
- Iteration ceiling reached while still requesting tools → `stopped_max_iterations` → `AgentStatus.PARTIAL`.
- Consecutive failures/denials hit the limit, and they were genuine
  technical failures → `stopped_tool_failures` → `AgentStatus.PARTIAL`.
- Consecutive failures were all approval denials → `stopped_needs_approval`
  → **`AgentStatus.NEEDS_INPUT`** (v3: distinct from a generic failure,
  so a caller knows a human decision — not a retry — is what's needed).

When the loop stops without a final answer, the response's `explanation`
and `warnings` always state exactly what was tried and why it stopped —
never a silent or misleading result.

---

## 9. Failure Recovery

If a tool fails, its real error is fed back to the model as an
observation (`"Tool 'X' failed: <real error>"`), and the model — not a
hard-coded rule — decides what to do next: retry with different
arguments, try a different tool, or give up and explain the limitation
in its final answer. The loop does not automatically retry a failing
call itself; `MAX_CONSECUTIVE_TOOL_FAILURES` puts a hard ceiling on how
many times this can happen before the loop stops on its own (see §8).
Duplicate identical calls are rejected outright, which also prevents one
common failure-recovery anti-pattern (blindly repeating the same failed
call forever).

---

## 10. Verification Integration

Every response — successful, partial, or needs-input — is passed
through the configured `VerificationProvider`:

```python
draft = agent.run(request)   # internally: Draft Result -> VerificationProvider.verify() -> Final Response
print(draft.metadata["verification"])
# {"verified": False, "notes": "Verification layer not yet integrated."}   <- default (NullVerificationProvider)
```

This package does **not** pretend a real verification engine already
exists — `NullVerificationProvider` always returns `verified=False` with
an honest note. A real implementation plugs in by subclassing
`VerificationProvider` and passing an instance into any agent or the
router (see §16). The agent supplies everything a real verifier would
need: `evidence`, `assumptions`, `confidence`, `tools_used` (which files/
commands were actually consulted), and the full `execution_trace`.

---

## 11. RAG / Knowledge Graph / Memory

Unchanged interfaces, still no-ops by default:

```python
Task -> Retrieve context (RAGProvider / GraphProvider / MemoryProvider) -> Agent -> Tools -> Verification
```

`BaseAgent._enrich_context()` calls these providers (if `rag_enabled` /
`graph_enabled` / `memory_enabled` is set AND a real provider instance
is supplied) before the first LLM turn, and never overwrites context
already supplied directly on the request. No vector database, Neo4j
client, or memory store is implemented inside this package — those are
integrated separately, per the interfaces in `agents/providers.py`.

---

## 12. Demo Scenarios

Three runnable demos, each showing genuine autonomy (the LLM decides the
next action; nothing is a hard-coded sequence) with **real** tool
execution against small, safe sample projects:

```bash
python -m agents.examples.demo_1_debugging_autonomous            # live Ollama
python -m agents.examples.demo_1_debugging_autonomous --scripted # reproducible, no Ollama needed
python -m agents.examples.demo_2_developer_autonomous
python -m agents.examples.demo_3_testing_autonomous
```

- **Demo 1 — Debugging Agent:** reads `login.py`, searches for the
  implicated symbol, runs the real test suite, and produces a diagnosis
  from real evidence gathered across three real tool calls.
- **Demo 2 — Developer Agent:** shows the *same* proposed fix run twice
  — once **without** approval (write is denied, file genuinely
  unchanged, real tests genuinely still pass, response is
  `NEEDS_INPUT`) and once **with** approval (write genuinely happens,
  and the real test run genuinely fails because the stricter validation
  now rejects the old test fixture's short password — reported honestly
  as `PARTIAL`, not glossed over).
- **Demo 3 — Testing Agent:** reads `divide.py`, generates edge-case
  tests, has a `write_file` request correctly rejected (Testing Agent
  isn't permitted that tool — demonstrating real permission
  enforcement), returns the tests structurally, and then the tests are
  genuinely written and run with pytest, reporting the real pass count.

`--scripted` demos use a scripted `FakeOllamaClient` for reproducibility
in a live presentation — **only the model's decisions are scripted; every
tool call still genuinely executes** against real files on disk. This is
explicitly labeled in each script's docstring and console output so it
is never mistaken for narrated/simulated autonomy.

---

## 13. Testing Performed

```bash
cd agents
python -m pytest tests/ -v
```

**71 tests passed, 0 failed.** (41 pre-existing + 30 added across
versions, most recently `test_executor.py`'s 11 new cases for this
round.) All tests run against a `FakeOllamaClient` — no live Ollama
server is required for the suite.

| Test file | Covers |
|---|---|
| `test_developer_agent.py` / `test_debugging_agent.py` / `test_testing_agent.py` / `test_security_agent.py` / `test_documentation_agent.py` | Per-agent instantiation, structured responses, error handling |
| `test_router.py` | Keyword routing, `RoutingDecision`, `enabled_agents`, routing metadata |
| `test_tools.py` | Sandboxing, terminal whitelisting, `write_file`, `read_logs` |
| `test_orchestration.py` | Multi-turn tool use, permissions, approval gating, stop conditions, duplicate-call rejection, RAG/Graph/Memory injection, Verification |
| `test_executor.py` | `AgentExecutionLoop` as a standalone class, alias tool-call protocol, `NEEDS_INPUT` vs `PARTIAL`, `ToolOperationType`, execution trace content/exclusions |

Explicitly covered scenarios requested: starting an autonomous task,
selecting a valid tool, real tool execution, tool result returned to the
agent, multiple tool calls in sequence, stopping on completion,
respecting max iterations, respecting max consecutive failures,
rejecting unauthorized tools, rejecting invalid tool names/arguments,
handling tool failures, recovering from a tool failure (model adapts on
the next turn), requiring approval for dangerous operations, invoking
verification, generating an execution trace, handling Ollama
unavailable/timeout/malformed-output, and validating the final response
against its schema.

---

## 14. AI Response Quality Evaluation (Separate From Testing)

**Software correctness** (does the code run, is the response shape
valid) is what `agents/tests/` checks, with a mocked LLM, and that suite
passing is **not** a claim about AI response quality.

**AI response quality** is a different, harder question answered by
`agents/evaluation/` — and this package does **not** invent a number for
it (no "90% accuracy" claim anywhere).

```python
from agents.evaluation import ALL_CASES, EvaluationHarness

harness = EvaluationHarness()          # real Ollama by default
reports = harness.run_all(ALL_CASES)   # 7 representative cases across all 5 agents
for r in reports:
    print(r.to_markdown())
print(EvaluationHarness.summarize_automatic_checks(reports))
```

Each `EvaluationCase` (developer: code generation + context-aware
refactor; debugging: two known bugs with known root causes; testing:
known source with an expected edge case; security: intentionally
vulnerable code with known findings; documentation: a class with
expected documentation points) produces an `EvaluationReport` with two
distinct parts:

1. **`automatic_check_results`** — objective, mechanically-verifiable
   properties (e.g. "did the agent actually call `read_file`", "were
   any findings/tests/docs produced"). These ARE computed automatically.
2. **A human-review checklist**, generated from `STANDARD_RUBRIC_CRITERIA`
   (task completion, factual correctness, technical correctness,
   evidence usage, no unsupported claims, appropriate uncertainty,
   successful tool usage) — left as `None` ("not yet reviewed") until a
   human fills them in via `report.record_human_review(...)`. These are
   **NOT** auto-scored, because doing so honestly requires either a
   human or a separately-audited judge model, neither of which this
   package fabricates.

`EvaluationHarness.summarize_automatic_checks()` produces a plain tally
of only the objective checks, explicitly labeled as not an accuracy
score.

---

## 15. Installation & Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r agents/requirements.txt
cp agents/.env.example .env

# Local LLM:
ollama pull qwen3
ollama serve
```

Run an agent directly:

```python
from agents.developer_agent import DeveloperAgent
from agents.schemas.common import AgentRequest

agent = DeveloperAgent()
response = agent.run(AgentRequest(query="Create a Python function to validate an email."))
print(response.status, response.generated_code, response.tools_used)
```

Or via the router:

```python
from agents.router import AgentRouter
router = AgentRouter()
response = router.route_and_run(AgentRequest(query="Why is this API returning 500?"))
```

---

## 16. Integrating Into the Main Moltress Backend (FastAPI)

No UI code, no global state, no hard-coded paths:

```python
from fastapi import FastAPI
from agents.router import AgentRouter
from agents.schemas.common import AgentRequest

app = FastAPI()
router = AgentRouter()   # build once, reuse across requests

@app.post("/agent/query")
def query_agent(request: AgentRequest):
    response = router.route_and_run(request)
    return response.model_dump()
```

Wire in the real RAG / Knowledge Graph / Memory / Verification modules
by implementing the interfaces in `agents/providers.py` and passing them
into the router once at startup:

```python
from agents.providers import RAGProvider, GraphProvider, MemoryProvider, VerificationProvider

class MyVerificationProvider(VerificationProvider):
    def verify(self, response, context):
        # cross-check response.evidence / response.tools_used against real sources
        ...

router = AgentRouter(
    rag_provider=MyRAGProvider(),
    graph_provider=MyGraphProvider(),
    memory_provider=MyMemoryProvider(),
    verification_provider=MyVerificationProvider(),
)
```

Set `RAG_ENABLED=true` / `GRAPH_ENABLED=true` / `MEMORY_ENABLED=true` so
`BaseAgent` actually calls these providers.

**Adding a new agent** or **adding a new tool** — see the equivalent
sections in prior README revisions (the process is unchanged): declare
`allowed_tool_names`, add the tool to `default_tools()`, register in the
router. `AgentExecutionLoop` and `BaseAgent` need no changes for either.

---

## 17. Security Notes

- **File tools** are sandboxed to `MOLTRESS_PROJECT_ROOT` via
  `resolve_safe_path()` — path traversal is rejected.
- **`write_file`** is off by default twice over: `ENABLE_WRITE_TOOL=true`
  to register it, AND per-request `approved_actions` to execute it.
- **`run_command`** is off by default (`ENABLE_TERMINAL_TOOL=false`);
  when enabled, restricted to a whitelist with `shell=False` and
  rejection of shell metacharacters — **and now also approval-gated**
  (v3), matching "potentially dangerous terminal commands" needing
  explicit approval.
- **Every tool call is wrapped in a wall-clock timeout**
  (`TOOL_CALL_TIMEOUT_SECONDS`), independent of any timeout the tool
  manages internally.
- **Logging** redacts request/response payloads by default; tool
  arguments/data are never logged regardless of that flag, and the
  execution trace deliberately excludes them too (verified by
  `test_execution_trace_is_generated_and_excludes_arguments`).

---

## 18. What Changed in v3

See §4 for the full breakdown. In one line: the loop that was inline in
`BaseAgent.run()` (added in v2) is now a standalone, reusable
`AgentExecutionLoop`, with explicit operation typing, a distinct
`NEEDS_INPUT` stop condition, human-readable execution traces, a wider
tool-call protocol, an updated tool permission matrix (`run_tests` added
to Debugging and Developer agents), an honest AI-quality evaluation
framework, and three demo scripts proving the autonomy is real.

---

## 19. Limitations

- This package implements the **agent layer only** — no UI, no real
  RAG/vector-DB/Knowledge-Graph/Memory backend, no real Verification
  engine, no authentication, no cloud deployment tooling.
- `AgentResponse.confidence` is the model's own self-reported confidence;
  it is not independently verified without a real `VerificationProvider`.
- `agents/evaluation/` deliberately does not produce an overall accuracy
  score — see §14 for why.
- The tool-calling protocol relies on the local model reliably following
  JSON-mode instructions; malformed tool-call JSON is handled as a
  structured `MalformedOutput` error, not a crash, but may need prompt
  tuning for a specific weaker local model in practice.
- No agent can guarantee hallucination-free output on its own — this is
  by design; `evidence`/`assumptions`/`confidence`/`tools_used`/
  `execution_trace` exist specifically so a downstream Verification
  layer or a human can check the agent's claims.
