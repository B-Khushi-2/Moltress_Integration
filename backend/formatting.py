"""
backend/formatting.py
=====================

Turns an agent's structured ``AgentResponse`` (or one of its specialised
subclasses) into a single Markdown string the chat UI can render directly.

Every agent shares the common envelope (``result`` / ``explanation`` / ...)
but adds its own fields (``findings``, ``suggested_fixes``,
``generated_tests`` ...). Rendering them here keeps the UI free of any
agent-specific knowledge: adding a sixth agent only needs a branch below
(or nothing at all - the common envelope is always rendered).
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from agents.schemas.common import AgentResponse

_AGENT_LABELS = {
    "developer_agent": "Developer Agent",
    "debugging_agent": "Debugging Agent",
    "testing_agent": "Testing Agent",
    "security_agent": "Security Agent",
    "documentation_agent": "Documentation Agent",
    "orchestrator": "Multi-Agent Pipeline",
}


def agent_label(agent_name: Optional[str]) -> str:
    if not agent_name:
        return "Agent"
    return _AGENT_LABELS.get(agent_name, agent_name.replace("_", " ").title())


def _fence(code: str, lang: Optional[str] = None) -> str:
    code = code.strip("\n")
    # Use a longer fence if the code itself contains ``` so it can't break out.
    fence = "```"
    while fence in code:
        fence += "`"
    return f"{fence}{lang or ''}\n{code}\n{fence}"


def _bullets(items: Iterable[Any]) -> str:
    return "\n".join(f"- {str(i).strip()}" for i in items if str(i).strip())


def _section(title: str, body: Optional[str]) -> Optional[str]:
    if body and body.strip():
        return f"**{title}**\n\n{body.strip()}"
    return None


def _contains(haystack: Optional[str], needle: Optional[str]) -> bool:
    return bool(haystack and needle and needle.strip() and needle.strip() in haystack)


def render_body(resp: AgentResponse) -> str:
    """Markdown for the agent's actual content (no footer)."""
    g = lambda name, default=None: getattr(resp, name, default)  # noqa: E731
    parts: List[Optional[str]] = []

    primary = g("documentation_markdown") or resp.result
    if primary and primary.strip():
        parts.append(primary.strip())

    # -- Developer ---------------------------------------------------------
    code = g("generated_code")
    if code and not _contains(primary, code):
        parts.append(_fence(code, g("language")))
    changes = g("proposed_changes") or []
    if changes:
        blocks = []
        for c in changes:
            head = f"`{c.file_path}` ({c.change_type})"
            if c.rationale:
                head += f" - {c.rationale}"
            blocks.append(head + "\n\n" + _fence(c.diff_or_content))
        parts.append(_section("Proposed changes", "\n\n".join(blocks)))
    parts.append(_section("Design notes", _bullets(g("design_notes") or [])))
    parts.append(_section("Suggested follow-ups", _bullets(g("follow_up_suggestions") or [])))

    # -- Debugging ---------------------------------------------------------
    parts.append(_section("Error summary", g("error_summary")))
    parts.append(_section("Most probable cause", g("most_probable_cause")))
    causes = [c for c in (g("candidate_causes") or []) if not c.ruled_out]
    if causes:
        parts.append(
            _section(
                "Candidate causes",
                _bullets(f"{c.description} (likelihood {c.likelihood:.0%})" for c in causes),
            )
        )
    fixes = g("suggested_fixes") or []
    if fixes:
        blocks = []
        for f in fixes:
            head = (f"`{f.file_path}`: " if f.file_path else "") + f.change_summary
            if f.risk:
                head += f" (risk: {f.risk})"
            blocks.append(head + (("\n\n" + _fence(f.diff_or_content)) if f.diff_or_content else ""))
        parts.append(_section("Suggested fixes", "\n\n".join(blocks)))
    parts.append(_section("How to reproduce", g("reproduction_notes")))

    # -- Testing -----------------------------------------------------------
    tests = g("generated_tests") or []
    if tests:
        blocks = []
        for t in tests:
            head = f"`{t.name}` ({t.test_type})" + (f" - {t.description}" if t.description else "")
            blocks.append(head + "\n\n" + _fence(t.code, "python"))
        parts.append(_section("Generated tests", "\n\n".join(blocks)))
    parts.append(_section("Edge cases", _bullets(g("identified_edge_cases") or [])))
    parts.append(_section("Coverage notes", g("coverage_notes")))
    ex = g("execution_result")
    if ex:
        status = "passed" if ex.passed else "FAILED"
        parts.append(_section("Test execution", f"{status} - {ex.total} run, {ex.failed} failed. {ex.output_summary or ''}"))

    # -- Security ----------------------------------------------------------
    parts.append(_section("Overall risk", g("overall_risk_summary")))
    findings = g("findings") or []
    if findings:
        blocks = []
        for f in findings:
            sev = str(getattr(f.severity, "value", f.severity)).upper()
            line = f"**[{sev}] {f.vulnerability}** - `{f.affected_area}`"
            if f.cwe_reference:
                line += f" ({f.cwe_reference})"
            blocks.append(f"{line}\n\n{f.explanation}\n\n*Fix:* {f.recommended_fix}")
        parts.append(_section("Findings", "\n\n".join(blocks)))

    # -- Documentation -----------------------------------------------------
    symbols = g("documented_symbols") or []
    if symbols and not g("documentation_markdown"):
        parts.append(_section("Symbols", _bullets(f"`{s.name}` ({s.kind}): {s.summary}" for s in symbols)))

    # -- Common envelope ---------------------------------------------------
    if resp.explanation and not _contains(primary, resp.explanation):
        parts.append(_section("Explanation", resp.explanation))
    if resp.assumptions:
        parts.append(_section("Assumptions", _bullets(resp.assumptions)))
    if resp.warnings:
        parts.append(_section("Warnings", _bullets(resp.warnings)))

    body = "\n\n".join(p for p in parts if p)
    return body.strip()


def render_footer(resp: AgentResponse, verification: Optional[dict] = None) -> str:
    bits = [agent_label(resp.agent_name)]
    conf = getattr(resp.confidence, "value", resp.confidence)
    if conf and conf != "unknown":
        bits.append(f"confidence: {conf}")
    if resp.tools_used:
        ok = sum(1 for t in resp.tools_used if t.success)
        bits.append(f"{ok}/{len(resp.tools_used)} tool calls ok")
    if verification and verification.get("verified") is not None:
        bits.append("verified" if verification["verified"] else "not fully verified")
    return "*" + " · ".join(bits) + "*"


def render_answer(resp: AgentResponse) -> str:
    """Full, display-ready Markdown: content followed by a one-line footer."""
    body = render_body(resp)
    if not body:
        body = "_The agent completed but returned no content._"
    verification = (resp.metadata or {}).get("verification")
    return f"{body}\n\n{render_footer(resp, verification)}"
