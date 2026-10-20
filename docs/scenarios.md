# Scenario engine

The scenario engine injects labelled incidents into the simulated year. Each incident is described in
a YAML file, changes the data at the level where it physically happens, and produces ground-truth
labels used later to score anomaly detection and forecasting. All data is synthetic.

## Where each event type acts

| Stage | Event types | Effect |
|---|---|---|
| Weather, before any equipment model | `heat_wave` | Adds a temperature delta, so chillers, cooling tower, dryer and compressors react through their normal models. |
| Compressed-air demand, before the compressor split | `air_leak` | Adds kW to the air demand; the fixed/VSD compressor split and the dryer respond naturally. |
| Electrical derivation, per feeder | `capacitor_fault` | Replaces the capacitor compensation (normally 55%) on one feeder, so reactive power is no longer cancelled and PF drops. |
| Equipment kW, per meter | `simultaneous_start`, `left_running` | Overrides the kW profile of named meters in a time window. |

The temperature delta feeds the demand formulas in `simulator/equipment.py`. Chiller demand is
`(15 + 11*max(T-20,0) + 90*activity) * (1 + 0.05*max(T-32,0))` kW (COP drops 5% per degree above
32 C). Compressor demand is multiplied by `1 + 0.01*max(T-30,0)`.

## YAML format

One file per scenario in `config/scenarios/`. Unknown keys are rejected. `caption` is a one-line summary (maximum 90 characters) shown in the dashboard clock bar.

```yaml
id: S2                          # S1..S99, unique
title: Monday morning simultaneous start
description: >                  # the story, shown in the dashboard
  Operators switch on all machines at 08:00 sharp.
caption: "08:00, everything starts at once"   # one line, max 90 chars, shown in the clock bar
replay: {start: 2025-06-16T06:00, end: 2025-06-16T11:00}   # window for the simulated-clock replay
events:
  - type: simultaneous_start
    at: 2025-06-16T08:00
    meters: [IM-01, IM-02, IM-03, IM-04, RF-01, RF-02, RF-03, WS-01, CH-02, AC-02]
what_if:                        # free-form numeric levers for the dashboard
  stagger_minutes: 15
```

## Event types

| Type | Fields | Label |
|---|---|---|
| `simultaneous_start` | `at`, `meters` (at least 2) | `SIMULTANEOUS_START` |
| `heat_wave` | `start` (date), `days` (1-14), `peak_delta_c` (above 0, up to 10) | `HEAT_WAVE` |
| `air_leak` | `start`, `full_at`, `repaired_at`, `max_kw`; needs `start < full_at <= repaired_at` | `AIR_LEAK` |
| `left_running` | `meter`, `start`, `end`, `level` (share of rating, above 0 up to 1) | `OFF_SCHEDULE_RUNNING` |
| `capacitor_fault` | `feeder`, `start`, `end`, `compensation` (0 up to below the normal 0.55) | `LOW_POWER_FACTOR` |

Unknown meters or feeders raise an error. A simultaneous start forces each meter off for 3 hours
before `at`, then holds a category-specific start-up level for 20-45 minutes (for example a chiller at 45% of rating for 30 minutes, a cold injection molder at 95% for 40 minutes, a reflow oven at 95% for 45 minutes).

## Ground truth

`ground_truth_events` holds one row per labelled event: `event_id`, `scenario_id`, `event_type`,
`meter_ids`, `start_ts`, `end_ts`, `severity`, `description`. Event types are `SIMULTANEOUS_START`,
`HEAT_WAVE`, `AIR_LEAK`, `OFF_SCHEDULE_RUNNING`, `LOW_POWER_FACTOR` and `DEMAND_EXCEEDANCE`.

`DEMAND_EXCEEDANCE` rows are not written in YAML. After the simulation, every plant 15-minute demand
interval above the 1,250 kW contract is labelled automatically and attributed to the overlapping
scenario event, otherwise to `BASE`. Each interval is its own row with meter `PLANT` and severity
high.

The `scenarios` table stores `scenario_id`, `title`, `description`, `caption`, `replay_start`, `replay_end` and
`what_if` (the levers as JSON text, for example `{"stagger_minutes": 15.0}`).

## The six scenarios

Measured results of the default run (seed 42, 2025, all scenarios):

| ID | Dates | Story | Caption | Measured effect |
|---|---|---|---|---|
| S1 | 2025-08-04 to 08-10 | Normal week | Normal week: the baseline | Reference, no events. |
| S2 | Mon 2025-06-16 08:00 | 10 machines (IM-01..04, RF-01..03, WS-01, the large chiller CH-02 and the standby compressor AC-02) start together | 08:00, everything starts at once: 1,324 kW, above the contract | 15-min demand 1,324 kW (peak interval 08:15) vs about 1,155-1,170 kW on previous Mondays; two intervals (08:00-08:30) above the 1,250 kW contract. What-if: stagger by 15 min gives 1,142 kW (-183 kW), below the contract. The large chiller CH-02, once started, stays on at its minimum load (about 75 kW) until mid-morning instead of stopping after the surge. |
| S3 | Heat wave 2025-07-22 to 07-24, up to +5.5 C | Chillers derate and compressors work harder | Heat wave: sustained overruns are warned 30 to 75 minutes ahead | Daily peaks 1,209 / 1,263 / 1,267 kW on Jul 22 / 23 / 24 (maximum temperature 39.9 C); 21 intervals above contract across the afternoons of Jul 23 and 24. Demand hovers 0-1.5% above the contract in episodes. |
| S4 | Air leak from 2025-09-01, full 18 kW by 09-21, repaired 09-29 10:00 | Slowly growing leak, visible in the Sunday night load | Slow air leak: compressors draw 18 kW more around the clock, caught by the baseline | Weekday-night (02:00-04:00) compressor load 96 -> 114 kW across the leak, back to 96 kW after repair; Sunday nights 53 -> 66 kW. |
| S5 | RF-02 left running Fri 2025-10-17 20:30 to Mon 10-20 07:15 at 36% rating | Reflow oven left in standby all weekend (it is used on Saturday, never switched off) | Oven left on all weekend: 4.5x the normal weekend energy | About 1,556 kWh that weekend vs about 340-350 kWh on a normal weekend; the off-schedule rule raises two episodes, Friday night and Saturday evening to Monday. |
| S8 | Capacitor bank fault on MDB-3, 2025-11-03 09:00 to 11-12 16:00 | Power-factor correction trips | Capacitor bank trips: power factor 0.96 to 0.84 | Daytime feeder power factor drops from about 0.96 to about 0.85 (Sunday about 0.82). |

## How to run

```bash
python -m factory_energy simulate --scenarios all --out data/plant.duckdb --force     # default
python -m factory_energy simulate --scenarios none --out data/plant.duckdb --force    # baseline only
python -m factory_energy simulate --scenarios S2,S3 --out data/plant.duckdb --force   # a subset
```

An unknown scenario id exits with an error. Output is deterministic for a given seed, and any given day is identical regardless of the simulation window.

## Adding a scenario

Drop a new YAML file into `config/scenarios/` with a unique `id` (`S` plus one or two digits) and one
or more events from the table above. It is picked up automatically by `--scenarios all` and by id.
Run `pytest` to validate the file against the schema before generating data.
