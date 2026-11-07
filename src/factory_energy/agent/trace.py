"""Observability: OpenTelemetry spans for every run, model call and tool call, plus a JSONL log.

Span names and attributes follow the OpenTelemetry GenAI semantic conventions
(``invoke_agent``, ``chat <model>``, ``execute_tool <name>``, ``gen_ai.usage.*``). Spans are
exported over OTLP when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (Jaeger in docker compose);
the JSONL file per run is always written so a run can be inspected without a collector.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from factory_energy.rag.settings import REPO_ROOT

if TYPE_CHECKING:
    from factory_energy.agent.loop import AgentResult

TRACER_NAME = "factory_energy.agent"


def tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def setup_tracing(
    env: Mapping[str, str] | None = None, extra: SpanProcessor | None = None
) -> TracerProvider | None:
    """Install a tracer provider once per process; returns it, or None if one already exists."""
    values = os.environ if env is None else env
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return None
    provider = TracerProvider(resource=Resource.create(
        {"service.name": values.get("OTEL_SERVICE_NAME", "factory-energy-agent")}))
    endpoint = values.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(_otlp(endpoint)))
    if extra is not None:
        provider.add_span_processor(extra)
    trace.set_tracer_provider(provider)
    return provider


def _otlp(endpoint: str) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=endpoint, insecure=endpoint.startswith("http://"))


def log_dir(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    path = Path(values.get("AGENT_LOG_DIR", "logs/agent"))
    return path if path.is_absolute() else REPO_ROOT / path


def write_jsonl(result: AgentResult, folder: Path) -> Path:
    """One line per event: run start, each model call and tool call, the final answer."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{result.started:%Y%m%d-%H%M%S}-{result.run_id[:8]}.jsonl"
    events: list[dict[str, Any]] = [{
        "event": "run_start", "run_id": result.run_id, "model": result.model,
        "question": result.question, "started": result.started.isoformat(),
    }]
    events += [{"event": step.kind, **asdict(step)} for step in result.steps]
    events.append({
        "event": "final", "answer": result.answer, "plan": result.plan,
        "citations_valid": result.citations_valid, "citations_invalid": result.citations_invalid,
        "stop_reason": result.stop_reason, "tools_called": result.tools_called,
        "security_events": result.security_events,
        "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        "latency_s": round(result.latency_s, 3), "llm_s": round(result.llm_s, 3),
        "tool_s": round(result.tool_s, 3),
    })
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return path
