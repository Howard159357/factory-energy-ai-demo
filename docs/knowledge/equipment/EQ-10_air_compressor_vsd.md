# EQ-10 VSD Air Compressor Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-10 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | AC-03 |

## Purpose and scope

This manual covers the variable-speed-drive (VSD) trim compressor AC-03 on board MDB-5. The VSD machine follows air demand, so it absorbs small changes while the fixed-speed machines stay at their set points.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| AC-03 | Air Compressor 3 (VSD Trim) | MDB-5 | 55 | 0.95 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 55 kW unit |
|---|---|---|
| Idle | 3 kW | 3.0 |
| Full load | 100% | 55.0 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 55 kW | 11.0 | 1.6 |

AC-03 draws 3 kW at idle and up to 55 kW at full load. It is the trim machine, with AC-01 the base machine and AC-02 the lag machine.

## Start-up sequence

### Sequence

1. Check oil, drain and drive cooling.
2. Start AC-03 so that it trims demand.
3. Confirm that its power follows the demand without hunting.

## Shutdown

Allow the drive to ramp down and stop normally. The VSD machine is the last to stop and the first to start.

## Power factor behaviour

The base power factor is 0.95 because the drive keeps the line-side current close to the voltage. At light load the PF falls, by up to about 0.12 at no load.

## Energy-saving notes

- Let AC-03 carry the variable part of the load instead of AC-02.
- Reduce the pressure set point by 0.5 bar to shed about 3.5% of present load.
- Fix leaks first; a VSD machine hides a leak by increasing speed.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check drive cooling and filters. |
| Monthly | Inspect drive and oil. |
| Quarterly | Verify drive parameters and idle consumption of 3 kW. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Air-leak baseline | Compares compressor night load (02:00-05:00) with the median of the last 6 similar nights; CUSUM k = 0.5, h = 8 robust sigmas, and more than 3 kW above expectation. The trim machine is first to show a leak. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-5. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-04 Compressed Air Leak (night-load triggered inspection)
