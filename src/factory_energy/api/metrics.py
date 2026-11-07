"""Prometheus metrics for the agent service, in a registry owned by the app (no global state)."""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram

from factory_energy.agent.loop import AgentResult

LATENCY_BUCKETS = (0.1, 0.5, 1, 2, 5, 10, 20, 30, 60, 120)


@dataclass(frozen=True)
class AgentMetrics:
    registry: CollectorRegistry
    http_requests: Counter
    runs: Counter
    run_latency: Histogram
    llm_latency: Histogram
    tool_latency: Histogram
    tool_calls: Counter
    tokens: Counter
    security_events: Counter

    @classmethod
    def create(cls) -> AgentMetrics:
        registry = CollectorRegistry()
        return cls(
            registry=registry,
            http_requests=Counter("http_requests", "HTTP requests", ["path", "status"],
                                  registry=registry),
            runs=Counter("agent_runs", "Agent runs by stop reason", ["stop_reason"],
                         registry=registry),
            run_latency=Histogram("agent_run_seconds", "End-to-end agent latency",
                                  buckets=LATENCY_BUCKETS, registry=registry),
            llm_latency=Histogram("agent_llm_call_seconds", "Model call latency",
                                  buckets=LATENCY_BUCKETS, registry=registry),
            tool_latency=Histogram("agent_tool_call_seconds", "Tool call latency", ["tool"],
                                   buckets=LATENCY_BUCKETS, registry=registry),
            tool_calls=Counter("agent_tool_calls", "Tool calls", ["tool", "ok"],
                               registry=registry),
            tokens=Counter("agent_tokens", "Model tokens", ["direction"], registry=registry),
            security_events=Counter("agent_security_events", "Guardrail events", ["layer"],
                                    registry=registry),
        )

    def record(self, result: AgentResult) -> None:
        self.runs.labels(result.stop_reason).inc()
        self.run_latency.observe(result.latency_s)
        for step in result.steps:
            if step.kind == "llm":
                self.llm_latency.observe(step.duration_s)
            else:
                self.tool_latency.labels(step.name).observe(step.duration_s)
                self.tool_calls.labels(step.name, str(step.ok).lower()).inc()
        self.tokens.labels("input").inc(result.prompt_tokens)
        self.tokens.labels("output").inc(result.completion_tokens)
        for event in result.security_events:
            self.security_events.labels(event["layer"]).inc()
