"""Tool registry: schemas for the model, permission checks and validated execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from factory_energy.tools.context import ToolContext, apply_cutoff

Permission = Literal["read", "write"]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    permission: Permission
    run: Callable[[ToolContext, Any], dict[str, Any]]

    def input_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        schema.setdefault("properties", {})
        schema["additionalProperties"] = False
        return schema

    def openai_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.input_schema(),
        }}


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    content: dict[str, Any]
    error: str = ""


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        names = [tool.name for tool in tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tool name")
        self.tools = {tool.name: tool for tool in tools}

    def available(self, allow_write: bool) -> list[Tool]:
        """The manifest: write tools only when writing is allowed."""
        return [t for t in self.tools.values() if allow_write or t.permission == "read"]

    def openai_tools(self, allow_write: bool) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self.available(allow_write)]

    def permissions(self) -> dict[str, Permission]:
        return {name: tool.permission for name, tool in self.tools.items()}

    def call(self, ctx: ToolContext, name: str, arguments: dict[str, Any] | None) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(name, False, {}, f"unknown tool {name!r}")
        if tool.permission == "write" and not ctx.allow_write:
            return ToolResult(name, False, {}, f"tool {name!r} writes and is disabled; "
                                               "set AGENT_ALLOW_WRITE=1 to enable it")
        try:
            args = tool.input_model.model_validate(arguments or {})
        except ValidationError as error:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                for e in error.errors()
            )
            return ToolResult(name, False, {}, f"invalid arguments: {problems}")
        try:
            return ToolResult(name, True, tool.run(ctx, apply_cutoff(ctx, args)))
        except (ValueError, KeyError, LookupError, FileNotFoundError, RuntimeError) as error:
            return ToolResult(name, False, {}, f"{type(error).__name__}: {error}")


def build_registry() -> ToolRegistry:
    from factory_energy.tools import anomaly, forecast, knowledge, plant, report

    return ToolRegistry([*knowledge.TOOLS, *plant.TOOLS, *anomaly.TOOLS, *forecast.TOOLS,
                         *report.TOOLS])
