"""
examples/full_pipeline_example.py

Demonstrates the complete Moltress agent pipeline end to end:

    User Query -> Router -> Agent -> Tool execution -> LLM -> Structured Response

This sets up a tiny sample "project" on disk (so the sandboxed file tools
have something real to inspect), routes a debugging-flavored query
through AgentRouter, and prints:
  - the router's decision (which agent, why, confidence)
  - every tool call the agent actually made and its real result
  - the final structured response

Run with:  python -m agents.examples.full_pipeline_example
(requires Ollama running locally with MODEL_NAME pulled, e.g. `ollama pull qwen3`)
"""

import json
import os
import tempfile

from agents.config.agent_config import AgentConfig, ToolConfig
from agents.router import AgentRouter
from agents.schemas.common import AgentRequest


SAMPLE_APP_CODE = """\
def compute_average(values):
    return sum(values) / len(values)


def main():
    print(compute_average([]))


if __name__ == "__main__":
    main()
"""

STACK_TRACE = """\
Traceback (most recent call last):
  File "app.py", line 6, in main
    print(compute_average([]))
  File "app.py", line 2, in compute_average
    return sum(values) / len(values)
ZeroDivisionError: division by zero
"""


def main():
    with tempfile.TemporaryDirectory() as project_root:
        with open(os.path.join(project_root, "app.py"), "w") as f:
            f.write(SAMPLE_APP_CODE)

        config = AgentConfig(tools=ToolConfig(project_root=project_root))
        router = AgentRouter(config=config)

        query = "Why is this raising ZeroDivisionError? Here's the traceback."
        decision = router.route(query)
        print("=== Routing Decision ===")
        print(f"agent:      {decision.agent_name}")
        print(f"reason:     {decision.reason}")
        print(f"confidence: {decision.confidence}")
        print(f"rule:       {decision.matched_rule}")
        print()

        request = AgentRequest(query=query)
        request.context.error_logs = STACK_TRACE

        response = router.route_and_run(request)

        print("=== Tool Calls Made (real execution, real results) ===")
        for call in response.tools_used:
            print(f"- {call.tool_name}({call.arguments}) -> success={call.success} | {call.summary}")
        print()

        print("=== Final Structured Response ===")
        print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
