"""
agents/executor.py
====================

AgentExecutionLoop: the reusable, controlled autonomous execution engine
shared by every Moltress agent.

This is the concrete implementation of:

    Understand Task
        |
    Determine Next Action   (LLM turn — the model decides, nothing is hard-coded)
        |
    Select Tool
        |
    Validate Tool            (exists? permitted? approved? well-formed?)
        |
    Execute Tool              (REAL execution, with a wall-clock timeout)
        |
    Observe Tool Result       (the REAL result, fed back to the model)
        |
    Update Task State
        |
    Determine Next Action  ---(repeat, bounded)---+
        |                                          |
    Task Complete <---------------------------------+
        |
    (raw final answer returned to the caller for parsing/verification)

Design notes
------------
- This class is intentionally decoupled from BaseAgent: it only needs an
  LLM client, a dict of already permission-filtered tools, and a config
  object. Any future agent — even one that does not subclass BaseAgent —
  can reuse it directly. `BaseAgent` (see agents/base_agent.py) is the
  only current caller: it builds the initial prompt, resolves which
  tools an agent may use, then hands off to this loop, and afterwards
  parses/validates the loop's raw final answer into a structured
  AgentResponse and runs verification.
- Tool selection uses a small structured JSON protocol (see
  agents/prompts/tool_protocol.py for the instructions given to the
  model). Two equivalent shapes are accepted for flexibility across
  differently-tuned local models:
      {"action": "use_tool", "tool_name": "...", "tool_arguments": {...}}
      {"action": "tool",     "tool": "...",      "arguments": {...}}
  A final answer is any JSON object that is not one of the above (or
  explicitly `{"action": "final", ...}`, with "action"/"answer" folded
  into the response schema's "result" field for convenience).
- NO FAKE AUTONOMY: when the model requests a tool, this loop actually
  calls `tool.safe_run(**arguments)` in a real, timeout-wrapped
  execution and feeds the real `ToolResult` back to the model. There is
  no code path that produces a "the agent inspected the file" narrative
  without a corresponding real tool call.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, List, Optional, Tuple

from agents.config.agent_config import AgentConfig
from agents.llm.ollama_client import (
    LLMMalformedOutputError,
    LLMMessage,
    LLMTimeoutError,
    LLMUnavailableError,
    OllamaClient,
)
from agents.schemas.common import AgentRequest, ToolInvocationRecord
from agents.state import AgentTaskState
from agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("moltress.agents.executor")


class LoopLLMError(Exception):
    """
    Raised when the underlying LLM call itself fails (unavailable,
    timed out, or produced unparsable output) — as opposed to a tool
    failure, which the loop handles internally and feeds back to the
    model. The caller (BaseAgent) converts this directly into a
    structured ERROR AgentResponse.
    """

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


class AgentExecutionLoop:
    """
    Reusable, controlled autonomous execution engine.

    Usage
    -----
        loop = AgentExecutionLoop(llm_client, tools=agent._tools, config=agent.config, agent_name=agent.agent_name)
        state = loop.execute(request, system_prompt=effective_prompt, initial_user_prompt=prompt_text)

        if state.final_result is not None:
            # model produced a final JSON answer -> caller validates it
            ...
        else:
            # loop stopped without a final answer (see state.status):
            #   "stopped_max_iterations" | "stopped_tool_failures" | "stopped_needs_approval"
            ...

    Safety
    ------
    Bounded by `config.orchestration.max_tool_iterations` (hard ceiling on
    LLM turns / tool calls) and `config.orchestration.max_consecutive_tool_failures`
    (stops early on repeated failures/denials rather than retrying
    forever). Every tool call is wrapped in a wall-clock timeout
    (`config.tools.tool_call_timeout_seconds`), independent of any
    timeout a tool manages internally. Duplicate identical tool calls
    are rejected automatically.
    """

    def __init__(
        self,
        llm_client: OllamaClient,
        tools: Dict[str, BaseTool],
        config: AgentConfig,
        agent_name: str = "agent",
    ):
        self.llm_client = llm_client
        self.tools = tools
        self.config = config
        self.agent_name = agent_name

    # -- Public entry point -------------------------------------------------

    def execute(self, request: AgentRequest, system_prompt: str, initial_user_prompt: str) -> AgentTaskState:
        """
        Run the DECISION -> TOOL -> OBSERVATION -> DECISION loop to
        completion or to a stop condition. Always returns an
        AgentTaskState (never raises for tool-level failures); raises
        `LoopLLMError` only when the LLM call itself fails, since that
        is not something a tool retry/adapt strategy can recover from.
        """
        state = AgentTaskState(request_id=request.request_id, original_query=request.query)
        max_iterations = request.max_tool_iterations or self.config.orchestration.max_tool_iterations
        messages: List[LLMMessage] = [LLMMessage(role="user", content=initial_user_prompt)]

        for iteration in range(1, max_iterations + 1):
            state.iteration = iteration

            try:
                raw = self.llm_client.chat_json(system_prompt=system_prompt, messages=messages)
            except LLMTimeoutError as exc:
                raise LoopLLMError("Timeout", str(exc)) from exc
            except LLMUnavailableError as exc:
                raise LoopLLMError("LLMUnavailable", str(exc)) from exc
            except LLMMalformedOutputError as exc:
                raise LoopLLMError("MalformedOutput", str(exc)) from exc

            action = self._parse_tool_request(raw)
            if action is not None:
                tool_name, arguments, reasoning = action
                state.record_step(f"Requested tool '{tool_name}'" + (f" — {reasoning}" if reasoning else ""))

                arguments_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
                if state.has_seen_tool_call(arguments_key):
                    observation = (
                        f"You already called '{tool_name}' with identical arguments earlier in this "
                        "task. Reusing the same call is not allowed — use the prior result, try "
                        "different arguments, or produce your final answer."
                    )
                    record = ToolInvocationRecord(
                        tool_name=tool_name, arguments=arguments, success=False,
                        summary="Duplicate call rejected", iteration=iteration, denied=True,
                    )
                    state.record_tool_call(record, arguments_key)
                else:
                    record, observation = self._execute_tool_call(tool_name, arguments, request, state, iteration)
                    state.record_tool_call(record, arguments_key)

                messages.append(LLMMessage(role="assistant", content=json.dumps(raw)))
                messages.append(
                    LLMMessage(
                        role="user",
                        content=(
                            f"## Tool Result: {tool_name}\n{observation}\n\n"
                            "Continue: request another tool if needed, or respond with your final JSON answer."
                        ),
                    )
                )

                if state.consecutive_tool_failures() >= self.config.orchestration.max_consecutive_tool_failures:
                    state.status = "stopped_needs_approval" if self._recent_calls_all_denied(state) else "stopped_tool_failures"
                    break
                continue

            # Not a tool request -> treat as the model's final answer.
            state.final_result = self._normalize_final_answer(raw)
            state.status = "completed"
            break
        else:
            # Loop exhausted without a break: max iterations reached while
            # the model was still requesting tools.
            state.status = "stopped_max_iterations"

        return state

    # -- Action parsing -------------------------------------------------------

    def _parse_tool_request(self, raw: Any) -> Optional[Tuple[str, Dict[str, Any], Optional[str]]]:
        """
        Recognize a tool-call request in either supported JSON shape:
            {"action": "use_tool", "tool_name": "...", "tool_arguments": {...}, "reasoning": "..."}
            {"action": "tool",     "tool": "...",      "arguments": {...},      "reasoning": "..."}
        Returns (tool_name, arguments, reasoning) or None if `raw` is not
        a tool-call request (i.e. it should be treated as a final answer).
        """
        if not isinstance(raw, dict):
            return None
        action = raw.get("action")
        if action not in ("use_tool", "tool"):
            return None

        tool_name = raw.get("tool_name")
        if not isinstance(tool_name, str):
            tool_name = raw.get("tool")
        if not isinstance(tool_name, str):
            return None

        arguments = raw.get("tool_arguments")
        if arguments is None:
            arguments = raw.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        reasoning = raw.get("reasoning")
        return tool_name, arguments, reasoning

    @staticmethod
    def _normalize_final_answer(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Accept the simplified `{"action": "final", "answer": "...", "confidence": ...}`
        shape as an alias for a plain final-answer object, folding
        "answer" into the common response schema's "result" field.
        """
        if raw.get("action") != "final":
            return raw
        normalized = dict(raw)
        normalized.pop("action", None)
        if "answer" in normalized and "result" not in normalized:
            normalized["result"] = normalized.pop("answer")
        return normalized

    def _recent_calls_all_denied(self, state: AgentTaskState) -> bool:
        """True if the run of consecutive failures that tripped the stop
        condition were all approval denials rather than genuine tool
        errors — used to report AgentStatus.NEEDS_INPUT instead of a
        generic failure, so the caller knows a human decision is what's
        actually blocking progress."""
        n = self.config.orchestration.max_consecutive_tool_failures
        if n <= 0 or not state.tools_used:
            return False
        recent = state.tools_used[-n:]
        return bool(recent) and all(r.denied for r in recent)

    # -- Tool validation & execution ------------------------------------------

    def _execute_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], request: AgentRequest, state: AgentTaskState, iteration: int
    ) -> Tuple[ToolInvocationRecord, str]:
        """
        Validate, execute (with a wall-clock timeout), and observe a
        single tool call. Returns (audit record, observation text to feed
        back to the model). Never raises — every failure mode becomes a
        ToolInvocationRecord + explanatory observation so the model (and
        ultimately the caller) can see exactly what happened.

        Validation order, per the "tool validation" requirement:
          1. Tool exists (registered / known to this agent).
          2. Arguments are a well-formed mapping (already coerced above).
          3. Destructive/high-risk tools require explicit request-level
             approval (`AgentRequest.approved_actions`).
          4. Path/command-level safety is enforced inside the tool itself
             (sandboxed file paths, whitelisted terminal commands) — this
             loop does not duplicate that logic, it just surfaces the
             tool's own rejection cleanly if it occurs.
        """
        tool = self.tools.get(tool_name)
        if tool is None:
            record = ToolInvocationRecord(
                tool_name=tool_name, arguments=arguments, success=False,
                summary="Tool not available to this agent", iteration=iteration, denied=True,
            )
            available = ", ".join(self.tools.keys()) or "(none)"
            self._log_tool_call(tool_name, iteration, success=False, denied=True, duration_ms=0.0)
            return record, f"Tool '{tool_name}' is not available to you. Available tools: {available}"

        if getattr(tool, "requires_approval", False) and tool_name not in request.approved_actions:
            record = ToolInvocationRecord(
                tool_name=tool_name, arguments=arguments, success=False,
                summary="Requires explicit user approval", iteration=iteration, denied=True,
                operation_type=getattr(tool, "operation_type", None),
            )
            state.record_assumption(
                f"Tool '{tool_name}' was requested but not approved for this request; it was not executed."
            )
            self._log_tool_call(tool_name, iteration, success=False, denied=True, duration_ms=0.0)
            return record, (
                f"Tool '{tool_name}' requires explicit approval and was NOT executed (this request did "
                f"not include '{tool_name}' in approved_actions). Do not repeat this exact request — "
                "either proceed without it, or clearly state in your final answer that user approval is "
                "required to complete this action."
            )

        call_start = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(tool.safe_run, **arguments)
                result: ToolResult = future.result(timeout=self.config.tools.tool_call_timeout_seconds)
        except FutureTimeoutError:
            duration_ms = (time.monotonic() - call_start) * 1000
            record = ToolInvocationRecord(
                tool_name=tool_name, arguments=arguments, success=False,
                summary=f"Timed out after {self.config.tools.tool_call_timeout_seconds}s",
                iteration=iteration, duration_ms=duration_ms,
                operation_type=getattr(tool, "operation_type", None),
            )
            state.record_error(f"Tool '{tool_name}' timed out")
            self._log_tool_call(tool_name, iteration, success=False, denied=False, duration_ms=duration_ms)
            return record, f"Tool '{tool_name}' timed out after {self.config.tools.tool_call_timeout_seconds}s."
        except TypeError as exc:
            # The model passed arguments that don't match the tool's signature.
            duration_ms = (time.monotonic() - call_start) * 1000
            record = ToolInvocationRecord(
                tool_name=tool_name, arguments=arguments, success=False,
                summary=f"Invalid arguments: {exc}", iteration=iteration, duration_ms=duration_ms,
                operation_type=getattr(tool, "operation_type", None),
            )
            self._log_tool_call(tool_name, iteration, success=False, denied=False, duration_ms=duration_ms)
            return record, f"Tool '{tool_name}' rejected the arguments given: {exc}"

        duration_ms = (time.monotonic() - call_start) * 1000
        record = ToolInvocationRecord(
            tool_name=tool_name, arguments=arguments, success=result.success,
            summary=result.summary or result.error, iteration=iteration, duration_ms=duration_ms,
            operation_type=getattr(tool, "operation_type", None),
        )
        self._log_tool_call(tool_name, iteration, success=result.success, denied=False, duration_ms=duration_ms)

        if result.success:
            if result.summary:
                state.record_finding(f"{tool_name}: {result.summary}")
            return record, self._format_tool_observation(result)

        state.record_error(f"Tool '{tool_name}' failed: {result.error}")
        return record, f"Tool '{tool_name}' failed: {result.error or 'unknown error'}"

    @staticmethod
    def _format_tool_observation(result: ToolResult, max_chars: int = 4000) -> str:
        """Render a tool's data payload as bounded text safe to feed back to the LLM."""
        if isinstance(result.data, str):
            text = result.data
        else:
            try:
                text = json.dumps(result.data, default=str)
            except (TypeError, ValueError):
                text = str(result.data)
        if len(text) > max_chars:
            text = text[:max_chars] + f"... [truncated, {len(text) - max_chars} more characters]"
        return text

    def _log_tool_call(self, tool_name: str, iteration: int, success: bool, denied: bool, duration_ms: float) -> None:
        # Metadata only — never logs tool arguments/data, which may contain
        # source code or other sensitive content.
        logger.info(
            "[%s] tool_call | iteration=%s | tool=%s | success=%s | denied=%s | duration_ms=%.1f",
            self.agent_name, iteration, tool_name, success, denied, duration_ms,
        )
