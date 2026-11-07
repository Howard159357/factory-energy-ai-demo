# EQ-04 Wave Solder Machine Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-04 |
| Revision | A |
| Owner role | Assembly process engineer |
| Applies to | WS-01 |

## Purpose and scope

This manual covers the wave soldering machine WS-01 on board MDB-2. The machine runs the day shift on workdays. Its solder pot and preheater are thermal loads, and its start-up is one of the machines that was part of the S2 simultaneous start incident.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| WS-01 | Wave Soldering Machine | MDB-2 | 35 | 0.97 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 35 kW unit |
|---|---|---|
| Preheat (30 min) | 90% | 31.5 |
| Running | 55% | 19.2 |
| Lunch | 45% | 15.8 |
| Off | 3% | 1.1 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 35 kW | 7.0 | 1.1 |

At 3% the machine is at the OFF boundary and is reported as OFF.

## Start-up sequence

### Timing

Preheat lasts 30 minutes at 90% of rating. Start the machine so the preheat ends when the first assembly is ready.

### Sequence

1. Check solder pot level and flux supply.
2. Switch on the machine and confirm the preheat level on the meter.
3. After 30 minutes confirm the power falls to the running level of 55%.
4. Release production.

### Position in the start-up order

WS-01 is placed in the last group in SOP-01 to avoid adding to the early demand peak.

## Shutdown

At the end of the day shift, drain the flux system and switch the machine off. It returns to 3% when off. It is also switched off over the weekend. See SOP-02.

## Power factor behaviour

The base power factor is 0.97. The load is mostly resistive, so the power factor does not change much between states.

## Energy-saving notes

- Start WS-01 as late as the preheat allows.
- Switch off rather than leave on between batches of unrelated work.
- Use the lunch level (45%) rather than the running level during the break.
- Keep it out of the first group at start-up.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check solder pot level and flux supply. |
| Weekly | Clean fingers and conveyor. |
| Monthly | Remove dross and inspect the preheater. |
| Quarterly | Verify solder pot temperature control and preheater power against the sub-meter reading. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Simultaneous start rule | Fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes (reflow ovens, molders, wave solder, chillers, fixed compressors). It fires about 5-8 minutes after the start. Counts toward the six-machine total. |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. Triggered if WS-01 runs outside the day shift for 120 minutes or more. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-02 Weekend Shutdown (per-area shutdown checklist)
- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
