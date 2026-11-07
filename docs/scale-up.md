# Scaling up: serving 500 engineers

What would change if this assistant served 500 engineers across several sites instead of one
demo user? Each section says what this project **has** today and what an enterprise version
would **add**. The plant and its data are fictional. The capacity numbers are estimates built
from the measurements in [eval/results/summary.md](../eval/results/summary.md); they are to be
checked by load tests, not quoted as results.

## 1. Authentication and authorisation

**Has:**
- One optional shared `API_KEY` on `/ask`, `/tools` and `/mcp`, compared in constant time.
- Every tool is `read` or `write`. Write tools stay hidden unless `AGENT_ALLOW_WRITE=1`.
- `MCP_TOOLS` narrows what an MCP client may call.

**Add:**
- **SSO (OIDC)** at the gateway, so every request carries a user identity and groups. No
  shared keys.
- **Roles mapped to tool scopes**, for example:
  - *viewer*: knowledge search and plant reads;
  - *engineer*: adds anomaly re-runs and what-ifs;
  - *energy lead*: adds report writing.
  The registry already checks permissions per call. It needs a per-user scope set instead of
  one process-wide flag.
- **Document permissions in retrieval.** Each chunk carries an ACL label (site, department,
  confidentiality), and the vector query filters on the caller's labels. A model should never
  see a passage its user could not open.

## 2. Multi-tenancy and data isolation

**Has:** one plant, one read-only DuckDB, one Chroma collection.

**Add:**
- **Tenant = site.** Each site gets its own collection or a mandatory metadata filter, and its
  own database role.
- **Tenant id set by the server.** The tool context carries a tenant id taken from the token,
  never from the prompt. Tools add it to every query, so a prompt cannot reach another site.
- **Separate indexes for sensitive departments** (finance, HR), not only filters, so a filter
  bug cannot leak them.
- **Per-tenant retention** for logs and traces.

## 3. Model routing

**Has:**
- One model per deployment, chosen by `LLM_PROVIDER`.
- Several configurations compared on the same evaluation set (`eval/configs.yaml`).

**Add:**
- **Small model first.** An 8B model answers lookups and document questions, which are about
  70% of the core set.
- **Escalate to the 30B-class model** when the question needs several tools, when the small
  model's answer fails the citation check, or when it hits the step limit.
- **Routing rules come from the evaluation.** A category is routed down only if the small model
  passes it at the required rate across repeated runs.
- **On-premises by default.** Cloud models would be allowed only by policy, for public, non-plant
  questions, behind a classifier and a data-loss-prevention check. Plant data never leaves.

## 4. Cost and capacity

**Has:**
- Up to 16 tool calls per question and 8 model steps.
- At most `AGENT_MAX_CONCURRENT` runs in flight per process (default 2), with a queue and a
  real stop.
- Token counts on every run.
- An HPA on the agent deployment.

**Add:**
- Per-user and per-tenant token budgets (daily, plus a hard cap per question).
- A shared queue in front of the model servers instead of per-process limits.
- Priority for interactive questions over batch reports.

**Estimate (assumptions stated):**
- **Questions per hour:** 20% of the 500 engineers use the assistant on a given day, at 5
  questions each, which is 500 questions a day. If 30% of them fall in the busiest hour, the
  peak is about 150 questions an hour.
- **Tokens per question:** the development stand-in used about 36,000 prompt tokens and 400
  completion tokens per question over all its model calls.
- **Load at the peak:** about 1,500 prompt tokens per second plus a few completion streams.
  Most prompt tokens are the shared system prompt and tool schemas, so vLLM prefix caching
  removes most of the prefill.
- **Sizing:** throughput is not the constraint; latency and availability are. Two replicas of a
  30B-class model on data-centre GPUs (one per failure domain) and one or two replicas of the
  8B router model would cover this with headroom.
- **Not yet checked:** the stage 3b profiling on the laptop and then the RTX 4090 measures
  tokens per second and time to first token at 1, 2 and 4 users. That data either confirms this
  sizing or replaces it.

## 5. Observability

**Has:**
- OpenTelemetry GenAI spans for every agent run, model call and tool call, exported over OTLP.
- JSONL run logs.
- Prometheus metrics: runs by stop reason, end-to-end, model and tool latency, tokens, guardrail
  events.

**Add:**
- **Trace sampling:** keep all errors and stops, 10% of successes.
- **A cost dashboard:** tokens per tenant, route and model, and GPU-hours.
- **Quality-drift alerts:** a nightly run of the evaluation sets against production
  configuration, with an alert when task success falls below the last release by more than its
  run-to-run spread.
- Alerts on rising citation-check failures, step-limit stops and guardrail events per tenant.

## 6. Quality governance

**Has:**
- Golden answers computed from the data and pinned to a dataset fingerprint.
- 25 core and 10 hard questions with programmatic scoring, 3 to 10 repeats with mean ± std (final system: 5 on core, 10 on hard).
- Re-grading without the model.
- A smoke subset in CI.

**Add:**
- **Versioned evaluation sets** (semantic version in the file, changes reviewed like code).
- **A release gate:** no prompt, model, tool or retrieval change ships if any category drops
  beyond its spread.
- **A human review queue** fed by low-confidence answers, user thumbs-down and citation-check
  removals. Reviewed cases become new evaluation questions.
- **When a citation check fails,** the answer is shown with the removed citation flagged rather
  than silently, and it is logged for review.

## 7. Security

**Has:**
- Structural controls: a read-only database, no free-form SQL, typed arguments, 31-day windows,
  write tools off, and a tool budget.
- Quarantine of retrieved text and an output guard.
- An injection corpus with a held-out set, which shows that structural controls generalise and
  pattern filters do not.

**Add:**
- **Every new tool goes through review:** threat model, permission class, argument limits and
  an attack in the corpus, before it joins the allow-list.
- **Per-tenant write approval:** a write proposed by the agent waits for a human click.
- **A held-out set kept by a separate owner,** refreshed every quarter and never used for
  tuning. A model or classifier is added in front of the pattern filters, and it is measured on
  the held-out set.
- **Secrets** come from the platform's secret store, never from environment files.
- **Egress** from the agent namespace is limited to the model servers and the data stores. A
  NetworkPolicy already does this in `k8s/`.

## 8. Migration path

1. **Pilot (one site, about 30 engineers).**
   - SSO at the gateway and a tenant id in the tool context.
   - The existing single model on vLLM.
   - Nightly evaluation, and dashboards built from the metrics that already exist.
2. **Department rollout (several sites, about 150).**
   - Per-site collections with ACL-filtered retrieval, roles mapped to tool scopes, a shared
     queue with token budgets.
   - The 8B to 30B router, with routing rules taken from the evaluation.
   - The human review queue.
3. **Enterprise (500 and more).**
   - Model servers on two failure domains, the release gate on every change, a held-out set
     with its own owner.
   - Write tools with approval, and cost reporting per tenant.
   - The multi-agent split ([multi-agent-design.md](multi-agent-design.md)) only if the
     evaluation shows single-agent answers degrade as the tool count grows.
