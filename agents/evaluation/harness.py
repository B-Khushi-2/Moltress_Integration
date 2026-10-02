"""
agents/evaluation/harness.py
===============================

Runs EvaluationCase objects (agents/evaluation/dataset.py) against real
agents and produces an EvaluationReport.

IMPORTANT — what this harness IS and IS NOT:

  IS:  A way to (a) mechanically check a handful of objective properties
       of each response (did it call the tools you'd expect, is evidence
       present, is confidence populated — see `automatic_checks` on each
       case), and (b) produce a structured, fillable review sheet for the
       SUBJECTIVE rubric criteria (factual correctness, hallucination,
       appropriate uncertainty, etc.) that only a human reviewer (or a
       separately-validated, explicitly-labeled LLM-judge — NOT
       implemented here) can actually assess.

  IS NOT: An auto-grader that produces a single "accuracy" percentage.
       Software tests (agents/tests/) already establish CORRECTNESS of
       the code. This harness is about response QUALITY, which cannot be
       reduced to a pass/fail assertion without either a human or a
       separately-audited judge model — and this project does not invent
       either. `EvaluationReport.rubric_criteria` are always left as
       `None` (not yet reviewed) until a human fills them in via
       `EvaluationReport.record_human_review(...)`.

Usage
-----
    from agents.evaluation.dataset import ALL_CASES
    from agents.evaluation.harness import EvaluationHarness

    harness = EvaluationHarness()          # uses real Ollama by default
    report = harness.run_case(ALL_CASES[0])
    print(report.to_markdown())

    # Or run the whole dataset and get a summary of the AUTOMATIC checks
    # only (rubric fields remain unfilled, pending human review):
    reports = harness.run_all(ALL_CASES)
    print(EvaluationHarness.summarize_automatic_checks(reports))
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agents.config.agent_config import AgentConfig, ToolConfig
from agents.debugging_agent import DebuggingAgent
from agents.developer_agent import DeveloperAgent
from agents.documentation_agent import DocumentationAgent
from agents.evaluation.dataset import EvaluationCase
from agents.llm.ollama_client import OllamaClient
from agents.schemas.common import AgentContext, AgentRequest, AgentResponse
from agents.security_agent import SecurityAgent
from agents.testing_agent import TestingAgent

_AGENT_CLASSES = {
    "developer_agent": DeveloperAgent,
    "debugging_agent": DebuggingAgent,
    "testing_agent": TestingAgent,
    "security_agent": SecurityAgent,
    "documentation_agent": DocumentationAgent,
}


@dataclass
class EvaluationReport:
    case: EvaluationCase
    response: Optional[AgentResponse]
    run_error: Optional[str] = None

    automatic_check_results: Dict[str, bool] = field(default_factory=dict)

    # Left unfilled by the harness — a human reviewer fills these in after
    # reading the response, using `case.rubric_criteria` as the checklist.
    # None = "not yet reviewed" (NOT "failed").
    human_review: Dict[str, Optional[bool]] = field(default_factory=dict)
    human_review_notes: str = ""

    def record_human_review(self, criterion: str, passed: bool, notes: str = "") -> None:
        self.human_review[criterion] = passed
        if notes:
            self.human_review_notes += f"[{criterion}] {notes}\n"

    def to_markdown(self) -> str:
        lines = [f"### {self.case.case_id} — {self.case.title} ({self.case.agent_name})", ""]
        lines.append(f"**Task:** {self.case.description}")
        lines.append("")
        if self.run_error:
            lines.append(f"**Run failed:** {self.run_error}")
            return "\n".join(lines)

        lines.append(f"**Status:** {self.response.status}")
        lines.append(f"**Confidence:** {self.response.confidence}")
        lines.append(f"**Tools used:** {[t.tool_name for t in self.response.tools_used]}")
        lines.append("")
        lines.append("**Automatic checks:**")
        for name, passed in self.automatic_check_results.items():
            lines.append(f"- [{'x' if passed else ' '}] {name}")
        lines.append("")
        lines.append("**Human review checklist (fill in during manual review):**")
        for criterion in self.case.rubric_criteria:
            key = criterion.split(" — ")[0]
            mark = {True: "x", False: "FAILED", None: " "}[self.human_review.get(key)]
            lines.append(f"- [{mark}] {criterion}")
        if self.human_review_notes:
            lines.append("")
            lines.append(f"**Reviewer notes:**\n{self.human_review_notes}")
        return "\n".join(lines)


class EvaluationHarness:
    """
    Builds a temporary sandboxed project per case, runs the case's agent
    against a real (or injected) LLM client, and returns an
    EvaluationReport with automatic checks pre-filled.
    """

    def __init__(self, llm_client: Optional[OllamaClient] = None, config: Optional[AgentConfig] = None):
        self.llm_client = llm_client  # None -> each agent falls back to the real shared OllamaClient
        self.base_config = config

    def run_case(self, case: EvaluationCase) -> EvaluationReport:
        agent_cls = _AGENT_CLASSES.get(case.agent_name)
        if agent_cls is None:
            return EvaluationReport(case=case, response=None, run_error=f"Unknown agent '{case.agent_name}'")

        with tempfile.TemporaryDirectory() as project_root:
            for rel_path, content in case.sample_files.items():
                full_path = os.path.join(project_root, rel_path)
                os.makedirs(os.path.dirname(full_path) or project_root, exist_ok=True)
                with open(full_path, "w") as f:
                    f.write(content)

            base = self.base_config or AgentConfig()
            cfg = AgentConfig(
                ollama=base.ollama,
                tools=ToolConfig(project_root=project_root),
                orchestration=base.orchestration,
                logging=base.logging,
            )

            agent = agent_cls(llm_client=self.llm_client, config=cfg) if self.llm_client else agent_cls(config=cfg)

            request = case.build_request()
            if case.error_logs:
                request.context = AgentContext(error_logs=case.error_logs)

            try:
                response = agent.run(request)
            except Exception as exc:  # noqa: BLE001 - the harness itself must never crash a batch run
                return EvaluationReport(case=case, response=None, run_error=f"{type(exc).__name__}: {exc}")

        checks = case.automatic_checks(response) if case.automatic_checks else {}
        return EvaluationReport(case=case, response=response, automatic_check_results=checks)

    def run_all(self, cases: List[EvaluationCase]) -> List[EvaluationReport]:
        return [self.run_case(case) for case in cases]

    @staticmethod
    def summarize_automatic_checks(reports: List[EvaluationReport]) -> str:
        """
        A plain tally of the OBJECTIVE checks only — e.g. "6/8 cases had
        the agent actually call a tool when the task needed one". This is
        NOT an accuracy score and is explicitly labeled as covering only
        the mechanically-checkable properties.
        """
        lines = ["## Automatic Check Summary (objective checks only — not an accuracy score)", ""]
        total = len(reports)
        errored = sum(1 for r in reports if r.run_error)
        lines.append(f"Cases run: {total}  |  Run errors: {errored}")
        lines.append("")

        check_totals: Dict[str, List[bool]] = {}
        for r in reports:
            for name, passed in r.automatic_check_results.items():
                check_totals.setdefault(name, []).append(passed)

        for name, results in check_totals.items():
            passed_count = sum(1 for x in results if x)
            lines.append(f"- {name}: {passed_count}/{len(results)} cases passed")

        lines.append("")
        lines.append(
            "Rubric criteria (factual correctness, hallucination, appropriate uncertainty, etc.) "
            "are NOT included above — those require human review per case; see the per-case "
            "'Human review checklist' in each EvaluationReport.to_markdown()."
        )
        return "\n".join(lines)
