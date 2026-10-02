#!/usr/bin/env python3
"""
Live verification of the Moltress agent chain against a REAL Ollama server.

Run this on a machine that has Ollama and the model, after configuring `.env`:

    ollama serve                         # if not already running
    ollama pull qwen2.5-coder:7b
    python scripts/verify_live_ollama.py                     # agent layer -> Ollama
    python scripts/verify_live_ollama.py --backend           # ...and via the running backend
    python scripts/verify_live_ollama.py --query "Explain the purpose of this application."

Steps (each prints PASS/FAIL, exit code is non-zero if any step fails):
  1. Ollama reachable at OLLAMA_BASE_URL
  2. OLLAMA_MODEL is pulled
  3. Raw JSON-mode round-trip through the real OllamaClient
  4. Full request through AgentService (Router -> Agent -> tools -> Ollama)
  5. (--backend) Same request over HTTP through the running backend

Nothing is mocked here. FakeOllamaClient is never used by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.settings import BackendSettings, load_env  # noqa: E402

load_env()

results: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Live Ollama verification for Moltress")
    ap.add_argument("--query", default="Explain the purpose of this application.")
    ap.add_argument("--backend", action="store_true", help="also test through the running backend over HTTP")
    ap.add_argument("--backend-url", default=None, help="default: http://HOST:PORT from the environment")
    args = ap.parse_args()

    from agents.config.agent_config import get_config
    from agents.llm.ollama_client import LLMMessage, LLMUnavailableError, OllamaClient
    from backend.models import ChatRequest
    from backend.service import AgentService

    cfg = get_config().ollama
    print(f"Ollama: {cfg.host}   model: {cfg.model}   timeout: {cfg.request_timeout_seconds}s\n")
    client = OllamaClient(cfg)

    # 1 + 2 ---------------------------------------------------------------
    if not step("Ollama reachable", client.is_available(), cfg.host):
        print("\nStart Ollama (`ollama serve`) or fix OLLAMA_BASE_URL in .env.")
        return 1
    try:
        models = client.list_models()
    except LLMUnavailableError as exc:
        step("Model is pulled", False, str(exc))
        return 1
    if not step("Model is pulled", cfg.model in models or f"{cfg.model}:latest" in models, f"installed: {', '.join(models) or 'none'}"):
        print(f"\nRun: ollama pull {cfg.model}")
        return 1

    # 3 -------------------------------------------------------------------
    t0 = time.time()
    try:
        data = client.chat_json("Reply ONLY with JSON.", [LLMMessage(role="user", content='Return {"ok": true}')])
        step("JSON-mode round-trip", isinstance(data, dict), f"{time.time() - t0:.1f}s -> {json.dumps(data)[:80]}")
    except Exception as exc:  # noqa: BLE001
        step("JSON-mode round-trip", False, f"{type(exc).__name__}: {exc}")

    # 4 -------------------------------------------------------------------
    service = AgentService(settings=BackendSettings.from_env())
    t0 = time.time()
    status, body = service.chat(ChatRequest(query=args.query))
    ok = status == 200 and body.ok and bool(body.answer.strip())
    step(
        "Agent layer end-to-end (Router -> Agent -> Ollama)",
        ok,
        f"HTTP {status}, agent={body.agent}, {time.time() - t0:.1f}s, tools={[t.tool_name for t in body.tools_used]}",
    )
    print("\n--- agent answer " + "-" * 50)
    print(body.answer if ok else (body.error.message if body.error else "(no answer)"))
    print("-" * 67 + "\n")

    # 5 -------------------------------------------------------------------
    if args.backend:
        import urllib.error
        import urllib.request

        s = BackendSettings.from_env()
        base = (args.backend_url or f"http://{s.host}:{s.port}").rstrip("/")
        req = urllib.request.Request(
            f"{base}/api/agent/chat",
            data=json.dumps({"query": args.query}).encode(),
            headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {s.api_token}"} if s.api_token else {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg.request_timeout_seconds * 3) as r:
                payload = json.loads(r.read())
            step("Backend HTTP end-to-end", bool(payload.get("ok") and payload.get("answer")), f"agent={payload.get('agent')}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            step("Backend HTTP end-to-end", False, f"{base}: {exc}  (is `npm run backend` running?)")

    failed = [r for r in results if not r[1]]
    print("ALL CHECKS PASSED" if not failed else f"{len(failed)} CHECK(S) FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
