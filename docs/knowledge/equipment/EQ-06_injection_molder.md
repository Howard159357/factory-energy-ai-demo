# EQ-06 Injection Molder Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-06 |
| Revision | A |
| Owner role | Molding process engineer |
| Applies to | IM-01, IM-02, IM-03, IM-04 |

## Purpose and scope

This manual covers the four injection molders on board MDB-3 (Injection Molding). Barrel heat-up is a large short-term load; steady running is lower. Molding also drives compressed-air demand more than any other process, so molder activity is visible on board MDB-5 as well.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| IM-01 | Injection Molder 1 (150T) | MDB-3 | 40 | 0.86 |
| IM-02 | Injection Molder 2 (150T) | MDB-3 | 40 | 0.86 |
| IM-03 | Injection Molder 3 (250T) | MDB-3 | 65 | 0.86 |
| IM-04 | Injection Molder 4 (350T) | MDB-3 | 90 | 0.86 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 40 kW unit | 65 kW unit | 90 kW unit |
|---|---|---|---|---|
| Barrel heat-up from warm (40 min) | 78% | 31.2 | 50.7 | 70.2 |
| Barrel heat-up from cold | 95% | 38.0 | 61.8 | 85.5 |
| Steady running | 53% | 21.2 | 34.5 | 47.7 |
| Off | 3% | 1.2 | 1.9 | 2.7 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 40 kW | 8.0 | 1.2 |
| 65 kW | 13.0 | 1.9 |
| 90 kW | 18.0 | 2.7 |

Heat-up draws about 1.45 times the steady power. IM-01 and IM-02 are 150T machines, IM-03 is 250T and IM-04 is 350T.

## Start-up sequence

### Timing

Molders start between 0 and 75 minutes before the shift for barrel preheat. Heat-up takes 40 minutes.

### Sequence

1. Check the hopper, dryer and mold clamp.
2. Switch on the barrel heaters and confirm the heat-up level on the meter.
3. Stagger the start of the four machines by 15 minutes (see SOP-01).
4. After 40 minutes confirm steady power before running production.

### Schedule

On workdays IM-03 and IM-04 run around the clock; IM-01 and IM-02 run until 20:00. On Saturday IM-01 and IM-02 run the day shift. On Sundays and holidays the molders are off.

## Shutdown

Purge the barrel, close the mold and switch the heaters off. At the end of a cycle the machine can be stopped; never stop it mid-cycle. For the weekend, all four molders are switched off as part of SOP-02.

## Power factor behaviour

The base power factor is 0.86, and falls by about 0.12 at no load compared with full load. A molder in a long hold at low power can therefore show a PF near 0.74. MDB-3 is therefore sensitive to its capacitor bank: in incident S8 a tripped bank took the board PF from 0.96 to 0.84. See SOP-05.

## Energy-saving notes

- Stagger molder start-up by 15 minutes; all four molders were part of the S2 incident, when ten machines started at once.
- Start the barrel preheat only as early as required.
- Do not leave idle molders hot between jobs.
- Reduce compressed-air consumption from the molders by checking blow-off nozzles.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check hydraulic oil level and barrel heater function. |
| Weekly | Inspect clamp, check cooling water flow. |
| Monthly | Clean filters and inspect hoses. |
| Quarterly | Check capacitor bank on MDB-3 and compare steady power with 53% of rating. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. Heat-up of several molders together is a leading cause of morning peaks. |
| Simultaneous start rule | Fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes (reflow ovens, molders, wave solder, chillers, fixed compressors). It fires about 5-8 minutes after the start. Molders count toward the six-machine total. |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. IM-01 and IM-02 above 20% of rating after 20:00 would be flagged. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. MDB-3 is the usual candidate. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-02 Weekend Shutdown (per-area shutdown checklist)
- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-05 Power Factor Check (capacitor bank verification)
