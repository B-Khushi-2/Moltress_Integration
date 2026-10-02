"""
agents/evaluation/
====================

AI response QUALITY evaluation — separate from agents/tests/, which
checks software correctness with mocked LLM responses.

This package provides a small representative dataset (dataset.py) and a
harness (harness.py) to run real agents against real tasks and produce a
structured review report: a handful of objective, automatically-checked
properties (did the agent call the tools it needed to?) plus a fillable
human-review checklist for the properties that genuinely require
judgment (factual correctness, hallucination, appropriate uncertainty).

This package does NOT compute or claim an overall "accuracy" percentage.
"""

from agents.evaluation.dataset import ALL_CASES, CASES_BY_AGENT, EvaluationCase
from agents.evaluation.harness import EvaluationHarness, EvaluationReport

__all__ = [
    "ALL_CASES",
    "CASES_BY_AGENT",
    "EvaluationCase",
    "EvaluationHarness",
    "EvaluationReport",
]
