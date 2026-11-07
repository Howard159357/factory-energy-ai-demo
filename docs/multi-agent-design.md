# Multi-agent design: an orchestrator and two specialists over A2A

Status: **design only, not implemented.** This page describes how the single energy agent would
split into an orchestrator and two specialist agents that talk over the Agent2Agent (A2A)
protocol, built with Google's Agent Development Kit (ADK). It also covers what the split would
cost and when it is worth it. The plant is fictional and all data is synthetic.

## Today: one agent, twelve tools

One hand-written loop (`src/factory_energy/agent/loop.py`) plans, calls typed tools in parallel,
feeds errors back and checks citations. Its twelve tools are one knowledge search, nine plant
data and analysis tools, the overview, and the write tool, which is off by default. Measured
with the development stand-in on the 25 core questions: 100% task success, a median of 13.4 s,
a p95 of 32.2 s, 1.7 tool calls and about 36,000 prompt tokens per question. The local-model
numbers come with the on-premises runs.

## Proposed agents

| Agent | Job | Tools | Model |
|---|---|---|---|
| **Orchestrator** | Understands the question, decides which specialists to ask (in parallel when independent), checks their answers, writes the final answer with citations | None of the plant tools; only the two specialists, as remote agents | 30B-class |
| **Energy analyst** | Numbers: demand, energy, cost, series, statistics, equipment status, detections, forecasts, what-ifs | The nine data and analysis tools plus the plant overview, read-only | 30B-class, or 8B for single lookups |
| **Knowledge agent** | Procedures, thresholds, tariff rules, from the documents, with citations | `search_knowledge` only | 8B |

With ADK, each specialist is an `LlmAgent` with its own instruction and tool list, published
over A2A (ADK can wrap an agent as an A2A server). The orchestrator reaches each one as a
remote A2A agent. The existing tool functions are reused unchanged: the registry, pydantic
validation, the replay-clock cutoff and the guardrails stay where they are, inside the
specialist that owns the tools.

## Messages

A2A is JSON-RPC 2.0 over HTTP. Each agent publishes an **agent card** (name, description,
skills, endpoint, authentication) at a well-known URL, so the orchestrator discovers what a
specialist can do instead of hard-coding it. A request is `message/send`, or `message/stream`
for live progress. The specialist answers with a **task** that moves through `submitted` →
`working` → `completed` (or `failed`, `canceled`, `input-required`), and its results are
**artifacts**.

The orchestrator sends one task per specialist:

```json
{"role": "user", "parts": [
  {"kind": "text", "text": "Plant energy for MDB-5, 2025-09-09 to 2025-09-16 and the week before"},
  {"kind": "data", "data": {"now": "2025-09-20T08:00", "tenant": "site-a",
                            "trace_id": "4bf9...", "budget": {"tool_calls": 8, "seconds": 40}}}
]}
```

The specialist returns a text answer and one structured artifact:

```json
{"kind": "data", "data": {
  "findings": [{"claim": "MDB-5 used 21,605 kWh", "value": 21605.2, "unit": "kWh",
                "evidence": "data:get_energy", "window": ["2025-09-09", "2025-09-16"]}],
  "citations": ["data:get_energy"], "tool_calls": 2, "stopped": null}}
```

Three rules make this safe:
- **`now`, the tenant and the trace id travel in a data part set by the orchestrator's
  server,** never in model-written text. Each specialist applies `now` through
  `ToolContext.as_of`, so the replay-clock guarantee still holds across agents.
- **The orchestrator may cite only what a specialist returned in `citations`.** The existing
  citation check runs on the final answer against the union of the specialists' verified
  citations.
- **Specialist output is data, not instructions.** It is quarantined like retrieved text before
  the orchestrator reads it.

## Failure handling

| Failure | Handling |
|---|---|
| Specialist unreachable or times out | One retry with the same task id. The orchestrator then answers from what it has and says which part is missing. It never guesses the number. |
| Specialist returns `failed` (bad arguments, no data) | The reason goes back to the orchestrator as an observation, which may rephrase once. This mirrors how tool errors are fed back today. |
| Budget exceeded (tool calls, seconds, tokens) | The specialist stops and returns partial findings with `stopped: "budget"`. The orchestrator reports the gap. |
| User presses Stop | The orchestrator sends `tasks/cancel` to every open task. Each specialist cancels its model call (the same `cancel()` used now) and ends in `canceled`. |
| Specialist asks back (`input-required`) | Passed to the user as a clarifying question. This is the hard set's "ambiguous" behaviour, one level down. |
| Disagreement (two numbers for one fact) | The answer cannot pass the citation check twice. The orchestrator re-asks the energy analyst with both values, or reports both. |

Every hop carries the trace id, so one OpenTelemetry trace shows the orchestrator's span with
the specialists' spans and their tool calls beneath it.

## When to split, and when one agent is enough

**Split when at least one of these holds:**
- **Too many tools for one model.** With twelve tools the single agent chooses well (1.7 calls
  per question). As tools grow past about 20, or when the routine questions move to an 8B
  model, tool choice degrades. Specialists with five to ten tools each keep the choice easy.
- **Different security boundaries.** The knowledge agent reads untrusted documents. If it has
  no data or write tools, a planted instruction in a document can reach the plant data only by
  convincing the orchestrator, and the orchestrator reads specialist output as quarantined data.
  This is structural containment, which the security tests show generalises better than text
  filters.
- **Different owners or release cycles.** For example, the energy team owns the analytics
  agent and the documentation team owns the knowledge agent, and each can be evaluated and
  released on its own.
- **Different models per role.** Document questions on an 8B model, numbers on a 30B model.

**Stay with one agent while:**
- the tool count stays small and one team owns it all, which is true today;
- latency matters more than separation, as in the live dashboard;
- the evaluation shows no gain. The split adds moving parts (network hops, more prompts, more
  failure modes) that must earn their place.

## Expected latency and cost

These are estimates to be measured, not results:
- **Model calls:** the orchestrator adds about two calls per question (one to plan and
  delegate, one to synthesise). Each specialist has its own system prompt and tool schemas.
- **Latency:** on questions that need only one specialist, about **+30–60%** over today's single
  agent (two extra model calls, plus milliseconds per A2A hop). On questions that need both
  specialists, they run in parallel, which recovers part of the cost.
- **Tokens:** about **+40–80%** per question, because more prompts carry their own preamble.
  This is partly offset by smaller tool lists per prompt and by the 8B knowledge agent.
- **Operations:** three services to deploy, monitor and version instead of one, plus agent-card
  and authentication management between them.

## How it would be decided

Run the same 35 questions (25 core and 10 hard), three times each, with the single agent and with
the multi-agent version, on the same local models. Adopt the split only if:
- task success is at least equal overall, and better on the hard `chain` and `citation`
  categories;
- the held-out injection attacks breach no more often;
- median latency rises by no more than 50%.

Otherwise keep one agent and revisit when the tool count or the team structure changes.

## Implementation outline (for when it is built)

1. `src/factory_energy/agents/`: one module each for the energy analyst, the knowledge agent and
   the orchestrator. Each is an ADK `LlmAgent` with the existing tool functions wrapped as
   function tools.
2. Each specialist is served as an A2A app (its own container, sharing the read-only database
   and Chroma), with an agent card that lists its skills.
3. The orchestrator gets the specialists as remote A2A agents. The citation check, output guard
   and quarantine run on its final answer.
4. The dashboard chat and `/ask` call the orchestrator. The single agent stays as the fallback
   and the baseline.
5. Extend `eval run` with a `--agent single|multi` switch, so both appear in the same tables.
