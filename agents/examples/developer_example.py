"""
examples/developer_example.py

Run with:  python -m examples.developer_example
(from the directory containing the `agents` package, with Ollama running
and MODEL_NAME pulled, e.g. `ollama pull qwen3`)
"""

from agents.developer_agent import DeveloperAgent
from agents.schemas.common import AgentRequest


def main():
    agent = DeveloperAgent()
    request = AgentRequest(
        query="Create a Python function to validate an email address, with basic edge-case handling.",
    )
    response = agent.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
