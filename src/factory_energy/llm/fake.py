"""A deterministic backend for tests and CI: no network, no model.

With a script it replays the given turns in order. Without one it behaves like a minimal
planner: search the knowledge base for the question, then answer from the best passage and cite
it. That is enough to exercise the whole loop (tool call, tool result, citation check).
"""

from __future__ import annotations

import json
from typing import Any

from factory_energy.llm.base import LLMTurn, Message, ToolCall


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


class FakeClient:
    def __init__(self, script: list[LLMTurn] | None = None) -> None:
        self.script = list(script) if script is not None else None
        self.calls: list[list[Message]] = []

    @property
    def name(self) -> str:
        return "fake:scripted" if self.script is not None else "fake:planner"

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMTurn:
        self.calls.append([dict(m) for m in messages])
        prompt = _tokens(json.dumps(messages)) + _tokens(json.dumps(tools))
        if self.script is not None:
            if not self.script:
                return LLMTurn("I have nothing more to add.", prompt_tokens=prompt,
                               completion_tokens=6, model=self.name, finish_reason="stop")
            turn = self.script.pop(0)
            return LLMTurn(turn.content, turn.tool_calls, prompt, _tokens(turn.content) + 8,
                           0.0, self.name, "tool_calls" if turn.tool_calls else "stop")
        return self._plan(messages, prompt)

    def _plan(self, messages: list[Message], prompt: int) -> LLMTurn:
        question = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            call = ToolCall("call_0", "search_knowledge",
                            json.dumps({"query": str(question)[:300], "k": 3}))
            return LLMTurn("Plan: 1. Search the plant documents. 2. Answer with a citation.",
                           [call], prompt, 30, 0.0, self.name, "tool_calls")
        try:
            passages = json.loads(results[-1]["content"]).get("passages", [])
        except (json.JSONDecodeError, AttributeError):
            passages = []
        if not passages:
            text = "I could not find this in the plant documents."
        else:
            best = passages[0]
            body = " ".join(str(best["text"]).split("\n\n", 1)[-1].split())
            sentence = body.split(". ")[0].rstrip(".")
            text = f"{sentence}. [source: {best['citation']}]"
        return LLMTurn(text, [], prompt, _tokens(text), 0.0, self.name, "stop")
