"""The interface every backend implements: one model turn in, text and tool calls out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, Any]  # OpenAI chat format: role, content, tool_calls, tool_call_id


class LLMError(RuntimeError):
    """The backend could not produce a turn (connection, HTTP error, malformed reply)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text exactly as the model produced it


@dataclass(frozen=True)
class LLMTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    model: str = ""
    finish_reason: str = ""
    reasoning: str = ""  # reasoning text, when the server returns it separately

    def as_message(self) -> Message:
        message: Message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return message


class LLMClient(Protocol):
    @property
    def name(self) -> str: ...

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMTurn: ...


class Cancellable(Protocol):
    def cancel(self) -> None:
        """Abort the model call in progress, from another thread; ``complete`` then raises
        ``LLMError``. Backends that can stop the work on the server side implement it."""
        ...


def cancel(client: object) -> bool:
    """Cancel a client's call in progress if the backend supports it; True if it did."""
    method = getattr(client, "cancel", None)
    if callable(method):
        method()
        return True
    return False


def close(client: object) -> None:
    """Release a client's connections if the backend holds any (the others need nothing)."""
    method = getattr(client, "close", None)
    if callable(method):
        method()
