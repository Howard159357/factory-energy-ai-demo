# EQ-12 Server Room Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-12 |
| Revision | A |
| Owner role | IT infrastructure lead |
| Applies to | DC-01 |

## Purpose and scope

This manual covers the server room DC-01 on board MDB-6 (Facilities and Office). The server room is a continuous critical load. It is never part of any load-shed action.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| DC-01 | Server Room | MDB-6 | 25 | 0.95 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 25 kW unit |
|---|---|---|
| Normal | 82-88% | 20.5-22.0 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 25 kW | 5.0 | 0.8 |

Power is constant at 82-88% of rating and slightly higher in hot weather. It stays RUNNING at all hours.

## Start-up sequence

### Sequence

The server room is not stopped in normal operation. After a planned outage, bring up storage first, then compute, and confirm cooling is online.

## Shutdown

Only the IT infrastructure lead may order a shutdown, with prior notice to the shift supervisor.

## Power factor behaviour

The base power factor is 0.95 because the power supplies are power-factor corrected. It remains stable across the day.

## Energy-saving notes

- Keep hot and cold aisles separated.
- Raise the room setpoint only when approved by the IT infrastructure lead.
- Remove unused equipment.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check room temperature and alerts. |
| Monthly | Inspect cooling and power distribution. |
| Quarterly | Test backup power. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. The server room is on the never-shed list. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-06 Heat Wave Pre-cooling (high exceedance probability on hot afternoons)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
