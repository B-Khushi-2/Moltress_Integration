"""
agents/verification.py
========================

Anti-Hallucination & Claim Verification Layer for Moltress Agent Layer.

Provides:
  - `CodeFactVerificationProvider`: Real rule-based verification provider that
    audits completed AgentResponse objects against actual source files, AST
    syntax, and tool invocation evidence to prevent hallucinated files, symbols,
    or unsubstantiated claims.
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional

from agents.providers import VerificationProvider, VerificationResult
from agents.schemas.common import AgentRequest, AgentResponse, SourceFile


class DetailedVerificationResult(VerificationResult):
    """
    Structured verification result returned by CodeFactVerificationProvider.
    """

    def __init__(
        self,
        verified: bool,
        confidence_score: float = 1.0,
        verified_claims: Optional[List[str]] = None,
        unverified_claims: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ):
        super().__init__(verified=verified, notes=notes)
        self.confidence_score = confidence_score
        self.verified_claims = verified_claims or []
        self.unverified_claims = unverified_claims or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "confidence_score": self.confidence_score,
            "verified_claims": self.verified_claims,
            "unverified_claims": self.unverified_claims,
            "notes": self.notes,
        }


class CodeFactVerificationProvider(VerificationProvider):
    """
    Verification provider that validates agent claims against the real filesystem,
    AST code structures, and tool invocation evidence.
    """

    def verify(self, response: AgentResponse, context: Optional[AgentRequest] = None) -> DetailedVerificationResult:
        verified_claims: List[str] = []
        unverified_claims: List[str] = []
        notes_list: List[str] = []

        if not response:
            return DetailedVerificationResult(verified=False, notes="No response object provided to verification.")

        # -------------------------------------------------------------------
        # Check 1: Tool Evidence Verification
        # -------------------------------------------------------------------
        if response.tools_used:
            successful_tools = [t for t in response.tools_used if t.success]
            verified_claims.append(f"{len(successful_tools)} tool call(s) executed and verified successfully.")
        elif response.status == "success":
            unverified_claims.append("Agent marked task successful without executing any tool calls for grounding.")

        # -------------------------------------------------------------------
        # Check 2: File Reference Verification
        # -------------------------------------------------------------------
        project_root = None
        known_files: Dict[str, str] = {}

        if context:
            if hasattr(context, "merged_source_files"):
                sfiles = context.merged_source_files()
            elif hasattr(context, "source_files"):
                sfiles = context.source_files
            else:
                sfiles = []
            for sf in sfiles:
                known_files[sf.path] = sf.content

        for ev in response.evidence:
            ref_file = ev.source
            if ref_file in known_files or (project_root and os.path.exists(os.path.join(project_root, ref_file))):
                verified_claims.append(f"Evidence file path '{ref_file}' verified to exist.")
            elif ref_file.endswith(".py") or ref_file.endswith(".txt") or "/" in ref_file or "\\" in ref_file:
                # Check if it exists on disk relatively
                if os.path.exists(ref_file):
                    verified_claims.append(f"Evidence file path '{ref_file}' verified on disk.")
                else:
                    unverified_claims.append(f"Evidence cites file '{ref_file}' which was not found in context or disk.")

        # -------------------------------------------------------------------
        # Check 3: Code Syntax Verification (if code generated)
        # -------------------------------------------------------------------
        generated_code = getattr(response, "generated_code", None) or getattr(response, "result", None)
        if generated_code and isinstance(generated_code, str) and ("def " in generated_code or "class " in generated_code or "import " in generated_code):
            # Extract code block if markdown fenced
            code_to_check = generated_code
            if "```python" in code_to_check:
                match = re.search(r"```python\s*(.*?)\s*```", code_to_check, re.DOTALL)
                if match:
                    code_to_check = match.group(1)

            try:
                ast.parse(code_to_check)
                verified_claims.append("Generated code block verified as syntactically valid Python AST.")
            except SyntaxError as parse_err:
                unverified_claims.append(f"Generated code block has Python syntax error: {parse_err}")

        # -------------------------------------------------------------------
        # Overall Score Calculation
        # -------------------------------------------------------------------
        total_checks = len(verified_claims) + len(unverified_claims)
        if total_checks == 0:
            verified = True
            confidence = 0.8
            notes_list.append("No explicit claims required deep verification.")
        else:
            confidence = round(len(verified_claims) / total_checks, 2)
            verified = len(unverified_claims) == 0

        notes = " | ".join(notes_list + [f"Verified {len(verified_claims)}/{total_checks} claim checks."])
        return DetailedVerificationResult(
            verified=verified,
            confidence_score=confidence,
            verified_claims=verified_claims,
            unverified_claims=unverified_claims,
            notes=notes,
        )
