"""
agents/schemas/testing.py
============================

Specialized response structure for the Testing Agent.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from agents.schemas.common import AgentResponse


class GeneratedTestCase(BaseModel):
    name: str
    description: Optional[str] = None
    test_type: str = Field("unit", description="'unit', 'integration', 'edge_case', 'regression'")
    code: str


class TestExecutionResult(BaseModel):
    passed: bool
    total: int = 0
    failed: int = 0
    output_summary: Optional[str] = None


class TestingAgentResponse(AgentResponse):
    """Response returned by TestingAgent.run()."""

    test_file_name: Optional[str] = None
    generated_tests: List[GeneratedTestCase] = Field(default_factory=list)
    identified_edge_cases: List[str] = Field(default_factory=list)
    coverage_notes: Optional[str] = None
    execution_result: Optional[TestExecutionResult] = Field(
        None, description="Populated only if test execution was explicitly enabled and performed"
    )
