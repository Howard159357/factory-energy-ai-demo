"""The agent loop: plan, call tools until the model answers, check the citations.

Hand-written on purpose (about 250 lines): every model call and tool call is visible, timed,
traced and permission-checked in code this project owns.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from opentelemetry.trace import Status, StatusCode

from factory_energy.agent import citations
from factory_energy.agent.guardrails import ToolBudget, guard_output
from factory_energy.agent.prompts import PROTECTED_PROMPT, SYSTEM_PROMPT
from factory_energy.agent.trace import tracer
from factory_energy.agent.working import strip_working
from factory_energy.llm.base import LLMClient, LLMError, Message, ToolCall
from factory_energy.tools.context import ToolContext
from factory_energy.tools.registry import ToolRegistry, ToolResult

MAX_TOOL_CHARS = 6000  # a tool result longer than this is truncated before the model sees it


@dataclass
class Step:
    kind: str  # "llm" or "tool"
    name: str
    offset_s: float  # start, seconds after the run began
    duration_s: float
    ok: bool = True
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    arguments: dict[str, Any] = field(default_factory=dict)
    result_chars: int = 0
    content: str = ""


@dataclass
class AgentResult:
    question: str
    answer: str
    plan: str
    model: str
    run_id: str
    started: datetime
    stop_reason: str  # "answer", "max_steps", "llm_error", "rejected_input", "stopped"
    steps: list[Step] = field(default_factory=list)
    citations_valid: list[str] = field(default_factory=list)
    citations_invalid: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    security_events: list[dict[str, str]] = field(default_factory=list)
    citations_repaired: list[str] = field(default_factory=list)  # near-misses resolved

    @property
    def llm_s(self) -> float:
        return sum(s.duration_s for s in self.steps if s.kind == "llm")

    @property
    def tool_s(self) -> float:
        return sum(s.duration_s for s in self.steps if s.kind == "tool")


class Agent:
    def __init__(self, llm: LLMClient, registry: ToolRegistry, ctx: ToolContext,
                 max_steps: int = 8, max_input_chars: int = 4000, max_tool_calls: int = 16,
                 output_guard: bool = True,
                 on_step: Callable[[Step], None] | None = None,
                 should_stop: Callable[[], bool] | None = None) -> None:
        self.llm = llm
        self.should_stop = should_stop  # checked before each model call and tool call
        self.max_tool_calls = max_tool_calls
        self.output_guard = output_guard
        self.on_step = on_step  # called as each step finishes (live traces, demos)
        self.registry = registry
        self.ctx = ctx
        self.max_steps = max_steps
        self.max_input_chars = max_input_chars

    def run(self, question: str, now: datetime | None = None, note: str = "",
            history: Sequence[tuple[str, str]] = ()) -> AgentResult:
        """Answer one question. ``now`` (for example a replay clock) is told to the model; the
        tools enforce it separately through ``ToolContext.as_of``. ``note`` is extra context
        for the system prompt, such as the dashboard page the user is looking at.
        ``history`` holds earlier (question, answer) turns of the same conversation, oldest
        first, so a follow-up such as "and in July?" can be understood."""
        began = time.perf_counter()
        result = AgentResult(question, "", "", self.llm.name, uuid.uuid4().hex, datetime.now(),
                             "answer")
        with tracer().start_as_current_span("invoke_agent energy-agent") as span:
            span.set_attribute("gen_ai.operation.name", "invoke_agent")
            span.set_attribute("gen_ai.request.model", self.llm.name)
            if span.get_span_context().is_valid:
                result.run_id = format(span.get_span_context().trace_id, "032x")
            if not question.strip() or len(question) > self.max_input_chars:
                result.stop_reason = "rejected_input"
                result.answer = (f"Please ask a question of 1 to {self.max_input_chars} "
                                 "characters.")
            else:
                self._loop(question, result, began, now, note, history)
            span.set_attribute("agent.stop_reason", result.stop_reason)
            span.set_attribute("agent.security_events", len(result.security_events))
            span.set_attribute("gen_ai.usage.input_tokens", result.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", result.completion_tokens)
        result.latency_s = time.perf_counter() - began
        return result

    def _loop(self, question: str, result: AgentResult, began: float,
              now: datetime | None = None, note: str = "",
              history: Sequence[tuple[str, str]] = ()) -> None:
        tools = self.registry.openai_tools(self.ctx.allow_write)
        system = SYSTEM_PROMPT
        if now is not None:
            system += (f"\n\nThe current time at the plant is {now:%Y-%m-%d %H:%M}. Treat it as "
                       "now: data after this moment does not exist yet, and the tools will not "
                       "return it.")
        if note:
            system += f"\n\n{note}"
        if history:
            system += ("\n\nThe earlier turns of this conversation are included so that "
                       "follow-up questions make sense. Get every number for the new question "
                       "from a tool again, and cite only what you retrieve now.")
        messages: list[Message] = [{"role": "system", "content": system}]
        for asked, answered in history:
            messages += [{"role": "user", "content": asked},
                         {"role": "assistant", "content": answered}]
        messages.append({"role": "user", "content": question})
        retrieved: set[str] = set()
        tools_ok: set[str] = set()
        budget = ToolBudget(max_calls=self.max_tool_calls)
        for _ in range(self.max_steps):
            if self._stopped(result):
                return
            turn_started = time.perf_counter()
            with tracer().start_as_current_span(f"chat {self.llm.name}") as span:
                span.set_attribute("gen_ai.operation.name", "chat")
                try:
                    turn = self.llm.complete(messages, tools)
                except LLMError as error:
                    span.set_status(Status(StatusCode.ERROR, str(error)))
                    self._record(result, Step("llm", self.llm.name, turn_started - began,
                                             time.perf_counter() - turn_started, False, str(error)))
                    if self._stopped(result):  # the call was cancelled because of a stop
                        return
                    result.stop_reason, result.answer = "llm_error", f"Model error: {error}"
                    return
                span.set_attribute("gen_ai.response.model", turn.model)
                span.set_attribute("gen_ai.usage.input_tokens", turn.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", turn.completion_tokens)
            result.prompt_tokens += turn.prompt_tokens
            result.completion_tokens += turn.completion_tokens
            self._record(result, Step("llm", turn.model or self.llm.name, turn_started - began,
                                     time.perf_counter() - turn_started,
                                     prompt_tokens=turn.prompt_tokens,
                                     completion_tokens=turn.completion_tokens,
                                     content=turn.content[:2000]))
            if turn.content.strip() and not result.plan and turn.tool_calls:
                result.plan = turn.content.strip()
            if not turn.tool_calls:
                report = citations.check(strip_working(turn.content), retrieved, tools_ok)
                result.answer = report.answer
                result.citations_valid, result.citations_invalid = report.valid, report.invalid
                result.citations_repaired = report.repaired
                if self.output_guard:
                    result.answer, findings = guard_output(result.answer, PROTECTED_PROMPT)
                    result.security_events += [
                        {"layer": f.layer, "kind": f.kind, "detail": f.detail} for f in findings]
                return
            messages.append(turn.as_message())
            for call in turn.tool_calls:
                if self._stopped(result):
                    return
                refusal = budget.check(call.name, call.arguments)
                if refusal:
                    tool_result = ToolResult(call.name, False, {}, refusal)
                    result.security_events.append(
                        {"layer": "tool_budget", "kind": "refused", "detail": refusal})
                    self._record(result, Step("tool", call.name, time.perf_counter() - began, 0.0,
                                             False, refusal))
                else:
                    tool_result = self._call_tool(call, result, began)
                if tool_result.ok:
                    tools_ok.add(call.name)
                    if call.name == "search_knowledge":
                        retrieved.update(p["citation"] for p in tool_result.content["passages"])
                        result.security_events += [
                            {"layer": "quarantine", "kind": ",".join(p["security_flags"]),
                             "detail": p["citation"]}
                            for p in tool_result.content["passages"] if p.get("security_flags")]
                payload = (json.dumps(tool_result.content, ensure_ascii=False, default=str)
                           if tool_result.ok else json.dumps({"error": tool_result.error}))
                if len(payload) > MAX_TOOL_CHARS:
                    payload = payload[:MAX_TOOL_CHARS] + " ... [truncated]"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})
        result.stop_reason = "max_steps"
        result.answer = (f"I stopped after {self.max_steps} model calls without a final answer. "
                         "Try a narrower question.")

    def _stopped(self, result: AgentResult) -> bool:
        if self.should_stop is None or not self.should_stop():
            return False
        result.stop_reason, result.answer = "stopped", "Stopped before a final answer."
        return True

    def _record(self, result: AgentResult, step: Step) -> None:
        result.steps.append(step)
        if self.on_step is not None:
            self.on_step(step)

    def _call_tool(self, call: ToolCall, result: AgentResult, began: float) -> ToolResult:
        started = time.perf_counter()
        result.tools_called.append(call.name)
        with tracer().start_as_current_span(f"execute_tool {call.name}") as span:
            span.set_attribute("gen_ai.operation.name", "execute_tool")
            span.set_attribute("gen_ai.tool.name", call.name)
            span.set_attribute("gen_ai.tool.call.id", call.id)
            try:
                arguments = json.loads(call.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as error:
                tool_result = ToolResult(call.name, False, {}, f"arguments are not valid JSON "
                                                               f"object: {error}")
                arguments = {"raw": call.arguments[:500]}
            else:
                tool_result = self.registry.call(self.ctx, call.name, arguments)
            size = len(json.dumps(tool_result.content, default=str))
            span.set_attribute("tool.result_chars", size)
            if not tool_result.ok:
                span.set_status(Status(StatusCode.ERROR, tool_result.error))
        self._record(result, Step("tool", call.name, started - began,
                                 time.perf_counter() - started, tool_result.ok, tool_result.error,
                                 arguments=arguments, result_chars=size))
        return tool_result
