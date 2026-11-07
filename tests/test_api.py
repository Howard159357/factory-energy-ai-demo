import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import anyio
import pytest
import uvicorn
from fastapi.testclient import TestClient
from mcp.client import Client

from factory_energy.api.app import create_app
from factory_energy.llm.fake import FakeClient
from factory_energy.tools import build_registry
from factory_energy.tools.context import ToolContext


@pytest.fixture
def client(ctx: ToolContext) -> Iterator[TestClient]:
    app = create_app(ctx, build_registry(), FakeClient, env={})
    with TestClient(app) as test_client:
        yield test_client


def test_health_ready_and_tools(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["database"].startswith("ok")
    tools = client.get("/tools").json()
    assert len(tools) == 11 and all(t["permission"] == "read" for t in tools)


def test_ask_answers_and_feeds_the_metrics(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "How long does a reflow oven preheat?"})
    body = response.json()
    assert response.status_code == 200 and body["stop_reason"] == "answer"
    assert body["tools_called"] == ["search_knowledge"] and body["citations"]
    metrics = client.get("/metrics").text
    assert 'agent_runs_total{stop_reason="answer"} 1.0' in metrics
    assert 'agent_tool_calls_total{ok="true",tool="search_knowledge"} 1.0' in metrics
    assert 'http_requests_total{path="/ask",status="200"} 1.0' in metrics
    assert "agent_run_seconds_bucket" in metrics


def test_input_is_validated(client: TestClient) -> None:
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 4001}).status_code == 422
    assert client.post("/ask", json={"question": "hi", "sql": "drop"}).status_code == 200


def test_api_key_protects_the_agent_and_mcp(ctx: ToolContext) -> None:
    app = create_app(ctx, build_registry(), FakeClient, env={"API_KEY": "s3cret"})
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200  # probes stay open
        assert test_client.post("/ask", json={"question": "hi"}).status_code == 401
        assert test_client.post("/ask", json={"question": "hi"},
                                headers={"X-API-Key": "wrong"}).status_code == 401
        assert test_client.get("/mcp/").status_code == 401
        ok = test_client.post("/ask", json={"question": "reflow oven preheat"},
                              headers={"X-API-Key": "s3cret"})
        assert ok.status_code == 200
        assert 'http_requests_total{path="/ask",status="401"} 2.0' in test_client.get(
            "/metrics").text


def test_not_ready_without_a_database(ctx: ToolContext, tmp_path: Path) -> None:
    broken = replace(ctx, db_path=tmp_path / "absent.duckdb")
    with TestClient(create_app(broken, build_registry(), FakeClient, env={})) as test_client:
        response = test_client.get("/ready")
        assert response.status_code == 503 and "error" in response.json()["checks"]["database"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_mcp_over_streamable_http(ctx: ToolContext) -> None:
    port = _free_port()
    app = create_app(ctx, build_registry(), FakeClient,
                     env={"MCP_ALLOWED_HOSTS": f"127.0.0.1:{port}"})
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)

    async def session() -> tuple[int, float]:
        async with Client(f"http://127.0.0.1:{port}/mcp/") as mcp:
            tools = (await mcp.list_tools()).tools
            demand = await mcp.call_tool("get_demand", {"start": "2025-06-16T06:00",
                                                        "end": "2025-06-16T11:00"})
            return len(tools), float(demand.structured_content["peak_kw"])

    try:
        count, peak = anyio.run(session)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert count == 11 and peak > 1300
