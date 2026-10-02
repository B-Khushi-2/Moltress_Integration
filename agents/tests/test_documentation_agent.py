"""
agents/tests/test_documentation_agent.py
"""

from __future__ import annotations

from agents.documentation_agent import DocumentationAgent
from agents.schemas.common import AgentRequest, AgentStatus

SAMPLE_CLASS = """
class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        return self._items.pop()
"""


def test_documentation_agent_instantiation(fake_llm_factory):
    agent = DocumentationAgent(llm_client=fake_llm_factory())
    assert agent.agent_name == "documentation_agent"


def test_documentation_agent_generates_docs(fake_llm_factory):
    canned = {
        "status": "success",
        "documentation_markdown": "# Stack\n\nA simple LIFO stack.\n\n## Methods\n- `push(item)`\n- `pop()`",
        "documented_symbols": [
            {
                "name": "Stack",
                "kind": "class",
                "summary": "A simple last-in-first-out stack backed by a Python list.",
                "parameters": [],
                "returns": None,
                "source_file": "stack.py",
            },
            {
                "name": "push",
                "kind": "function",
                "summary": "Appends `item` to the internal list.",
                "parameters": ["item"],
                "returns": "None",
                "source_file": "stack.py",
            },
        ],
        "doc_format": "markdown",
        "confidence": "high",
        "evidence": [],
        "assumptions": [],
        "warnings": [],
    }
    agent = DocumentationAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(query="Generate documentation for this class.", code=SAMPLE_CLASS)

    response = agent.run(request)

    assert response.status == AgentStatus.SUCCESS
    assert response.documentation_markdown is not None
    assert len(response.documented_symbols) == 2


def test_documentation_agent_handles_llm_unavailable(fake_llm_factory):
    agent = DocumentationAgent(llm_client=fake_llm_factory(available=False))
    request = AgentRequest(query="Document this module.")

    response = agent.run(request)

    assert response.status == AgentStatus.ERROR
    assert response.error.error_type == "LLMUnavailable"
