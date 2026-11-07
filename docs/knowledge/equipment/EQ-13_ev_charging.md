# EQ-13 EV Charging Bank Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-13 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | EV-01 |

## Purpose and scope

This manual covers the staff EV charging bank EV-01 on board MDB-6. It has four chargers of 7 kW each. It is the first and simplest load-shed action: pausing it removes all of its load.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| EV-01 | EV Charging Bank (4 x 7 kW) | MDB-6 | 28 | 0.98 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 28 kW unit |
|---|---|---|
| No sessions | 0% | 0.0 |
| One charger active (7 kW) | 25% | 7.0 |
| Two chargers active | 50% | 14.0 |
| Three chargers active | 75% | 21.0 |
| All four active | 100% | 28.0 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 28 kW | 5.6 | 0.8 |

Workday arrivals are between 07:30 and 09:30, with sessions of 1-4 hours. On Saturdays there are 0 to 1 sessions. One charger in use is 7.0 kW, above the 5.6 kW RUNNING boundary.

## Start-up sequence

### Sequence

Chargers start when a vehicle connects. There is no staged start.

### Morning arrivals

Arrivals between 07:30 and 09:30 coincide with the morning start-up of production. Pause readiness matters during this window.

## Shutdown

Sessions end when the vehicle is full or disconnected. A pause can be applied by the facilities engineer at any time.

## Power factor behaviour

The base power factor is 0.98. The chargers add little reactive power.

## Energy-saving notes

- Pause charging when demand is projected to exceed the contract.
- Pause charging before the start of hot afternoon peaks.
- Resume only when projected demand is back below 1,125 kW.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check charger cables and connectors. |
| Monthly | Inspect the pause control. |
| Quarterly | Test the pause function and confirm the meter returns to 0. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. Pause is the first action in the playbook (100% of present load). |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. Sessions on Sundays would be flagged. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-06 Heat Wave Pre-cooling (high exceedance probability on hot afternoons)
