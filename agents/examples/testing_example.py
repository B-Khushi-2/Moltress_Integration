"""
examples/testing_example.py

Run with:  python -m examples.testing_example
"""

from agents.testing_agent import TestingAgent
from agents.schemas.common import AgentRequest

SAMPLE_CODE = """
def add(a, b):
    return a + b
"""


def main():
    agent = TestingAgent()
    request = AgentRequest(
        query="Write unit tests for this function, including edge cases.",
        code=SAMPLE_CODE,
    )
    response = agent.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
