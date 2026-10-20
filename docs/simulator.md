# Plant simulator

The simulator generates one year (or any number of days) of 1-minute electrical data for the
fictional DemoTronics plant: 6 feeder meters plus 23 equipment sub-meters. All data is synthetic.

## Purpose and determinism

The simulator is the data source for the energy engine, forecasting, anomaly detection and the
dashboard. It is fully deterministic: the same `--seed`, start date and number of days give
identical data. Every random quantity draws from its own stream, created by
`rng_for(seed, *keys)` (a `SeedSequence` seeded with the seed plus a CRC32 of each key, for example
`("RF-01", "load")` or `("schedule", "overtime")`). Streams are independent per meter and per
purpose, so changing one meter or adding a new one does not shift the random numbers of the others.

Randomness is also window-independent. Draws are keyed by calendar day (`RandomSource` in
`timeline.py`), and multi-day processes (weather persistence, burn-in batches) are integrated from a
fixed epoch, 2020-01-01. The simulator additionally simulates one padding day on each side and trims
it (`generator.padded`). As a result any given day is identical regardless of the simulation window
(`--start` / `--days`). Only the absolute kWh register value depends on the window start; its deltas
do not.

## Pipeline

```text
Timeline (1-minute grid)
  -> ProductionPlan (day types, holidays, shifts, overtime, start stagger, lunch)
  -> outdoor temperature
  -> per-category equipment models (kW per sub-meter)
  -> feeder kW = sum(sub-meters) + unmetered load
  -> electrical derivation (PF, kvar, capacitor compensation, voltages, currents, kWh register)
  -> DuckDB tables
```

1. **Timeline**: whole days at 1-minute resolution in plant local time.
2. **ProductionPlan**: day type per date (workday, Saturday, Sunday, holiday from
   `config/factory.yaml`), overtime on 60% of workdays (random per day), start-time stagger per
   machine, lunch mask, office occupancy and 0..1 activity levels for SMT, molding and assembly.
3. **Outdoor temperature**: subtropical season (mean 23.5 C, +/-6 C, peak late July), a diurnal
   swing of 4 C peaking at 14:30, and persistent day-to-day weather anomalies.
4. **Equipment models**: one function per category (table below).
5. **Feeders**: sum of the feeder's sub-meters plus an unmetered load (lighting, AOI, AHU fans,
   office), which keeps `feeder - sub-meters >= 0`.
6. **Electrical derivation**: equipment PF is category-specific and worsens at light load; kvar is
   `kW * tan(acos(PF))`. Feeders sum sub-meter kvar plus unmetered kvar (PF 0.90), then 55% is
   cancelled by capacitor banks. Apparent power gives PF, three line voltages (380 V nominal,
   slight sag with load, noise, small per-phase offsets) and three phase currents
   (`S / (sqrt3 * V)` with about 1% imbalance). The kWh register is the running integral of kW from
   a random starting value.
7. **Storage**: each meter is written to DuckDB as it is generated.

## Why these ratings

Ratings follow typical connected loads for this kind of plant: reflow oven 70 kW, injection molders
40 kW (150 T), 65 kW (250 T) and 90 kW (350 T), burn-in room 60 kW, wave solder 35 kW, chillers
200 and 250 kW input, and compressors 75 / 75 / 55 kW. The sum of the ratings is about 1,480 kW
against a 1,250 kW contract, so the plant relies on diversity (about 0.75) at its summer peaks of
1,100-1,180 kW: not everything runs at full rating at the same time, which is exactly why a
simultaneous start is dangerous.

## Plant layout and process flow

The six distribution boards follow the material flow of a PCBA-plus-housing electronics plant,
so the plant map reads the way a plant engineer expects:

```
receiving dock -> raw-material warehouse (reels, bare boards, resin)
   |-- SMT hall (MDB-1): paste print -> pick-and-place -> reflow -> AOI -> PCBA buffer
   '-- injection moulding (MDB-3): dryers -> moulders -> housings
                |                                   |
        assembly & test (MDB-2): final assembly -> burn-in -> functional test -> packing
                |
        finished-goods warehouse -> shipping dock
```

- **Front**: the office and facilities block (MDB-6: offices, reception, server room) faces the
  visitor parking and the EV charging bays. People enter here; material never does.
- **Right side**: logistics. The receiving dock and raw-material warehouse at the front, the
  finished-goods warehouse and shipping dock at the back, one truck yard along the wall, so the
  flow is a U and never crosses the people entrance.
- **Middle row**: the SMT hall (MDB-1) next to the raw-material warehouse, where component reels
  and bare boards come from, and the injection-moulding hall (MDB-3) on the other side with its
  resin silos outside the wall.
- **Back centre**: assembly and test (MDB-2) downstream of both halls, with packing against the
  finished-goods warehouse.
- **Back-left corner**: the utility plant, compressors (MDB-5) and chillers (MDB-4), behind the
  moulding hall. It is the noisy corner, as far from the office as possible, and next to the
  biggest consumers of compressed air and chilled water (moulds and reflow ovens), which keeps
  the pipe runs short. The cooling tower and the outdoor HVAC units stand outside this wall.

The warehouses and docks carry no distribution board of their own (their lighting and dock
equipment sit on MDB-6), so they appear on the illustration but not in the meter list.

## Equipment models

| Category (meters) | Behaviour |
|---|---|
| Reflow oven (RF-01..03) | Follows its SMT line. Switches on 35-60 min before the line starts, heats at 80% of rated for 45 min (95% when started cold in a scenario), then 44% while the line runs and 36% idle; stays on 30 min after the line stops. |
| SMT line (SMT-L1..3) | 72% of rated when running, 30% at lunch, 4% standby. Lunch is staggered: L1 11:45, L2 12:00, L3 12:15. |
| Burn-in (BI-01..02) | Independent of production: back-to-back 24-48 h batches at about 85% with a 2 h ramp (45%) and a 1 h unload tail (40%), 2-6 h gaps, 8% idle. |
| Wave solder (WS-01) | 30 min preheat at 90%, then 55% (45% at lunch); 3% off. |
| ICT/FCT test bank (TEST-01) | `15% + 60% * SMT activity`. |
| Injection molder (IM-01..04) | 40 min barrel heat-up at 78% of rated (95% when started cold in a scenario), then 53% steady (normal heat-up is about 1.45x steady); 3% off. |
| Chiller (CH-01 200 kW, CH-02 "Large" 250 kW) | Share of the cooling demand `(15 + 11*max(T-20,0) + 90*activity) * (1 + 0.05*max(T-32,0))` kW (last factor: COP derating of 5% per degree above 32 C). CH-01 takes it up to 180 kW; CH-02 stages in on the remainder (clipped to 60-240 kW). |
| Cooling tower (CT-01) | `10% + 40% * chiller load / 400 + 15% * humid-heat factor` of rated. |
| Fixed compressors (AC-01, AC-02) | AC-01 is the base machine (load/unload 33-100%); AC-02 is the lag machine and only runs when demand exceeds AC-01 plus the VSD trim. |
| VSD compressor (AC-03) | Trim machine: 3 kW idle, 5 kW plus the demand above 70 kW (capped at 50 kW). |
| Air dryer (DR-01) | `30% + 45% * airflow + 15% * ambient` of rated; airflow follows compressed-air demand. |
| Server room (DC-01) | Near-constant 82-88% of rated, slightly higher in hot weather. |
| EV chargers (EV-01) | 4 chargers; on workdays arrivals 07:30-09:30, 1-4 h sessions (15% skip); 0-1 session on Saturdays. |

Machines started by hand that the schedule does not need keep running: a chiller is held at 30% of
rating for 150 minutes after its start-up (`HOLD_AFTER_START` in `simulator/scenarios.py`).

Compressed-air demand is `(35 kW + 120 kW * (0.3 SMT + 0.5 molding + 0.2 assembly activity) + leak) * (1 + 0.01*max(T-30,0))`; the last factor is the hot intake air penalty.

## Schedule rules

From `schedule.build_plan` (day shift 08:00-17:00, overtime until 20:00, lunch 12:00-13:00):

| Day type | Running |
|---|---|
| Workday | SMT-L1, IM-03, IM-04: around the clock (24 h from shift start). SMT-L2: day shift, or until 20:00 on overtime days. SMT-L3 and WS-01: day shift. IM-01, IM-02: until 20:00. Office 07:30-17:30. |
| Saturday | Half plant: SMT-L1, SMT-L2, IM-01, IM-02 on the day shift; office at 30% until lunch. |
| Sunday, holiday | Only base load: burn-in, chillers, compressors, server room (no production lines). |

Start times are staggered: SMT lines -10..+10 min, wave solder -5..+15 min, molders 0 to 75 min
early (barrel preheat). Reflow oven lead time is drawn per start inside its own model.

## Output tables

| Table | Columns |
|---|---|
| `meter_master` | `meter_id`, `display_name`, `meter_type` (FEEDER/EQUIPMENT), `feeder_id`, `category`, `rated_kw`, `include_in_plant_total`, `enabled` |
| `meter_reading_minute` | `meter_id`, `ts`, `kwh`, `kw`, `pf`, `r_v`, `s_v`, `t_v`, `r_a`, `s_a`, `t_a`, `status` (key: `meter_id`, `ts`) |
| `production_calendar` | `day`, `day_type`, `overtime`, `holiday_name` |
| `weather_minute` | `ts`, `temp_c` |
| `ground_truth_events` | `event_id`, `scenario_id`, `event_type`, `meter_ids`, `start_ts`, `end_ts`, `severity`, `description` (see [scenarios](scenarios.md)) |
| `simulation_runs` | `run_id`, `seed`, `start_day`, `days`, `simulator_version`, `created_at` |

`pf` is NULL when apparent power is below 0.5 kVA (the meter is idle). The plant total is the sum
of the six feeders (`include_in_plant_total`); sub-meters are never added to it.

The columns mirror what a typical panel-mounted three-phase power meter exposes: voltage inputs
V1-V3 (+ neutral), current inputs from clamp-on CTs (I11/I12 ... I31/I32), and an RS-485 port
polled over Modbus RTU by a gateway. A real acquisition loop reads the holding registers for
per-phase V and A, total kW, power factor and the cumulative kWh counter about once a minute;
15-minute demand is then derived from kWh differences rather than from instantaneous kW, which
is what the simulator reproduces (`kwh` is cumulative, `kw` is the minute average).

## Validated properties (default run)

Seed 42, start 2025-01-01, 365 days, all scenarios (see [scenarios](scenarios.md); a run with
`--scenarios none` differs slightly):

- 29 meters x 525,600 rows = 15,242,400 rows in about 57 s.
- Plant energy about 5,300 MWh per year; night base load about 500 kW; load factor 0.45.
- Energy share by area: HVAC 25%, compressed air 19%, assembly & test 19%, injection molding 17%,
  SMT 13%, facilities 8%.
- Normal daily peaks by season: January median about 900 kW, July median about 1,070 kW; summer
  normal days peak at 1,100-1,180 kW. Only scenario days exceed the 1,250 kW contract (warning
  line at 90% = 1,125 kW).
- Feeder minus its sub-meters is >= 0 at every minute.
- The kWh register delta matches the kW integral within 0.0001%.
- Phase current matches `P / (sqrt3 * V * PF)` within 0.3%.
- Hourly correlations: chillers vs temperature strongly positive; cooling tower vs chillers,
  compressors vs production and dryer vs compressors also strongly positive; burn-in is independent
  of the production schedule (near zero).
- Reflow ovens switch on 35-60 min before their SMT line; molder heat-up (40 min) draws about 1.45x the
  steady load; SMT lines take staggered lunch breaks (11:45 / 12:00 / 12:15).

## How to run

```bash
python -m factory_energy check-config
python -m factory_energy simulate --start 2025-01-01 --days 365 --seed 42 --out data/plant.duckdb --force
python -m factory_energy simulate --scenarios none --out data/baseline.duckdb --force   # all | none | S2,S3
```

`--force` replaces an existing database file. The command prints the row count, peak demand, night
base load, plant energy and elapsed time.

## Scenarios

Incident injection (S1-S5, S8) and the labelled `ground_truth_events` rows are described in
[scenarios.md](scenarios.md). Use `--scenarios none` for the normal-operation baseline only.
