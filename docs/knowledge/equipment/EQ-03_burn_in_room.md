# EQ-03 Burn-in Room Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-03 |
| Revision | A |
| Owner role | Test engineer |
| Applies to | BI-01, BI-02 |

## Purpose and scope

This manual covers the two burn-in rooms on board MDB-2 (Assembly and Test). Burn-in rooms run long thermal stress batches on finished boards and are independent of the production schedule: they run on nights, weekends and Sundays as well as workdays. Because batches are long, loading time is the main lever for energy and demand.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| BI-01 | Burn-in Room 1 | MDB-2 | 60 | 0.96 |
| BI-02 | Burn-in Room 2 | MDB-2 | 60 | 0.96 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 60 kW unit |
|---|---|---|
| Batch hold (24-48 h) | about 85% | 51.0 |
| Ramp at batch start (2 h) | 45% | 27.0 |
| Unload tail (1 h) | 40% | 24.0 |
| Idle between batches | 8% | 4.8 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 60 kW | 12.0 | 1.8 |

Batches last 24-48 hours at about 85%. The gap between batches is 2-6 hours. A room in the idle state is above 3% of rating (1.8 kW) and is therefore reported as IDLE.

## Start-up sequence

### Batch loading

Boards are loaded, the chamber door is closed and the room ramps for 2 hours at 45% before reaching the batch level of about 85%.

### Sequence

1. Confirm the previous batch is fully unloaded.
2. Load the new batch and verify the connection of all fixtures.
3. Start the batch program and confirm the meter shows the ramp level.
4. Record the planned finish time.

### Loading discipline

Do not load both rooms in the same quarter hour on a hot afternoon. If demand is high, the next loading can be delayed; see the playbook in EM-02.

## Shutdown

At the end of a batch the room unloads for 1 hour at 40%, then returns to idle at 8%. A room is not powered off between batches. During Sunday and holiday maintenance, burn-in continues as normal.

## Power factor behaviour

The base power factor is 0.96. The load is a mix of heaters and fans, and the PF is stable across the batch. A fall in MDB-2 PF is more likely to come from the test bank (EQ-05) or from the capacitor bank than from the burn-in rooms.

## Energy-saving notes

- Delay the next burn-in loading when demand is high; the playbook assumes 35% of present burn-in load can be shed within minutes.
- Aim to load a new batch during off-peak hours when the batch plan allows.
- Shorten the gap between batches only when a loading slot is genuinely needed.
- Never interrupt a batch in progress solely to save energy.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check chamber door seals and temperature display. |
| Weekly | Inspect fixtures and fan operation. |
| Monthly | Clean filters and check heater elements. |
| Quarterly | Calibrate chamber temperature and compare batch kW with the expected level of 85% of rating. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. Delaying the next loading is the second shed action in the playbook. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-2 as a whole. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-06 Heat Wave Pre-cooling (high exceedance probability on hot afternoons)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
