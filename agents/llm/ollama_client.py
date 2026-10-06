"""
agents/llm/ollama_client.py
==============================

A single, reusable client for talking to a local Ollama server.

Every agent goes through this client rather than opening its own
connection. This is what lets the model be swapped (MODEL_NAME env var)
without touching any agent code, and keeps all retry/timeout/error
handling logic in one place.

Ollama exposes an HTTP API (default http://localhost:11434). We use the
`/api/chat` endpoint, which supports a system prompt + message history and
(on recent Ollama versions) a `format: "json"` option for structured
output.

No cloud APIs are used anywhere in this module — this is the core of
Moltress's "local-first, privacy-preserving" guarantee.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from agents.config.agent_config import OllamaConfig, get_config

logger = logging.getLogger("moltress.llm.ollama")


class LLMUnavailableError(Exception):
    """Raised when the Ollama server cannot be reached or errors out after retries."""


class LLMTimeoutError(Exception):
    """Raised when a request to Ollama exceeds the configured timeout."""


class LLMMalformedOutputError(Exception):
    """Raised when the model's output cannot be parsed as expected (e.g. invalid JSON)."""


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResult:
    text: str
    raw_response: Dict[str, Any]
    model: str
    duration_ms: float


class OllamaClient:
    """
    Thin, dependency-light wrapper around the Ollama HTTP API.

    Usage
    -----
        client = OllamaClient()
        result = client.chat(
            system_prompt="You are a helpful assistant.",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        print(result.text)

    The client is intentionally stateless per-call (no hidden conversation
    state) — callers (agents) are responsible for constructing the full
    message list each time, typically including relevant memory entries.
    """

    def __init__(self, config: Optional[OllamaConfig] = None):
        self.config = config or get_config().ollama
        self._session = requests.Session()

    # -- Public API ---------------------------------------------------

    def chat(
        self,
        system_prompt: str,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        json_mode: Optional[bool] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        """
        Send a chat-style request to Ollama and return the model's reply.

        Raises
        ------
        LLMUnavailableError, LLMTimeoutError
        """
        model_name = model or self.config.model
        use_json = self.config.json_mode if json_mode is None else json_mode
        temp = self.config.temperature if temperature is None else temperature

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temp,
                "top_p": self.config.top_p,
                "num_predict": self.config.max_tokens,
                "num_ctx": 4096,
            },
        }
        if use_json:
            payload["format"] = "json"

        url = f"{self.config.host.rstrip('/')}/api/chat"

        last_error: Optional[Exception] = None
        for attempt in range(self.config.num_retries + 1):
            start = time.monotonic()
            try:
                resp = self._session.post(
                    url, json=payload, timeout=self.config.request_timeout_seconds
                )
                duration_ms = (time.monotonic() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                text = data.get("message", {}).get("content", "")
                return LLMResult(text=text, raw_response=data, model=model_name, duration_ms=duration_ms)

            except requests.exceptions.Timeout as exc:
                last_error = exc
                logger.warning("Ollama request timed out (attempt %s/%s)", attempt + 1, self.config.num_retries + 1)
                continue

            except requests.exceptions.ConnectionError as exc:
                last_error = exc
                logger.warning(
                    "Could not connect to Ollama at %s (attempt %s/%s)",
                    self.config.host,
                    attempt + 1,
                    self.config.num_retries + 1,
                )
                continue

            except requests.exceptions.HTTPError as exc:
                last_error = exc
                logger.error("Ollama returned HTTP error: %s", exc)
                # Retry on 5xx (transient), fail fast on 4xx (our request was bad)
                status = resp.status_code if "resp" in locals() else None
                if status is not None and 400 <= status < 500:
                    raise LLMUnavailableError(f"Ollama rejected the request ({status}): {exc}") from exc
                continue

        if isinstance(last_error, requests.exceptions.Timeout):
            raise LLMTimeoutError(
                f"Ollama did not respond within {self.config.request_timeout_seconds}s"
            ) from last_error

        raise LLMUnavailableError(
            f"Could not reach Ollama at {self.config.host} after "
            f"{self.config.num_retries + 1} attempt(s): {last_error}"
        ) from last_error

    def chat_json(
        self,
        system_prompt: str,
        messages: List[LLMMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Convenience wrapper that requests JSON-mode output and parses it.

        Raises
        ------
        LLMUnavailableError, LLMTimeoutError, LLMMalformedOutputError
        """
        result = self.chat(system_prompt, messages, model=model, json_mode=True, temperature=temperature)
        try:
            return json.loads(result.text)
        except json.JSONDecodeError as exc:
            # Some local models wrap JSON in markdown fences even in JSON mode.
            cleaned = result.text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                raise LLMMalformedOutputError(
                    f"Model output was not valid JSON: {result.text[:300]!r}"
                ) from exc

    def list_models(self) -> List[str]:
        """
        Names of the models the Ollama server has pulled (GET /api/tags).

        Raises LLMUnavailableError if the server cannot be reached. Used by
        health checks to distinguish "Ollama is down" from "model not pulled".
        """
        try:
            resp = self._session.get(f"{self.config.host.rstrip('/')}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
        except (requests.exceptions.RequestException, ValueError) as exc:
            raise LLMUnavailableError(f"Could not list models from Ollama at {self.config.host}: {exc}") from exc

    def is_available(self) -> bool:
        """Lightweight health check against the Ollama server."""
        try:
            resp = self._session.get(f"{self.config.host.rstrip('/')}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> Optional[List[str]]:
        """
        Names of the models installed on the Ollama server (GET /api/tags),
        or None if the server cannot be queried. Used by the backend health
        check to distinguish "Ollama is down" from "model not pulled yet".
        """
        try:
            resp = self._session.get(f"{self.config.host.rstrip('/')}/api/tags", timeout=5)
            resp.raise_for_status()
            return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
        except (requests.exceptions.RequestException, ValueError):
            return None


# Module-level convenience singleton, mirroring get_config().
_default_client: Optional[OllamaClient] = None


def get_llm_client() -> OllamaClient:
    global _default_client
    if _default_client is None:
        _default_client = OllamaClient()
    return _default_client
