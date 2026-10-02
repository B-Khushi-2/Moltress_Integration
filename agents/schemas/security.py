"""
agents/schemas/security.py
=============================

Specialized response structure for the Security Agent.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.schemas.common import AgentResponse


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityFinding(BaseModel):
    vulnerability: str = Field(..., description="Short name, e.g. 'Hardcoded credential', 'SQL Injection risk'")
    severity: Severity
    affected_area: str = Field(..., description="File path / function / config key")
    explanation: str
    recommended_fix: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    cwe_reference: Optional[str] = Field(None, description="e.g. 'CWE-798' if identifiable")


class SecurityAgentResponse(AgentResponse):
    """Response returned by SecurityAgent.run()."""

    findings: List[SecurityFinding] = Field(default_factory=list)
    overall_risk_summary: Optional[str] = None
    scanned_files: List[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)
