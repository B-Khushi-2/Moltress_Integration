"""
agents/tests/conftest.py

Shared pytest fixtures for agent tests.

Tests use a FakeOllamaClient instead of a real Ollama server so the whole
suite runs fast, deterministically, and without requiring a local model
to be pulled/running. This satisfies requirement #20 ("do not require an
actual large model for every unit test... use mocks where appropriate").

FakeOllamaClient supports two modes:
  - Single canned_response (original v1 behavior): every call returns the
    same dict. This is what most existing single-shot-agent tests use.
  - canned_responses (a list, new in v2): calls consume the list in
    order, returning the last entry repeatedly once exhausted. This is
    what multi-turn tool-use-loop tests use (e.g. first response is a
    tool call, second is the final answer).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from agents.llm.ollama_client import LLMMessage, LLMResult, OllamaClient


class FakeOllamaClient(OllamaClient):
    """
    A drop-in stand-in for OllamaClient that returns pre-programmed
    JSON payload(s) instead of calling a real Ollama server.
    """

    def __init__(
        self,
        canned_response: Optional[Dict[str, Any]] = None,
        canned_responses: Optional[List[Dict[str, Any]]] = None,
        available: bool = True,
    ):
        # Deliberately do not call super().__init__() — we don't want a
        # real requests.Session or config dependency for these tests.
        if canned_responses is not None:
            self._responses: List[Dict[str, Any]] = list(canned_responses)
        elif canned_response is not None:
            self._responses = [canned_response]
        else:
            self._responses = [{}]
        self._call_index = 0
        self._available = available

        # Full call history, for tests that want to assert on what the
        # agent actually sent the model at each turn.
        self.call_log: List[Dict[str, Any]] = []

        # Kept for backward compatibility with any code referencing these
        # single-value attributes; reflects the MOST RECENT call.
        self.last_system_prompt: Optional[str] = None
        self.last_messages: Optional[List[LLMMessage]] = None

    def _next_response(self) -> Dict[str, Any]:
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
        else:
            resp = self._responses[-1]
        self._call_index += 1
        return resp

    def _record(self, system_prompt: str, messages: List[LLMMessage]) -> None:
        self.last_system_prompt = system_prompt
        self.last_messages = messages
        self.call_log.append({"system_prompt": system_prompt, "messages": list(messages)})

    def is_available(self) -> bool:
        return self._available

    def chat(self, system_prompt, messages, model=None, json_mode=None, temperature=None) -> LLMResult:
        self._record(system_prompt, messages)
        text = json.dumps(self._next_response())
        return LLMResult(text=text, raw_response={"message": {"content": text}}, model=model or "fake-model", duration_ms=1.0)

    def chat_json(self, system_prompt, messages, model=None, temperature=None) -> Dict[str, Any]:
        self._record(system_prompt, messages)
        return dict(self._next_response())

    @property
    def call_count(self) -> int:
        return len(self.call_log)


@pytest.fixture
def fake_llm_factory():
    """
    Factory fixture.

    Usage:
        fake_llm_factory(canned_response)                 # single-shot (v1 style)
        fake_llm_factory(canned_responses=[a, b, c])       # multi-turn tool loop
        fake_llm_factory(available=False)                  # simulate LLM down
    """

    def _make(
        canned_response: Optional[Dict[str, Any]] = None,
        canned_responses: Optional[List[Dict[str, Any]]] = None,
        available: bool = True,
    ) -> FakeOllamaClient:
        return FakeOllamaClient(canned_response=canned_response, canned_responses=canned_responses, available=available)

    return _make
