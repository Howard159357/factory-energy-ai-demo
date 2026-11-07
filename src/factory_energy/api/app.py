"""FastAPI service around the agent.

- ``GET /health``  liveness: the process answers.
- ``GET /ready``   readiness: the plant database and the knowledge base can be queried.
- ``GET /metrics`` Prometheus metrics (runs, latency, tool calls, tokens, guardrail events).
- ``GET /tools``   the tool manifest with read/write permissions.
- ``POST /ask``    one question through the agent.
- ``/mcp``         the plant tools over MCP (streamable HTTP), same registry and guardrails.

When ``API_KEY`` is set, /ask, /tools and /mcp need a matching ``X-API-Key`` header. Logs are
one JSON object per line.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from factory_energy import __version__
from factory_energy.agent.loop import Agent
from factory_energy.api.metrics import AgentMetrics
from factory_energy.llm import LLMClient, LLMSettings, make_client
from factory_energy.tools.context import ToolContext
from factory_energy.tools.registry import ToolRegistry

PROTECTED = ("/ask", "/tools", "/mcp")
log = logging.getLogger("factory_energy.api")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {"ts": self.formatTime(record), "level": record.levelname,
                                   "logger": record.name, "message": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("factory_energy")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class AskResponse(BaseModel):
    answer: str
    stop_reason: str
    run_id: str
    model: str
    tools_called: list[str]
    citations: list[str]
    citations_removed: list[str]
    security_events: list[dict[str, str]]
    latency_s: float
    prompt_tokens: int
    completion_tokens: int


@dataclass
class Service:
    ctx: ToolContext
    registry: ToolRegistry
    make_llm: Callable[[], LLMClient]
    metrics: AgentMetrics
    api_key: str
    max_steps: int
    max_tool_calls: int
    output_guard: bool


def create_app(ctx: ToolContext, registry: ToolRegistry,
               make_llm: Callable[[], LLMClient] | None = None,
               env: Mapping[str, str] | None = None) -> FastAPI:
    values = os.environ if env is None else env
    settings = LLMSettings.from_env(values)
    service = Service(
        ctx=ctx, registry=registry,
        make_llm=make_llm or (lambda: make_client(settings)),
        metrics=AgentMetrics.create(),
        api_key=values.get("API_KEY", ""),
        max_steps=int(values.get("AGENT_MAX_STEPS", "8")),
        max_tool_calls=int(values.get("AGENT_MAX_TOOL_CALLS", "16")),
        output_guard=values.get("AGENT_OUTPUT_GUARD", "1") != "0",
    )
    mcp_app, mcp_server = _mcp(registry, ctx, values)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp_server.session_manager.run():
            yield
        ctx.close()

    app = FastAPI(title="DemoTronics energy agent", version=__version__, lifespan=lifespan,
                  description="Synthetic data for a fictional plant. On-premises agent service.")
    app.state.service = service

    @app.middleware("http")
    async def guard(request: Request,
                    call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if service.api_key and path.startswith(PROTECTED):
            given = request.headers.get("x-api-key", "")
            if not hmac.compare_digest(given.encode(), service.api_key.encode()):
                service.metrics.http_requests.labels(_route(path), "401").inc()
                return JSONResponse({"detail": "missing or wrong X-API-Key"}, status_code=401)
        response = await call_next(request)
        service.metrics.http_requests.labels(_route(path), str(response.status_code)).inc()
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/ready")
    def ready() -> JSONResponse:
        checks: dict[str, str] = {}
        try:
            seed = ctx.query("SELECT seed FROM simulation_runs LIMIT 1")
            checks["database"] = f"ok (seed {int(seed.seed.iloc[0])})"
        except Exception as error:  # noqa: BLE001 - report any failure as not ready
            checks["database"] = f"error: {type(error).__name__}: {error}"
        try:
            checks["knowledge"] = f"ok ({ctx.store().count()} chunks)"
            if ctx.store().count() == 0:
                checks["knowledge"] = "error: index is empty, run `rag ingest`"
        except Exception as error:  # noqa: BLE001
            checks["knowledge"] = f"error: {type(error).__name__}: {error}"
        ok = all(v.startswith("ok") for v in checks.values())
        return JSONResponse({"status": "ready" if ok else "not ready", "checks": checks},
                            status_code=200 if ok else 503)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(service.metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/tools")
    def tools() -> list[dict[str, str]]:
        return [{"name": t.name, "permission": t.permission, "description": t.description}
                for t in registry.available(ctx.allow_write)]

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest) -> AskResponse:
        agent = Agent(service.make_llm(), registry, ctx, max_steps=service.max_steps,
                      max_input_chars=4000, max_tool_calls=service.max_tool_calls,
                      output_guard=service.output_guard)
        result = agent.run(body.question)
        service.metrics.record(result)
        log.info("ask", extra={"fields": {
            "run_id": result.run_id, "stop_reason": result.stop_reason,
            "latency_s": round(result.latency_s, 3), "tools": result.tools_called,
            "security_events": len(result.security_events), "model": result.model}})
        return AskResponse(
            answer=result.answer, stop_reason=result.stop_reason, run_id=result.run_id,
            model=result.model, tools_called=result.tools_called,
            citations=result.citations_valid, citations_removed=result.citations_invalid,
            security_events=result.security_events, latency_s=round(result.latency_s, 3),
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens)

    app.mount("/mcp", mcp_app)
    return app


def _route(path: str) -> str:
    """Bounded label values for metrics: never the raw path of an unknown URL."""
    for known in ("/health", "/ready", "/metrics", "/tools", "/ask", "/mcp"):
        if path == known or path.startswith(known + "/"):
            return known
    return "other"


def _mcp(registry: ToolRegistry, ctx: ToolContext, env: Mapping[str, str]) -> tuple[Any, Any]:
    from mcp.server.transport_security import TransportSecuritySettings

    from factory_energy.mcp_server.server import build_server

    server = build_server(registry, ctx, env)
    hosts = [h.strip() for h in env.get("MCP_ALLOWED_HOSTS",
                                         "127.0.0.1:8000,localhost:8000").split(",") if h.strip()]
    app = server.streamable_http_app(
        streamable_http_path="/", stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                                     allowed_hosts=hosts),
    )
    return app, server


def serve(host: str, port: int) -> None:
    import uvicorn

    from factory_energy.cli_agent import tool_context
    from factory_energy.tools import build_registry

    configure_logging()
    started = time.perf_counter()
    app = create_app(tool_context(), build_registry())
    log.info("starting", extra={"fields": {"host": host, "port": port,
                                           "startup_s": round(time.perf_counter() - started, 2)}})
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)
