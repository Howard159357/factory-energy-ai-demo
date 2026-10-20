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
| P6 | Scripted demo recording, title cards, README GIFs, demo video, social preview | done |
| P7 | Optional: remaining scenarios, AI shift summary, hosted demo | planned |

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
