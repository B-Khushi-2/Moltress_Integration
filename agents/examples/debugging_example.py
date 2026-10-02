"""
examples/debugging_example.py

Run with:  python -m examples.debugging_example
"""

from agents.debugging_agent import DebuggingAgent
from agents.schemas.common import AgentContext, AgentRequest, SourceFile

BUGGY_CODE = """
def compute_average(values):
    return sum(values) / len(values)
"""

STACK_TRACE = """
Traceback (most recent call last):
  File "app.py", line 10, in <module>
    compute_average([])
  File "app.py", line 2, in compute_average
    return sum(values) / len(values)
ZeroDivisionError: division by zero
"""


def main():
    agent = DebuggingAgent()
    request = AgentRequest(
        query="Why is this raising ZeroDivisionError, and how should I fix it?",
        context=AgentContext(
            error_logs=STACK_TRACE,
            source_files=[SourceFile(path="app.py", content=BUGGY_CODE, language="python")],
        ),
    )
    response = agent.run(request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
