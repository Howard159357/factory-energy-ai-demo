# Dashboard

The dashboard is the command-center front end of the demo: a Dash / Plotly app that replays the
synthetic plant year as if it were happening live. It shows power and demand, equipment status,
anomaly detections and the load forecast, all driven by the simulator, `detect` and `forecast`
outputs. Every screen carries a **SYNTHETIC DEMO DATA** badge in the top bar; the plant is
fictional.

## Running it

```bash
python -m factory_energy build-demo   # simulate, detect and forecast into the demo database
python -m factory_energy dashboard    # serves http://127.0.0.1:8731
```

The server binds to the loopback address only (local use, no network exposure) and runs with
debug mode off. `build-demo` prepares everything the pages read (readings, labels, detections,
forecasts), so the dashboard itself never trains or detects anything at start-up.

## Status banner

Every page shows a status banner under the top bar: **OK**, **WARNING** or **ALARM**, one sentence
saying why, and a recommended action.

| Level | Condition |
|---|---|
| ALARM | Projected 15-minute demand is above the contract, or P(exceed next hour) >= 50% |
| WARNING | P(exceed next hour) >= 20%, or projected demand >= 90% of the contract (1,125 kW) |
| OK | Otherwise |

The recommended action names the first rows of the load-shed playbook that together cover the
reduction needed. The banner and the page below it read the same per-instant state, so they never
disagree. A disclaimer line under it reads: "Internal management alert for dispatch decisions; not
the utility's official exceedance ruling."

## The replay clock

The top bar holds the simulated clock that every page follows.

- **Scenario dropdown**: picks a labelled incident scenario; the clock resets to the start of that
  scenario's replay window. The default scenario is S2. The scenario's one-line `caption` (see
  [scenarios.md](scenarios.md)) is shown in the clock bar.
- **Speed**: 60x, 300x, 900x or 3600x, meaning 1, 5, 15 or 60 simulated minutes per one-second
  tick. The default is 300x.
- **Pause / Play**: freezes or resumes the clock. The clock stops by itself at the end of the
  replay window. A paused or finished clock sends no updates to the server.
- **Jump to event**: moves the clock to 45 minutes before the first high-severity label of the
  scenario; if there is none, before the first rule or baseline detection in the replay window.
- **Restart**: back to the start of the replay window, playing.
- The clock state survives page reloads within the same browser tab.

## Tariff

`config/factory.yaml` has a `tariff` section. Its structure and unit prices follow Taipower's
high-voltage **three-segment time-of-use tariff with a fixed peak** (tariff table approved on
17 November 2025). Money is shown as NT$ with a US$ equivalent at an illustrative NT$32 = US$1,
for example `NT$6,652 (US$208)`. The demo plant holds only a regular contract of 1,250 kW.

| Period (Mon–Fri) | Summer, 16 May–15 Oct | Other months |
|---|---|---|
| Peak | 16:00–22:00, NT$9.39/kWh | none |
| Half-peak | 09:00–16:00 and 22:00–24:00, NT$5.85/kWh | 06:00–11:00 and 14:00–24:00, NT$5.47/kWh |
| Off-peak | 00:00–09:00, NT$2.53/kWh | the rest, NT$2.32/kWh |

Saturday daytime is a cheaper "Saturday half-peak" (NT$2.60 / 2.41); Sundays are off-peak all
day. The demand charge is per kW of contract per month: NT$223.60 (summer) and NT$166.90 for the
regular contract, NT$44.70 / 33.30 for off-peak and Saturday contracts.

- **Exceedance.** When the month's highest 15-minute demand in a period is above the contract,
  the excess is billed at that period's contract price: **2x up to 10% of the contract, 3x
  beyond**, with no power-factor credit on it. The period matters: the S2 surge at 08:15 on a
  summer Monday is off-peak, so its 74.4 kW excess costs 74.4 x 44.70 x 2 ≈ NT$6,652 (US$208); the
  same surge at 16:00 would cost 74.4 x 223.60 x 2 ≈ NT$33,277 (US$1,040).
- **Power factor.** The monthly average power factor adjusts the whole bill by 0.1% per
  percentage point from 80%: a surcharge below 80%, a credit above it, up to 95% (1.5% at most).
  The dashboard's 0.90 rule is an early warning that fires well before any surcharge.

It is used for:

- the **Energy today** KPI on the Overview (MWh, with the cost so far in its sub-line);
- the impact line on alerts: a demand exceedance costs the period's contract price x 2 (x3
  beyond 10%); off-schedule running costs `kWh x the energy rate at its start`; an air leak costs
  about `kW x 8,760 h x the year's average energy rate` (NT$4.12/kWh); a low power factor shows
  the bill credit or surcharge it leads to;
- the S2 what-if hero card on the Demand page.

## Pages

| Page | What it shows |
|---|---|
| Plant map (home, `/`) | An illustration of the fictional plant with live data anchored on each distribution board, a load bar against the contract and a hot-afternoon tint caption; see [Plant map](#plant-map) |
| Overview (`/overview`) | KPIs (Plant load, 15-min demand (projected), Contract usage, Chance of exceeding within the next hour, Energy today in MWh with the cost in its sub-line, Next 3 h peak (forecast) with the outdoor temperature in its sub-line), actual load against the day-ahead and next-hour forecast bands, the alert list with impact lines, and load by distribution board |
| Demand | The what-if hero card, the interval in progress, average so far, headroom and next-hour risk level; 15-minute demand with the next-hour forecast; the load-shed playbook; the exceedance probability over the day; the single-line diagram at the bottom |
| Equipment | One card per sub-metered load, grouped by distribution board, with live kW, share of rating, 24-hour energy and a status chip |
| Anomalies | Counts per layer, the table of detections so far, an evidence chart for the selected detection and a details panel with the scores table |
| Forecast | A "Model shown" dropdown, the "Next 3 hours" forecast chart, today's day-ahead forecast (P10-P90 band and P50) against actual demand, a one-line takeaway, the out-of-sample accuracy table, a "Model comparison" card and a short explanation of the model |
| History | Weekday-by-hour load heatmap, top equipment over the last 30 days and monthly energy by distribution board |

### Plant map

The home page (`/`) shows an isometric illustration of the fictional plant at dawn
(`src/factory_energy/dashboard/assets/plant_map.webp`, 1920x1080, about 430 KB) with live data
anchored on it. Anchors come from `config/layout.yaml`: for each distribution board, a percent x/y
position on the image and a label side (`left` or `right`).

- Each board shows a glowing dot and a label with live kW and % of rating.
- The dot turns amber above 85% of rating, and red (pulsing) when a rule or baseline detection is
  open on that board or on one of its loads; the reason is shown on the label.
- A load bar above the image shows plant kW against the contract.
- A tint caption appears on hot afternoons (outdoor temperature >= 33 °C).

The floor plan follows the plant's material flow (office at the front, logistics on the right,
utilities in the back-left corner); see
[Plant layout and process flow](simulator.md#plant-layout-and-process-flow).

The illustration is decorative; only the anchors carry meaning. Swapping the image means editing
`layout.yaml` only (the `image` name and the anchor positions). The illustration was generated with
an AI image model (OpenAI, via Codex CLI) from a written brief, contains no text, and depicts no
real site. The Overview moved to `/overview`.

#### Equipment markers

Every sub-metered load has a small dot at its position in `config/layout.yaml` (`equipment:`),
coloured by state: green running, amber idle, grey off. A load with an open detection gets a
red pulsing dot and a chip with its id; the reason is shown on its board's label. Hovering a dot
shows the load's name, kW and state.

## Single-line diagram

At the bottom of the Demand page, an SVG single-line diagram shows the electrical path: utility
supply, main bus, six distribution boards, then the sub-metered loads. It is rendered directly as
SVG from the tick state (no charting library).

- Line width follows board loading.
- Colours follow loading against the 90% warning level and the contract.
- Load boxes show RUNNING, IDLE or OFF, and go red when a detection is open on that load.

### Overview and charts

The Overview load chart shows the last 10 hours and 2 hours ahead, not the whole day. A "now" line
marks the replay clock. Detections from rules and baselines are marked on the chart: a shaded
event span and a dotted "detected" line at the time the detector fired. The Demand chart carries
the same markers. The Anomalies evidence chart never shows readings after the replay clock.

### Demand

The what-if is the hero card at the top. For S2 (staggered start-up) it shows the peak
15-minute demand falling by 183 kW, from 1,324 to 1,142 kW (below the 1,250 kW contract), and the penalty avoided:
74.4 kW excess in the summer off-peak period x NT$44.70 x 2 ≈ **NT$6,652 (US$208) for the month**
(simulated). It is computed from the database's own seed and precomputed at start-up.

The load-shed playbook shows "Need to shed X kW", then "covered" or "not enough" depending on
whether the listed actions add up. The shed shares are labelled as **assumptions**: EV chargers
100%, burn-in rooms 35%, chillers 4%, air compressors 3.5%.

### Equipment

Cards with an active alert are sorted first and show the reason. Wording follows the plant model:
"sub-metered loads" and "distribution board".

### Anomalies

Each detection row has a layer tag and a severity chip, plus an impact column using the tariff
above. The scores table is folded into a details panel, with the note that it is scored on the
same synthetic plant the thresholds were tuned on.

### Forecast

The page is named "Forecast" and labels avoid the term "AI". Columns use plain English headers
(for example "typical error" instead of MAE) and a one-line takeaway sits above the table.

The **Model shown** dropdown picks which model's forecasts the Forecast page draws (default:
lightgbm, the primary model). The first chart is "Next 3 hours" (it used to be the next hour): the
forecast issued at the last completed interval, with its P10-P90 band. The accuracy table has a
WAPE column (total absolute error over total demand) next to the typical error.

The **Model comparison** card has one row per model (profile, linear, hgb, lightgbm, ensemble) with
the columns 1 h error, 1 h pinball, 1 h in band, 3 h error, 3 h peak error / timing and alarm lead per
exceedance (minutes ahead for each real episode). A one-line verdict sits above it and the primary model
(lightgbm, the one the dashboard and alerts use) is marked. See
[forecasting.md](forecasting.md#model-comparison).

## Design choices

- **No look-ahead.** A detection appears at its `detected_at` time, not at its start. Batch
  detectors (nightly CUSUM, daily ML) therefore show up the morning after, and rules show up once
  they could be sure. The replay never shows something before it could have been known; see
  [anomaly_detection.md](anomaly_detection.md).
- **Demand-controller projection.** The projected 15-minute demand is
  `(kWh so far + present load x remaining minutes) / 15`, the same estimate a demand controller
  would make mid-interval. It drives the contract-usage and headroom figures and the banner.
- **Forecast as issued.** The next-3-hour forecast on screen is the one issued at the last completed
  15-minute interval, never a newer one.
- **Static versus live.** Most pages refresh on every clock tick; the History heatmap and monthly
  chart are computed once from the whole year.

## Performance

- At start-up the plant database is attached read-only into an in-memory DuckDB, which builds
  `plant_minute`, `plant_interval`, `meter_hour` and a time-ordered `reading_window` table
  restricted to the replay windows (8 days before to 1 day after each window). The source file is
  never modified.
- Detections are loaded once and sliced by detection time.
- One `TickState` is computed per instant and shared by the banner and the page.
- What-ifs are precomputed at start-up; the history ranking is cached per hour.
- Typical per-tick callback time is under ~250 ms on a laptop.

## Limitations

- The data is replayed from a pre-built database; nothing is measured live.
- The what-if is a re-simulation of one scenario, not a general optimiser.
- Thresholds and shed shares are illustrative; the tariff follows Taipower's published
  structure and prices but only models a regular contract, and the US$ rate is illustrative.
