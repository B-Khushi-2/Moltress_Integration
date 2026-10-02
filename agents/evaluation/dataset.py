"""
agents/evaluation/dataset.py
==============================

A small, representative evaluation dataset for AI response QUALITY
review — distinct from the pytest suite in agents/tests/, which checks
SOFTWARE CORRECTNESS (does the code run, does it return the right
shape) and never touches a real model.

This dataset is for the other, harder question: when a real local LLM
(e.g. qwen3 via Ollama) answers these tasks, is the answer actually
good — factually correct, evidence-based, appropriately uncertain, free
of invented details? That question cannot be answered by asserting on a
mocked LLM response; it requires either a human reviewer or a carefully
scoped rubric applied to real model output (see agents/evaluation/harness.py).

Each EvaluationCase bundles:
  - which agent it targets
  - a task description (the `query`, plus any code/context to supply)
  - a small sample project (files) the case operates against, so tool
    calls like read_file/search_code have something real to find
  - `automatic_checks`: properties of the RESPONSE OBJECT that can be
    verified with plain code, no judgment required (e.g. "did it call
    read_file", "is confidence populated", "is evidence non-empty")
  - `rubric_criteria`: properties that require human (or a separately
    audited LLM-as-judge, NOT provided here) review, listed so the
    review has a fixed checklist rather than an open-ended vibe check

No case in this file claims a "correct answer" the harness auto-grades
against — for tasks like debugging or security review, "correctness" is
precisely what a human reviewer must judge, using the rubric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from agents.schemas.common import AgentRequest, AgentResponse, SourceFile


# Standard rubric criteria applied to every case (agent-specific cases can
# add extra criteria on top of this list). Kept identical across agents so
# review results are comparable.
STANDARD_RUBRIC_CRITERIA: List[str] = [
    "task_completion — did the agent actually address what was asked, not a tangential rephrasing?",
    "factual_correctness — are concrete claims (behavior, cause, fix, vulnerability) actually true of the supplied code?",
    "technical_correctness — is any generated code/tests/config syntactically and logically sound?",
    "evidence_usage — does the response cite specific files/lines/tool output rather than asserting facts unsupported by evidence?",
    "no_unsupported_claims — does the response avoid inventing APIs, files, causes, or components not present in the supplied context or tool output?",
    "appropriate_uncertainty — where the agent could not verify something, does it say so (assumptions/warnings) rather than asserting confidently?",
    "successful_tool_usage — when tools were needed to answer well, did the agent actually call them (visible in tools_used), not just narrate that it would?",
]


@dataclass
class EvaluationCase:
    case_id: str
    agent_name: str  # "developer_agent" | "debugging_agent" | "testing_agent" | "security_agent" | "documentation_agent"
    title: str
    description: str

    # Files that should exist in the sandboxed project root before running
    # this case, so the agent's tools have something real to inspect.
    sample_files: Dict[str, str] = field(default_factory=dict)

    # The request to send to the agent. `code`/`context.error_logs` are
    # optional convenience fields; sample_files are written to disk
    # separately by the harness (see evaluation/harness.py).
    query: str = ""
    code: Optional[str] = None
    error_logs: Optional[str] = None

    rubric_criteria: List[str] = field(default_factory=lambda: list(STANDARD_RUBRIC_CRITERIA))

    # Callable(response) -> Dict[str, bool] of check_name -> passed.
    # These are the ONLY automatically-scored parts of a case; everything
    # else requires human review via the rubric above.
    automatic_checks: Optional[Callable[[AgentResponse], Dict[str, bool]]] = None

    def build_request(self) -> AgentRequest:
        return AgentRequest(query=self.query, code=self.code)


def _has_evidence_or_findings(response: AgentResponse) -> bool:
    return bool(response.evidence) or bool(response.metadata.get("task_state", {}).get("findings"))


# ---------------------------------------------------------------------------
# Developer Agent cases
# ---------------------------------------------------------------------------

DEVELOPER_CASES = [
    EvaluationCase(
        case_id="dev-01-code-generation",
        agent_name="developer_agent",
        title="Generate a validation function",
        description="Straightforward code-generation task with no project context supplied.",
        query="Write a Python function to validate an email address, with reasonable edge-case handling.",
        automatic_checks=lambda r: {
            "produced_code": bool(r.generated_code or r.result),
            "has_confidence": r.confidence is not None,
        },
    ),
    EvaluationCase(
        case_id="dev-02-refactor-with-context",
        agent_name="developer_agent",
        title="Refactor using real project conventions",
        description=(
            "The agent should inspect the supplied file before refactoring — a good answer will "
            "reference the ACTUAL existing function, a poor answer will invent a generic replacement "
            "without reading it."
        ),
        sample_files={
            "billing.py": (
                "def calc_total(items):\n"
                "    total = 0\n"
                "    for i in items:\n"
                "        total = total + i['price'] * i['qty']\n"
                "    return total\n"
            )
        },
        query="Refactor the calc_total function in billing.py to be more Pythonic. Read the file first.",
        automatic_checks=lambda r: {
            "used_a_tool": len(r.tools_used) >= 1,
            "read_the_real_file": any(t.tool_name == "read_file" and t.success for t in r.tools_used),
        },
    ),
]

# ---------------------------------------------------------------------------
# Debugging Agent cases — known bugs with known root causes
# ---------------------------------------------------------------------------

DEBUGGING_CASES = [
    EvaluationCase(
        case_id="dbg-01-zero-division",
        agent_name="debugging_agent",
        title="ZeroDivisionError on empty input",
        description="Known root cause: compute_average() divides by len(values) with no empty-list guard.",
        sample_files={
            "stats.py": (
                "def compute_average(values):\n"
                "    return sum(values) / len(values)\n"
            )
        },
        query="Why does calling compute_average([]) raise ZeroDivisionError? Investigate stats.py.",
        error_logs=(
            "Traceback (most recent call last):\n"
            "  File \"stats.py\", line 2, in compute_average\n"
            "    return sum(values) / len(values)\n"
            "ZeroDivisionError: division by zero\n"
        ),
        automatic_checks=lambda r: {
            "inspected_real_code": any(t.tool_name in ("read_file", "search_code") and t.success for t in r.tools_used),
            "has_evidence": _has_evidence_or_findings(r),
        },
    ),
    EvaluationCase(
        case_id="dbg-02-key-error",
        agent_name="debugging_agent",
        title="KeyError from a typo'd dict key",
        description="Known root cause: config lookup uses 'timeout_s' but the dict key is actually 'timeout_seconds'.",
        sample_files={
            "config_loader.py": (
                "DEFAULT_CONFIG = {'timeout_seconds': 30, 'retries': 3}\n\n"
                "def get_timeout(config):\n"
                "    return config['timeout_s']\n"
            )
        },
        query="get_timeout(DEFAULT_CONFIG) raises KeyError: 'timeout_s'. Find out why.",
        automatic_checks=lambda r: {
            "inspected_real_code": any(t.tool_name in ("read_file", "search_code") and t.success for t in r.tools_used),
        },
    ),
]

# ---------------------------------------------------------------------------
# Testing Agent cases — known source with expected test-relevant behavior
# ---------------------------------------------------------------------------

TESTING_CASES = [
    EvaluationCase(
        case_id="test-01-divide-edge-cases",
        agent_name="testing_agent",
        title="Edge cases for a divide function",
        description=(
            "A good answer identifies the division-by-zero edge case explicitly; a poor answer only "
            "tests the happy path."
        ),
        sample_files={"mathutil.py": "def divide(a, b):\n    return a / b\n"},
        query="Write unit tests for the divide function in mathutil.py, including edge cases.",
        automatic_checks=lambda r: {
            "generated_tests": len(r.generated_tests) >= 1,
            "read_the_real_file": any(t.tool_name == "read_file" and t.success for t in r.tools_used),
        },
    ),
]

# ---------------------------------------------------------------------------
# Security Agent cases — intentionally vulnerable code with known issues
# ---------------------------------------------------------------------------

SECURITY_CASES = [
    EvaluationCase(
        case_id="sec-01-hardcoded-secret-and-shell-injection",
        agent_name="security_agent",
        title="Hardcoded AWS key + shell=True",
        description="Known findings: a hardcoded AWS access key, and subprocess.run with shell=True on unsanitized input.",
        sample_files={
            "deploy.py": (
                "import subprocess\n\n"
                "AWS_KEY = \"AKIAABCDEFGHIJKLMNOP\"\n\n"
                "def run(cmd):\n"
                "    subprocess.run(cmd, shell=True)\n"
            )
        },
        query="Review deploy.py for security vulnerabilities.",
        automatic_checks=lambda r: {
            "found_at_least_one_issue": len(r.findings) >= 1,
            "used_scanning_tools": any(
                t.tool_name in ("scan_for_secrets", "scan_insecure_patterns") and t.success for t in r.tools_used
            ),
        },
    ),
]

# ---------------------------------------------------------------------------
# Documentation Agent cases — source with expected documentation points
# ---------------------------------------------------------------------------

DOCUMENTATION_CASES = [
    EvaluationCase(
        case_id="doc-01-stack-class",
        agent_name="documentation_agent",
        title="Document a simple Stack class",
        description="Good documentation covers push/pop and their real signatures — not invented methods.",
        sample_files={
            "stack.py": (
                "class Stack:\n"
                "    def __init__(self):\n"
                "        self._items = []\n\n"
                "    def push(self, item):\n"
                "        self._items.append(item)\n\n"
                "    def pop(self):\n"
                "        return self._items.pop()\n"
            )
        },
        query="Generate documentation for the Stack class in stack.py.",
        automatic_checks=lambda r: {
            "produced_docs": bool(r.documentation_markdown),
            "read_the_real_file": any(t.tool_name == "read_file" and t.success for t in r.tools_used),
        },
    ),
]

ALL_CASES: List[EvaluationCase] = [
    *DEVELOPER_CASES,
    *DEBUGGING_CASES,
    *TESTING_CASES,
    *SECURITY_CASES,
    *DOCUMENTATION_CASES,
]

CASES_BY_AGENT: Dict[str, List[EvaluationCase]] = {
    "developer_agent": DEVELOPER_CASES,
    "debugging_agent": DEBUGGING_CASES,
    "testing_agent": TESTING_CASES,
    "security_agent": SECURITY_CASES,
    "documentation_agent": DOCUMENTATION_CASES,
}
