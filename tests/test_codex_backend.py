"""The temporary Codex CLI backend, driven by a stand-in runner (no Codex, no network)."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from factory_energy.llm import LLMError, LLMSettings, make_client
from factory_energy.llm.codex_cli import CodexCLIClient, render
from factory_energy.tools import build_registry
from factory_energy.tools.context import Window

TOOLS = build_registry().openai_tools(allow_write=False)
MESSAGES = [
    {"role": "system", "content": "Be an energy assistant."},
    {"role": "user", "content": "Peak on 16 June?"},
    {"role": "assistant", "content": "1. Get demand.", "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "get_demand", "arguments": '{"start": "a", "end": "b"}'}}]},
    {"role": "tool", "tool_call_id": "c1", "content": '{"peak_kw": 1324.4}'},
]


def runner(reply: dict | None, code: int = 0):  # type: ignore[no-untyped-def]
    seen: dict[str, object] = {}

    def run(command: list[str], prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, prompt=prompt)
        if reply is not None:
            Path(command[command.index("-o") + 1]).write_text(json.dumps(reply), encoding="utf-8")
        usage = {"type": "turn.completed", "usage": {"input_tokens": 1200, "output_tokens": 30,
                                                     "reasoning_output_tokens": 5}}
        return subprocess.CompletedProcess(command, code, json.dumps(usage) + "\n", "boom")

    return run, seen


def test_render_shows_the_catalogue_and_labels_results() -> None:
    prompt = render(MESSAGES, TOOLS)
    assert "## Action catalogue" in prompt and '"name": "get_demand"' in prompt
    assert '(requested actions: get_demand({"start": "a", "end": "b"}))' in prompt
    assert '[action result: get_demand]\n{"peak_kw": 1324.4}' in prompt
    assert prompt.rstrip().endswith("Return the agent's next turn as JSON.")


def test_client_maps_the_structured_reply_to_a_turn() -> None:
    run, seen = runner({"content": "Plan", "tool_calls": [
        {"name": "get_demand", "arguments_json": '{"start": "x", "end": "y"}'}]})
    client = CodexCLIClient("gpt-6-luna", "low", runner=run)
    turn = client.complete(MESSAGES[:2], TOOLS)
    assert [c.name for c in turn.tool_calls] == ["get_demand"]
    assert turn.tool_calls[0].id == "call_0_0" and turn.content == "Plan"
    assert (turn.prompt_tokens, turn.completion_tokens) == (1200, 35)
    command = seen["command"]
    assert isinstance(command, list)
    assert {"--output-schema", "--ignore-user-config", "read-only"} <= set(command)
    assert "model_reasoning_effort=low" in command and client.name == "codex_cli:gpt-6-luna@low"


def test_failures_raise_llm_errors() -> None:
    with pytest.raises(LLMError, match="exited 1"):
        CodexCLIClient(runner=runner(None, code=1)[0]).complete(MESSAGES, TOOLS)


def test_factory_builds_the_codex_backend() -> None:
    client = make_client(LLMSettings.from_env({"LLM_PROVIDER": "codex_cli",
                                               "CODEX_EFFORT": "medium"}))
    assert client.name == "codex_cli:gpt-6-luna@medium"


def test_aware_times_are_converted_to_plant_time() -> None:
    window = Window.model_validate({"start": "2025-06-16T08:00:00+08:00",
                                    "end": "2025-06-16T02:00:00Z"})
    assert window.start == datetime(2025, 6, 16, 8, 0)
    assert window.end == datetime(2025, 6, 16, 10, 0) and window.end.tzinfo is None


def test_close_removes_the_temp_dir_and_is_idempotent() -> None:
    client = CodexCLIClient()
    assert client.workdir.exists()
    client.close()
    assert not client.workdir.exists()
    client.close()
