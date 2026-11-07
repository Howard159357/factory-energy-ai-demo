"""CLI wiring for the agent and the MCP server (kept out of __main__ to keep it small)."""

from __future__ import annotations

import argparse
import os
import sys

from factory_energy.agent.loop import Agent, Step
from factory_energy.agent.trace import log_dir, setup_tracing, write_jsonl
from factory_energy.llm import LLMSettings, make_client
from factory_energy.rag.embed import embedder_from
from factory_energy.rag.settings import RagSettings
from factory_energy.rag.store import KnowledgeStore, open_client
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext


def tool_context() -> ToolContext:
    settings = RagSettings.from_env()

    def knowledge() -> KnowledgeStore:
        return KnowledgeStore(open_client(settings), embedder_from(settings), settings.collection)

    return ToolContext.from_env(knowledge=knowledge)


def add_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    agent = commands.add_parser("agent", help="ask the energy agent a question")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    ask = agent_commands.add_parser("ask", help="run one question through the agent")
    ask.add_argument("question")
    ask.add_argument("--trace", action="store_true", help="print every model and tool step")
    ask.add_argument("--max-steps", type=int, default=int(os.environ.get("AGENT_MAX_STEPS", "8")))
    mcp = commands.add_parser("mcp", help="Model Context Protocol server")
    mcp_commands = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_commands.add_parser("serve", help="serve the plant tools over stdio")
    mcp_commands.add_parser("tools", help="list the tools the server exposes")
    api = commands.add_parser("api", help="HTTP service: /ask, /health, /ready, /metrics, /mcp")
    api_commands = api.add_subparsers(dest="api_command", required=True)
    serve = api_commands.add_parser("serve", help="run the service with uvicorn")
    serve.add_argument("--host", default=os.environ.get("API_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8000")))


def run(args: argparse.Namespace) -> int:
    if args.command == "agent":
        return _ask(args)
    if args.command == "api":
        from factory_energy.api.app import serve

        serve(args.host, args.port)
        return 0
    return _mcp(args)


def _ask(args: argparse.Namespace) -> int:
    setup_tracing()
    try:
        llm = make_client(LLMSettings.from_env())
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    ctx = tool_context()
    live = _print_step if args.trace else None
    agent = Agent(llm, build_registry(), ctx, max_steps=args.max_steps,
                  max_input_chars=int(os.environ.get("AGENT_MAX_INPUT_CHARS", "4000")),
                  max_tool_calls=int(os.environ.get("AGENT_MAX_TOOL_CALLS", "16")),
                  output_guard=os.environ.get("AGENT_OUTPUT_GUARD", "1") != "0",
                  on_step=live)
    result = agent.run(args.question)
    path = write_jsonl(result, log_dir())
    if args.trace:
        print()
    print(result.answer)
    print(f"\n-- {result.model} | {len(result.steps)} steps | tools: "
          f"{', '.join(result.tools_called) or 'none'} | {result.latency_s:.1f} s "
          f"(model {result.llm_s:.1f} s, tools {result.tool_s:.1f} s) | tokens "
          f"{result.prompt_tokens} in / {result.completion_tokens} out | {result.stop_reason}")
    if result.security_events:
        kinds = ", ".join(f"{e['layer']}:{e['kind']}" for e in result.security_events)
        print(f"-- security events: {kinds}")
    if result.citations_invalid:
        print(f"-- removed unverified citations: {', '.join(result.citations_invalid)}")
    print(f"-- log: {path}")
    ctx.close()
    return 0 if result.stop_reason == "answer" else 1


def _print_step(step: Step) -> None:
    """One line per finished step, printed as it happens."""
    mark = "ok" if step.ok else f"ERROR {step.error}"
    if step.kind == "llm":
        print(f"[{step.offset_s:6.2f}s] model {step.name}  {step.duration_s:.2f}s  "
              f"{step.prompt_tokens}/{step.completion_tokens} tokens  {mark}", flush=True)
        plan = step.content.strip()
        if plan and step.offset_s < 0.5:  # the first turn's text is the plan
            for line in plan.splitlines():
                print(f"         {line}", flush=True)
    else:
        print(f"[{step.offset_s:6.2f}s]   tool {step.name}({_short(step.arguments)})  "
              f"{step.duration_s:.2f}s  {step.result_chars} chars  {mark}", flush=True)


def _short(arguments: dict[str, object]) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    return text if len(text) <= 90 else text[:87] + "..."


def _mcp(args: argparse.Namespace) -> int:
    import anyio

    from factory_energy.mcp_server.server import allowed_tools, build_server, serve_stdio

    registry, ctx = build_registry(), tool_context()
    if args.mcp_command == "tools":
        for tool in allowed_tools(registry, ctx):
            print(f"{tool.name:<24} {tool.permission:<5} {tool.description[:80]}")
        return 0
    anyio.run(serve_stdio, build_server(registry, ctx))  # stdout belongs to the protocol
    return 0
