"""Any OpenAI-compatible chat server: vLLM (default), llama.cpp llama-server, Strata, ..."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from factory_energy.llm.base import LLMError, LLMTurn, Message, ToolCall


def _shutdown_sockets(client: Any) -> int:
    """Best effort: shut down the sockets of the SDK's connection pool so a blocked read ends and
    the server sees the disconnect; returns how many were shut down. Reaches into httpx/httpcore
    internals, so any surprise in their shape is ignored (a test checks the count);
    ``complete`` stops waiting regardless."""
    try:
        pool = client._client._transport._pool  # openai -> httpx.Client -> transport -> pool
        connections = list(pool.connections)
    except Exception:  # noqa: BLE001
        return 0
    shut = 0
    for connection in connections:
        try:
            stream = connection._connection._network_stream
            stream._sock.shutdown(socket.SHUT_RDWR)
            shut += 1
        except Exception:  # noqa: BLE001, S112 - a connection already gone needs nothing
            continue
    return shut


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        extra_body: dict[str, Any] | None = None,
        max_retries: int = 1,
    ) -> None:
        if not base_url or not model:
            raise ValueError("LLM_BASE_URL and LLM_MODEL are required for openai_compatible")
        from openai import OpenAI

        # Local servers usually ignore the key; the SDK still needs a non-empty string.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=timeout,
                              max_retries=max_retries)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_body = extra_body or {}
        self._cancelled = threading.Event()

    @property
    def name(self) -> str:
        return f"openai_compatible:{self.model}"

    def cancel(self) -> None:
        """Stop the request in flight. ``complete`` stops waiting at once (the call runs in a
        helper thread); the open sockets are shut down so the server sees the client go away
        (vLLM then aborts the generation). Closing alone is not enough on Linux: a read blocked
        in another thread is not woken by close(). This client is not reused after."""
        self._cancelled.set()
        _shutdown_sockets(self._client)
        self._client.close()

    def close(self) -> None:
        """Release the SDK client's connections; safe to call more than once."""
        self._client.close()

    def _create(self, messages: list[Message], tools: list[dict[str, Any]]) -> Any:
        import openai

        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools or openai.omit,  # type: ignore[arg-type]
            tool_choice="auto" if tools else openai.omit,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            extra_body=self.extra_body or None,
        )

    def _create_cancellable(self, messages: list[Message], tools: list[dict[str, Any]]) -> Any:
        """Run the request in a helper thread and return as soon as it ends or is cancelled."""
        outcome: dict[str, Any] = {}
        finished = threading.Event()

        def work() -> None:
            try:
                outcome["response"] = self._create(messages, tools)
            except BaseException as error:  # noqa: BLE001 - handed back to the caller
                outcome["error"] = error
            finally:
                finished.set()

        threading.Thread(target=work, daemon=True, name="llm-request").start()
        while not finished.wait(0.1):
            if self._cancelled.is_set():
                raise LLMError("cancelled by the user")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["response"]

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMTurn:
        import openai
        from openai.types.chat import ChatCompletionMessageFunctionToolCall

        if self._cancelled.is_set():
            raise LLMError("cancelled by the user")
        began = time.perf_counter()
        try:
            response = self._create_cancellable(messages, tools)
        except LLMError:
            raise
        except Exception as error:  # noqa: BLE001 - a closed connection is not always APIError
            if self._cancelled.is_set():
                raise LLMError("cancelled by the user") from error
            if isinstance(error, openai.APIError):
                raise LLMError(f"{type(error).__name__}: {error}") from error
            raise
        latency = time.perf_counter() - began
        if not response.choices:
            raise LLMError("the server returned no choices")
        choice = response.choices[0]
        message = choice.message
        calls = [
            ToolCall(call.id or f"call_{index}", call.function.name,
                     call.function.arguments or "{}")
            for index, call in enumerate(message.tool_calls or [])
            if isinstance(call, ChatCompletionMessageFunctionToolCall)
        ]
        extra = message.model_extra or {}
        reasoning = extra.get("reasoning_content") or extra.get("reasoning") or ""
        usage = response.usage
        return LLMTurn(
            content=message.content or "",
            tool_calls=calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_s=latency,
            model=response.model or self.model,
            finish_reason=choice.finish_reason or "",
            reasoning=str(reasoning),
        )
