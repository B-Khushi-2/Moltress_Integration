"""
examples/documentation_example.py

Run with:  python -m examples.documentation_example
"""

from agents.documentation_agent import DocumentationAgent
from agents.schemas.common import AgentRequest

SAMPLE_CLASS = """
class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        return self._items.pop()
"""


def main():
    agent = DocumentationAgent()
    request = AgentRequest(
        query="Generate documentation for this class.",
        code=SAMPLE_CLASS,
    )
    response = agent.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
