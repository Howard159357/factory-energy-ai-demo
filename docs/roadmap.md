# Roadmap

| Phase | Scope | Status |
|---|---|---|
| P0 | Clean repository, plant/meter config, energy engine, DuckDB storage, CI | done |
| P1 | Plant simulator: equipment state machines, production schedule, weather, one year of 1-minute data, ground-truth labels | done |
| P2 | Scenario engine (YAML) and core scenarios S1–S5, S8 | done |
| P3 | Anomaly detection (rules, statistical baselines, IsolationForest) with precision/recall against labels | done |
| P4 | Load forecasting (LightGBM quantiles), rolling-origin backtest, demand-exceedance alerts | done |
| P4b | Model comparison (profile, Ridge, HGB, LightGBM, ensemble; 15 min to 3 h and 24 h horizons) and backtest cache | done |
| P4c | Deferred forecasting items: extra lag/volatility features, 7-day cost strip | planned |
| P5 | Dashboard (7 pages) with simulated-clock scenario replay | done |
| P5b | Plant map home page (illustration with live anchors) and single-line diagram on the Demand page | done |
| P6 | Scripted demo recording, title cards, README animations, demo video, social preview | done |
| P7 | Optional: remaining scenarios, AI shift summary, hosted demo | planned |
| A1 | Knowledge base: generated plant documents, chunking, embeddings, Chroma, cited search | done |
| A2 | Agent: typed tools with permissions, MCP server, tool-calling loop, OpenTelemetry tracing | done |
| A2b | Multi-agent layer over A2A (orchestrator and specialist agents) | designed ([multi-agent-design.md](multi-agent-design.md)); next phase, built only if the evaluation favours it |
| A3 | Evaluation: golden answers from data, scoring, repeated runs, retrieval metrics | done |
| A3b | vLLM serving and inference benchmark on the local GPU host | done |
| A4 | Security: injection corpus with held-out set, guardrails, interception rates | done |
| A5 | Deployment: HTTP service, container, Kubernetes, CI with container and kind tests | done |
| A6 | Showcase: README, data documentation, demo storyboard | done |

## Next phase

1. **On-premises numbers.**
   - Run the 25 core and 10 hard questions and the security tests on the local engine.
   - Run the indicative profiling (A3b).
   - Then run it all again on the RTX 4090 with the 30B-class models.
2. **Real embeddings.** Hash against a multilingual model, for retrieval and the full
   evaluation.
3. **Multi-agent (A2b).**
   - Build the orchestrator, the energy analyst and the knowledge agent over A2A with Google
     ADK, as in [multi-agent-design.md](multi-agent-design.md).
   - Compare them with the single agent on the same questions.
   - Adopt the split only if it passes the stated criteria.
4. **Enterprise path.** [scale-up.md](scale-up.md) describes what serving 500 engineers would
   add, in three phases.

## Scenarios

| ID | Scenario | Detection | Status |
|---|---|---|---|
| S1 | Normal weekday / weekend / night shift | baseline | done |
| S2 | Monday 08:00 simultaneous start of molders, reflow ovens and a chiller | step-change rule, demand risk | done |
| S3 | Heat wave pushes 15-min demand toward the contract limit | forecast exceedance probability | done |
| S4 | Compressed-air leak raises weekend base load | baseline drift (CUSUM / STL residual) | done |
| S5 | Reflow oven left idling over the weekend | off-schedule consumption rule | done |
| S6 | Reflow heater degradation | per-equipment efficiency drift | planned |
| S7 | Injection molder heater band failure | IsolationForest | planned |
| S8 | Capacitor bank fault lowers power factor | PF threshold rule | done |
| S9 | Phase current imbalance | imbalance rule | planned |
| S10 | Meter communication loss, frozen value, kWh reset | data quality checks | planned |
| S11 | Chiller efficiency loss | temperature-adjusted regression residual | planned |
| S12 | Lunar New Year shutdown / annual maintenance | forecast holiday handling | planned |
