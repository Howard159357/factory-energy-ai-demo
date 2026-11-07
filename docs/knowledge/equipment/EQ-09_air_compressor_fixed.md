# EQ-09 Fixed-Speed Air Compressor Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-09 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | AC-01, AC-02 |

## Purpose and scope

This manual covers the two fixed-speed air compressors on board MDB-5 (Compressed Air). AC-01 is the base machine and AC-02 is the lag machine. They work with the VSD trim machine AC-03 (EQ-10) and the air dryer DR-01 (EQ-11).

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| AC-01 | Air Compressor 1 (Fixed Speed) | MDB-5 | 75 | 0.85 |
| AC-02 | Air Compressor 2 (Fixed Speed) | MDB-5 | 75 | 0.85 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 75 kW unit |
|---|---|---|
| AC-01 load/unload range | 33-100% | 24.8-75.0 |
| AC-02 lag machine | Runs only when demand exceeds AC-01 plus the trim | 0.0-75.0 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 75 kW | 15.0 | 2.2 |

AC-01 swings between 33% and 100% as it loads and unloads. AC-02 runs only when demand exceeds AC-01 plus the trim machine. Hot intake air adds 1% per degC above 30 degC. Compressed-air demand rises with production, and molding weighs most.

## Start-up sequence

### Sequence

1. Check oil level and drain condensate.
2. Start AC-01 as the base machine.
3. Let AC-03 trim the demand.
4. Start AC-02 only if demand requires it.

### Group start

After a weekend AC-02 is part of the first group in SOP-01.

## Shutdown

Unload, allow the cooldown run, then stop. AC-02 stops first when demand falls. Compressors keep running on Sundays for maintenance loads.

## Power factor behaviour

The base power factor is 0.85 at full load and falls by about 0.12 at no load. A compressor running unloaded for long periods therefore lowers MDB-5 PF.

## Energy-saving notes

- Lower the compressed-air pressure by 0.5 bar to shed about 3.5% of present compressor load.
- Fix leaks; the night load (02:00-05:00) is the baseline for finding them (SOP-04).
- Keep AC-02 off unless demand needs it.
- Keep intake air cool.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check oil, drains and filters. |
| Monthly | Inspect belts or couplings and intake filter. |
| Quarterly | Test load/unload set points. |
| Quarterly | Walk the network for leaks. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. Pressure reduction is a playbook action. |
| Simultaneous start rule | Fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes (reflow ovens, molders, wave solder, chillers, fixed compressors). It fires about 5-8 minutes after the start. Fixed compressors count toward the six-machine total. |
| Air-leak baseline | Compares compressor night load (02:00-05:00) with the median of the last 6 similar nights; CUSUM k = 0.5, h = 8 robust sigmas, and more than 3 kW above expectation. A rising night load points to a leak. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-5. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-04 Compressed Air Leak (night-load triggered inspection)
