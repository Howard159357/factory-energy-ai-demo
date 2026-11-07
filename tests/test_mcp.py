import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import anyio
from mcp.client import Client

from factory_energy.mcp_server.server import build_server
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext

S2 = {"start": "2025-06-16T06:00", "end": "2025-06-16T11:00"}


def session(ctx: ToolContext, env: dict[str, str], body: Callable[[Client], Awaitable[Any]]) -> Any:
    async def main() -> Any:
        async with Client(build_server(build_registry(), ctx, env)) as client:
            return await body(client)

    return anyio.run(main)


def test_server_lists_read_tools_with_schemas_and_hints(ctx: ToolContext) -> None:
    async def body(client: Client) -> Any:
        return (await client.list_tools()).tools

    tools = {t.name: t for t in session(ctx, {}, body)}
    assert len(tools) == 11 and "generate_report" not in tools
    demand = tools["get_demand"]
    assert demand.input_schema["required"] == ["start", "end"]
    assert demand.annotations is not None and demand.annotations.read_only_hint is True


def test_tools_return_structured_results_and_errors(ctx: ToolContext) -> None:
    async def body(client: Client) -> Any:
        ok = await client.call_tool("get_demand", S2)
        bad = await client.call_tool("get_demand", {"start": "2025-06-16"})
        hidden = await client.call_tool("generate_report", {"title": "abc",
                                                            "body_markdown": "0123456789"})
        return ok, bad, hidden

    ok, bad, hidden = session(ctx, {}, body)
    assert not ok.is_error and ok.structured_content["peak_kw"] > 1300
    assert json.loads(ok.content[0].text)["intervals_over_contract"] == 2
    assert bad.is_error and "Field required" in bad.content[0].text
    assert hidden.is_error and "not available" in hidden.content[0].text


def test_allow_list_and_write_permission(ctx: ToolContext) -> None:
    async def names(client: Client) -> Any:
        return sorted(t.name for t in (await client.list_tools()).tools)

    narrow = session(ctx, {"MCP_TOOLS": "get_demand, search_knowledge"}, names)
    assert narrow == ["get_demand", "search_knowledge"]
    writer = session(replace(ctx, allow_write=True), {}, names)
    assert "generate_report" in writer and len(writer) == 12
