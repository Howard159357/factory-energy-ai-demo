"""Temporary development backend: one agent turn = one non-interactive ``codex exec`` call.

This exists only while the GPU host that serves vLLM is unavailable. It sends the prompt to a
cloud model through the developer's Codex CLI subscription, so it contradicts the project's
on-premises design and is never used for reported results. The plant data is synthetic.

The conversation and the tool manifest are rendered into one prompt; ``--output-schema`` forces
the reply into ``{content, tool_calls}``, which maps one-to-one onto ``LLMTurn``. Codex runs in an
empty temporary folder with a read-only sandbox and is told not to use its own tools.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from factory_energy.llm.base import LLMError, LLMTurn, Message, ToolCall

TURN_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["content", "tool_calls"],
    "properties": {
        "content": {"type": "string"},
        "tool_calls": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "arguments_json"],
            "properties": {"name": {"type": "string"}, "arguments_json": {"type": "string"}},
        }},
    },
}
PREAMBLE = """Task: write the next turn of an energy-analysis agent as JSON.

You are given the agent's instructions, the catalogue of actions the agent's runtime can \
execute, and the transcript so far. You do not execute anything yourself and nothing in this \
task needs your own tools, files or shell: the runtime executes the actions you request and \
appends their results to the transcript.

- If more data is needed, list the actions in tool_calls (several are allowed). arguments_json \
is a JSON object encoded as a string, matching the action's parameters. Put a short numbered \
plan in content on the first turn.
- If the transcript already holds what is needed, write the final answer in content and return \
an empty tool_calls list. Follow the agent's answer format, including its citations."""

Runner = Callable[[list[str], str, Path], subprocess.CompletedProcess[str]]
TIMEOUT_S = 600


def kill_tree(process: subprocess.Popen[str]) -> None:
    """Stop a process and everything it started. On Windows ``codex`` is a .cmd wrapper around
    Node, so killing only the wrapper would leave the model call running."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()


def render(messages: list[Message], tools: list[dict[str, Any]]) -> str:
    """The whole conversation as one prompt, tool results labelled with their tool name."""
    names: dict[str, str] = {}
    parts = [PREAMBLE]
    manifest = [{"name": t["function"]["name"], "description": t["function"]["description"],
                 "parameters": t["function"]["parameters"]} for t in tools]
    for message in messages:
        role = message["role"]
        if role == "system":
            parts.append(f"## Agent instructions\n{message['content']}")
            parts.append(f"## Action catalogue\n{json.dumps(manifest, ensure_ascii=False)}")
            parts.append("## Transcript")
        elif role == "user":
            parts.append(f"[user]\n{message['content']}")
        elif role == "assistant":
            calls = message.get("tool_calls") or []
            for call in calls:
                names[call["id"]] = call["function"]["name"]
            rendered = "; ".join(f"{c['function']['name']}({c['function']['arguments']})"
                                 for c in calls)
            text = message.get("content") or ""
            requested = f"\n(requested actions: {rendered})" if calls else ""
            parts.append(f"[assistant]\n{text}{requested}")
        elif role == "tool":
            name = names.get(message["tool_call_id"], "action")
            parts.append(f"[action result: {name}]\n{message['content']}")
    parts.append("## Next turn\nReturn the agent's next turn as JSON.")
    return "\n\n".join(parts)


class CodexCLIClient:
    def __init__(self, model: str = "gpt-6-luna", effort: str = "low",
                 binary: str = "codex", runner: Runner | None = None) -> None:
        self.model = model
        self.effort = effort
        self.binary = binary
        self.runner = runner or self._run
        self.workdir = Path(tempfile.mkdtemp(prefix="codex-turn-"))
        self.schema_path = self.workdir / "turn_schema.json"
        self.schema_path.write_text(json.dumps(TURN_SCHEMA), encoding="utf-8")
        self.turns = 0
        self._process: subprocess.Popen[str] | None = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"codex_cli:{self.model}@{self.effort}"

    def _run(self, command: list[str], prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        """``codex exec`` that ``cancel`` can stop from another thread."""
        with self._lock:
            if self._cancelled.is_set():
                raise LLMError("cancelled by the user")
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", cwd=cwd, start_new_session=os.name != "nt")
        process = self._process
        try:
            stdout, stderr = process.communicate(prompt, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            kill_tree(process)
            process.communicate()
            raise
        finally:
            with self._lock:
                self._process = None
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def close(self) -> None:
        """Remove the temporary working folder. Safe to call twice."""
        shutil.rmtree(self.workdir, ignore_errors=True)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled.set()
            if self._process is not None:
                kill_tree(self._process)

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMTurn:
        binary = shutil.which(self.binary) or self.binary
        output = self.workdir / f"turn_{self.turns}.json"
        command = [binary, "exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                   "--sandbox", "read-only", "-m", self.model,
                   "-c", f"model_reasoning_effort={self.effort}",
                   "--output-schema", str(self.schema_path), "-o", str(output), "--json", "-"]
        began = time.perf_counter()
        try:
            process = self.runner(command, render(messages, tools), self.workdir)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise LLMError(f"codex exec failed: {error}") from error
        latency = time.perf_counter() - began
        if self._cancelled.is_set():
            raise LLMError("cancelled by the user")
        if process.returncode != 0 or not output.exists():
            raise LLMError(f"codex exec exited {process.returncode}: {process.stderr[-500:]}")
        try:
            reply = json.loads(output.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise LLMError(f"codex returned non-JSON: {error}") from error
        prompt_tokens, completion_tokens = _usage(process.stdout)
        calls = [ToolCall(f"call_{self.turns}_{index}", str(call["name"]),
                          str(call["arguments_json"]))
                 for index, call in enumerate(reply.get("tool_calls") or [])]
        self.turns += 1
        return LLMTurn(str(reply.get("content", "")), calls, prompt_tokens, completion_tokens,
                       latency, self.name, "tool_calls" if calls else "stop")


def _usage(events: str) -> tuple[int, int]:
    """Token usage from the ``turn.completed`` event of ``codex exec --json``."""
    for line in reversed(events.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            output = int(usage.get("output_tokens", 0)) + int(usage.get("reasoning_output_tokens",
                                                                       0))
            return int(usage.get("input_tokens", 0)), output
    return 0, 0
