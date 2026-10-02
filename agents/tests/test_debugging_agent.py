"""
agents/tests/test_debugging_agent.py
"""

from __future__ import annotations

from agents.debugging_agent import DebuggingAgent
from agents.schemas.common import AgentContext, AgentRequest, AgentStatus, SourceFile


BUGGY_CODE = """
def divide(a, b):
    return a / b

def compute_average(values):
    return sum(values) / len(values)
"""

STACK_TRACE = """
Traceback (most recent call last):
  File "app.py", line 10, in <module>
    compute_average([])
  File "app.py", line 6, in compute_average
    return sum(values) / len(values)
ZeroDivisionError: division by zero
"""


def test_debugging_agent_instantiation(fake_llm_factory):
    agent = DebuggingAgent(llm_client=fake_llm_factory())
    assert agent.agent_name == "debugging_agent"


def test_debugging_agent_diagnoses_from_stack_trace(fake_llm_factory):
    canned = {
        "status": "success",
        "error_summary": "ZeroDivisionError raised in compute_average when called with an empty list.",
        "candidate_causes": [
            {
                "description": "compute_average does not guard against an empty `values` list before dividing.",
                "likelihood": 0.95,
                "supporting_evidence": ["app.py:6 divides by len(values) with no zero check"],
                "ruled_out": False,
            }
        ],
        "most_probable_cause": "Empty list passed to compute_average causes division by zero.",
        "suggested_fixes": [
            {
                "file_path": "app.py",
                "change_summary": "Guard against empty input before dividing.",
                "diff_or_content": "if not values:\n    return 0.0\nreturn sum(values) / len(values)",
                "risk": "low",
            }
        ],
        "confidence": "high",
        "evidence": [],
        "assumptions": [],
        "warnings": [],
    }
    agent = DebuggingAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(
        query="Why is this raising ZeroDivisionError?",
        context=AgentContext(
            error_logs=STACK_TRACE,
            source_files=[SourceFile(path="app.py", content=BUGGY_CODE, language="python")],
        ),
    )

    response = agent.run(request)

    assert response.status == AgentStatus.SUCCESS
    assert response.most_probable_cause is not None
    assert len(response.candidate_causes) >= 1
    assert len(response.suggested_fixes) >= 1


def test_debugging_agent_handles_malformed_llm_output(fake_llm_factory):
    # 'candidate_causes' has the wrong type (should be a list of objects)
    canned = {"status": "success", "candidate_causes": "not-a-list"}
    agent = DebuggingAgent(llm_client=fake_llm_factory(canned))
    request = AgentRequest(query="Diagnose this error.")

    response = agent.run(request)

    assert response.status == AgentStatus.ERROR
    assert response.error.error_type == "MalformedOutput"
