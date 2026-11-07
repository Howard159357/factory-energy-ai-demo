"""The plant tools over the Model Context Protocol.

Built on the SDK's low-level server so the tool schemas are exactly the registry's pydantic
schemas, and every call goes through the same validation and permission check as the agent.
Least privilege: the plant database is opened read-only, write-class tools are not listed and
are refused unless AGENT_ALLOW_WRITE=1, and an optional MCP_TOOLS allow-list narrows the set.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

import anyio
from mcp import types
from mcp.server.lowlevel import Server

from factory_energy import __version__
from factory_energy.tools.context import ToolContext
from factory_energy.tools.registry import Tool, ToolRegistry

INSTRUCTIONS = (
    "Tools for DemoTronics, a fictional electronics plant with synthetic 2025 meter data. "
    "Use get_plant_overview first for meter ids and incident dates; cite search_knowledge "
    "passages by their citation."
)


def allowed_tools(
    registry: ToolRegistry, ctx: ToolContext, env: Mapping[str, str] | None = None
) -> list[Tool]:
    values = os.environ if env is None else env
    names = {n.strip() for n in values.get("MCP_TOOLS", "").split(",") if n.strip()}
    tools = registry.available(ctx.allow_write)
    return [t for t in tools if not names or t.name in names]


def build_server(
    registry: ToolRegistry, ctx: ToolContext, env: Mapping[str, str] | None = None
) -> Server[Any]:
    exposed = {tool.name: tool for tool in allowed_tools(registry, ctx, env)}

    async def list_tools(
        context: Any, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(
                name=tool.name, description=tool.description, input_schema=tool.input_schema(),
                annotations=types.ToolAnnotations(
                    read_only_hint=tool.permission == "read",
                    destructive_hint=False,
                    open_world_hint=False,
                ),
            )
            for tool in exposed.values()
        ])

    async def call_tool(context: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        if params.name not in exposed:
            return _error(f"tool {params.name!r} is not available on this server")
        # Tools run blocking DuckDB and simulator code: keep the event loop free.
        result = await anyio.to_thread.run_sync(registry.call, ctx, params.name,
                                                dict(params.arguments or {}))
        if not result.ok:
            return _error(result.error)
        text = json.dumps(result.content, ensure_ascii=False, default=str)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)],
                                    structured_content=json.loads(text))

    return Server(
        "factory-energy",
        version=__version__,
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)],
                                is_error=True)


async def serve_stdio(server: Server[Any]) -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
