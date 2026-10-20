# Load forecasting

All data in this repository is synthetic. The forecasting layer predicts the 15-minute demand of the
fictional plant and turns the forecast into early warnings about the 1,250 kW contract limit.

## Goal

- **Demand control**: forecasts 15 min, 30 min, 1 h, 2 h and 3 h ahead, so an operator can shed
  load before the interval closes above the contract and can see the next-3-hour peak coming.
- **Day-ahead**: a 24 h forecast for planning and a next-day advisory.
- Every forecast is a **P10 / P50 / P90 band**, plus the **probability of exceeding 1,250 kW**.

## Leakage-free framing

One training row means: *we are standing at the end of interval i and predict interval i + h*. Only
information that really exists at that moment is allowed:

- demand up to interval i (`last`, `last_mean_1h`, `last_trend_1h`);
- demand at the same time yesterday and last week (`same_time_yesterday`, `same_time_last_week`);
- the production calendar, which is planned in advance (`is_workday`, `is_saturday`, `is_sunday`,
  `is_holiday`, `overtime`, `after_rest_day`);
- time of day and weekday (`slot`, `slot_sin`, `slot_cos`, `weekday`);
- a temperature **forecast** for the target time (`temp_forecast`) and the temperature at issue time
  (`temp_now`).

The temperature forecast is the actual temperature plus an error that grows with lead time:
`sd = 0.3 + 1.5 * min(h / 96, 1)` degrees C. The model never sees the true future temperature.

## Model

One **LightGBM quantile model** per quantile (0.1, 0.5, 0.9) per horizon. Each model predicts the
**change from an anchor**, not the demand level:

- short horizons (15 min to 3 h): anchor is the last completed interval;
- day-ahead: anchor is the same time last week.

Why change, not level: tree models cannot predict values above anything seen in training, and the
plant rarely exceeded its contract in the training data. A level model therefore tends not to warn
about an exceedance; the first version (level target) missed the exceedances. Predicting a change lets
the model add a heat-driven or start-up-driven increment on top of the current load.

Two refinements keep the bands honest:

- **Quantile crossing** is fixed by sorting P10 <= P50 <= P90 per row.
- **Conformal widening**: the models are fitted on all but the last 14 days of the training window;
  the band is then scaled so that 80% of those held-out 14 days fall inside P10-P90.

## Exceedance probability and alerts

P(demand > 1,250 kW) is computed from the three quantiles with a **two-piece normal** (different
spread below and above the median). Two alert tiers use the next-hour (15-60 min) forecast:

| Tier | Rule |
|---|---|
| Warning | P(exceed) >= 0.2 |
| Alarm | P(exceed) >= 0.5 |

## Rolling-origin backtest

For each month from June to December 2025 the models are trained on **everything before that
month** and used to forecast that month. All reported numbers are out-of-sample. Baselines:
persistence (last interval) for the short horizons, and same time last week for day-ahead.

## Results

Default run (seed 42, all scenarios), primary model (LightGBM):

| Horizon | MAE kW | WAPE | P10-P90 coverage | Baseline MAE | Skill |
|---|---|---|---|---|---|
| 15 min | 6.4 | 1.0% | 80% | 13.1 | 51% |
| 30 min | 8.5 | 1.3% | 80% | 23.9 | 64% |
| 1 h | 11.8 | 1.9% | 80% | 44.8 | 74% |
| 2 h | 15.7 | 2.5% | 81% | 79.1 | 80% |
| 3 h | 19.1 | 3.0% | 80% | 112.7 | 83% |
| 24 h | 31.0 | 4.9% | 77% | 49.8 | 38% |

Skill = 1 - MAE / baseline MAE. WAPE is the total absolute error divided by the total demand.
The baseline is persistence up to 3 h and same time last week at 24 h.

On real meter data from a working plant the same approach (gradient boosting with calendar
features) gave a WAPE of about 2% at 15 minutes, 3.5% at 1 hour and 5% at 3 hours ahead, roughly
twice this synthetic benchmark, because real demand has unscheduled events the simulator does not
generate.

### Exceedance alerts

| Event | Peak | Warning lead | Alarm lead |
|---|---|---|---|
| S3 heat wave, 2025-07-23 14:00-15:45 (sustained) | 1,263 kW day peak | 30 min | 30 min |
| S3 heat wave, 2025-07-24 13:00-15:30 (sustained) | 1,267 kW day peak | 30 min | 30 min |
| S3 heat wave, 2025-07-24 15:45-16:15 | | 75 min | 75 min |
| S3 single-interval blips, 2025-07-23 13:30 and 2025-07-24 11:45 | about 1 kW and 17 kW over | missed | missed |
| S2 simultaneous start, 2025-06-16 08:00 | 1,324 kW | 0 min | 0 min |

- **S3** is caught early when the overrun is sustained: the heat wave builds gradually and the forecast sees the episodes coming 30 to 75 minutes ahead (warning at P(exceed) >= 0.2, alarm at >= 0.5; both tiers fired at those leads). Honest miss: demand hovers only 0-1.5% above the contract, and two single-interval blips (2025-07-23 13:30 and 2025-07-24 11:45, about 1 kW and 17 kW over) were not forecast.
- **S2** is not predictable: a forecast cannot anticipate operators switching everything on at
  once. It is caught in real time by the `SIMULTANEOUS_START` rule (see
  [anomaly_detection.md](anomaly_detection.md)) and should be prevented with a start-up sequence.
- **False alarms**: over June-December there are 4 false-alarm hours for the warning tier and 2 for the
  alarm tier.
- **Day-ahead**: the day-ahead exceedance probability is usable as a next-day advisory, but it
  also flags some hot days that stayed below the limit, so treat it as an advisory, not an alarm.

## Model comparison

Five models are compared. They share the same features, the same delta-from-anchor framing, the same
rolling-origin backtest and the same 80%-coverage calibration on a held-out fortnight, so the
differences come from the model alone.

| Model | What it is |
|---|---|
| `profile` | Median of the same weekday type and 15-minute slot over the last 4 weeks, nudged by the current deviation from that profile (the nudge decays with lead time). The "spreadsheet baseline". |
| `linear` | Ridge regression (alpha 10) on the same features; bands from empirical residual quantiles. |
| `hgb` | scikit-learn `HistGradientBoostingRegressor` with the quantile loss (180 iterations, learning rate 0.05, 31 leaves, L2 1.0), same features as LightGBM. A dependency-light alternative. |
| `lightgbm` | Gradient-boosted quantile regression. The primary model: the dashboard and the alerts use it. |
| `ensemble` | Quantile-wise average of `lightgbm` and `linear`, derived from their stored forecasts (never refitted). |

Deliberately not included:

- **XGBoost / CatBoost**: same family as LightGBM, so they would add rows, not insight.
- **Prophet / ARIMA**: weak at 15-minute demand control, where the last few intervals and the start-up calendar matter most.
- **LSTM / Transformer**: cost, and over-claiming on synthetic data.

### Leaderboard

June to December, out-of-sample. MAE and pinball loss are in kW; cover is the share of actuals
inside the 10-90% band (target 80%). WAPE is total absolute error over total demand. Skill is
relative to persistence up to 3 h, and to same time last week for 24 h.

| Horizon | Model | MAE kW | WAPE | Pinball kW | Cover | Skill |
|---|---|---|---|---|---|---|
| 15 min | lightgbm | 6.4 | 1.0% | 2.16 | 80% | +51% |
| 15 min | hgb | 6.4 | 1.0% | 2.18 | 80% | +51% |
| 15 min | ensemble | 9.9 | 1.6% | 3.53 | 84% | +25% |
| 15 min | linear | 15.1 | 2.4% | 5.78 | 81% | -15% |
| 15 min | profile | 15.2 | 2.4% | 5.68 | 81% | -16% |
| 30 min | lightgbm | 8.5 | 1.3% | 2.90 | 80% | +64% |
| 30 min | hgb | 8.8 | 1.4% | 2.96 | 80% | +63% |
| 30 min | ensemble | 15.5 | 2.4% | 5.41 | 84% | +35% |
| 30 min | profile | 24.9 | 3.9% | 9.65 | 81% | -4% |
| 30 min | linear | 25.7 | 4.0% | 9.35 | 82% | -7% |
| 1 h | lightgbm | 11.8 | 1.9% | 4.16 | 80% | +74% |
| 1 h | hgb | 12.2 | 1.9% | 4.31 | 81% | +73% |
| 1 h | ensemble | 24.2 | 3.8% | 8.21 | 86% | +46% |
| 1 h | profile | 37.5 | 5.9% | 15.29 | 82% | +16% |
| 1 h | linear | 41.9 | 6.6% | 14.41 | 82% | +7% |
| 2 h | lightgbm | 15.7 | 2.5% | 5.76 | 81% | +80% |
| 2 h | hgb | 16.7 | 2.6% | 6.03 | 80% | +79% |
| 2 h | ensemble | 31.5 | 5.0% | 10.52 | 87% | +60% |
| 2 h | profile | 49.2 | 7.7% | 20.80 | 82% | +38% |
| 2 h | linear | 54.4 | 8.6% | 17.80 | 83% | +31% |
| 3 h | lightgbm | 19.1 | 3.0% | 7.08 | 80% | +83% |
| 3 h | hgb | 20.1 | 3.2% | 7.32 | 80% | +82% |
| 3 h | ensemble | 35.2 | 5.5% | 11.68 | 88% | +69% |
| 3 h | profile | 53.3 | 8.4% | 22.88 | 82% | +53% |
| 3 h | linear | 59.3 | 9.3% | 18.99 | 84% | +47% |
| 24 h | lightgbm | 31.0 | 4.9% | 11.27 | 77% | +38% |
| 24 h | hgb | 32.0 | 5.0% | 11.65 | 78% | +36% |
| 24 h | ensemble | 41.8 | 6.6% | 14.08 | 86% | +16% |
| 24 h | profile | 55.5 | 8.7% | 24.09 | 82% | -11% |
| 24 h | linear | 61.6 | 9.7% | 19.96 | 84% | -24% |

Pinball loss is the proper score for quantile forecasts: it rewards a band that is both calibrated
and sharp, which MAE of the median alone cannot show.

### Next-3-hour peak

At every issue time, the highest P50 over the 15 min to 3 h horizons is compared with the highest
actual demand over the same window. This is what a dispatcher asks: "how high will the next three
hours get, and when?" There are 20,533 issue times. Bias is forecast minus actual; the timing error
is the median difference between the forecast and actual peak times.

| Model | Peak MAE kW | Bias kW | Median timing error |
|---|---|---|---|
| lightgbm | 12.6 | -3.4 | 0 min |
| hgb | 13.5 | -4.1 | 0 min |
| ensemble | 23.5 | -0.4 | 0 min |
| linear | 39.6 | +5.1 | 0 min |
| profile | 39.8 | +21.8 | 15 min |

The profile baseline overestimates the peak by about 22 kW on average; the tree models slightly
underestimate it.

### Alarm lead per exceedance episode

Six episodes: the S2 start-up at 08:00, then five on Jul 23-24. Lead is in minutes before the
interval closed over the contract; `-` means missed.

| Model | S2 08:00 | Jul 23-24 (five episodes) | False-alarm hours |
|---|---|---|---|
| profile | 0 | - - - - - | 0 |
| linear | 0 | 30, 0, -, 0, - | 2 |
| hgb | 0 | -, 30, -, 30, 75 | 2 |
| lightgbm | 0 | -, 30, -, 30, 75 | 2 |
| ensemble | 0 | -, 0, -, 0, 0 | 2 |

### Honest reading

- At 30 minutes and below the simple models (`profile`, `linear`) are **worse than persistence**.
  The plant's load is smooth from minute to minute, so "stays as it is" is hard to beat without
  learning the ramps. From 1 h on they beat persistence.
- The tree models win at every horizon. `hgb` tracks `lightgbm` within about 5% on every metric and
  gives the same alarm leads, so it is a reasonable dependency-light alternative.
- Averaging with Ridge dilutes the tree model, so the ensemble is kept only as a reference.
- Results are on synthetic data and say nothing about a real plant.

## Backtest cache

Each (model, horizon, month) backtest unit is stored in `forecasts` (primary key `model`,
`target_ts`, `horizon_min`) and registered in `forecast_runs` with a **fingerprint**: a hash of the
demand history (kW, temperature, day types, overtime) plus the feature version and the model
version. `forecast` reuses units whose fingerprint matches and reruns only what changed.

| Option | Effect |
|---|---|
| `--refresh` | ignore the cache and rerun everything |
| `--models profile,hgb,lightgbm` | restrict the run to these models |
| `--workers N` | size of the process pool (default 4; work is split one horizon per process) |

Timings measured on a laptop:

| Run | Time |
|---|---|
| First full run (all trained units over one process per horizon, plus derived ensemble units) | about 3 minutes |
| Rerun, nothing changed | about 2.5 s |
| Rerun after bumping two models' versions | about 14 s (only those models recomputed) |

The old single-model table layout is replaced automatically.

## How to run

```bash
python -m factory_energy forecast [--db data/plant.duckdb] [--models ...] [--workers N] [--refresh]   # about 3 min first run
```

This prints the backtest table (with a WAPE column), the "Next-3-hour peak" table, the alert
episodes and the alarm lead per model, and stores the out-of-sample forecasts in the
`forecasts` table:

| Column | Meaning |
|---|---|
| `issue_ts` | when the forecast was issued |
| `target_ts` | interval being predicted |
| `horizon_min` | lead time in minutes |
| `p10`, `p50`, `p90` | forecast quantiles in kW |
| `p_exceed` | probability of exceeding the contract |
| `actual` | measured demand for the target interval |
| `model` | model identifier |

## Limitations

- The data is synthetic, so real-world accuracy is not implied.
- The weather forecast error is simulated, not taken from a real forecast provider.
- There is no online retraining yet; models are refitted per backtest month only.
- The dashboard replays these stored out-of-sample forecasts rather than running live models. The next-hour forecast it shows is the one issued at the last completed interval.
