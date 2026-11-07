# SOP-07 Meter Data Quality

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-07 |
| Revision | A |
| Owner role | Energy coordinator |
| Applies to | All feeder meters (MDB-1 to MDB-6) and all equipment sub-meters |

## Purpose

This procedure describes the daily checks that show whether the meter data can be trusted, and what to do when it cannot. Demand status, forecasts and alarms depend on correct readings.

## Data basics

- Meters report every 60 seconds.
- A meter is stale after 180 seconds without a reading.
- The kWh register is a cumulative counter and should only increase.
- The six feeders (MDB-1 to MDB-6) add up to the plant total.
- Sub-meters sit beneath their feeders and must not add up to more than the feeder.

## Checks

### Check 1: stale meters

| Item | Detail |
|---|---|
| Rule | No reading for more than 180 seconds |
| Typical causes | Communication fault, gateway restart, power loss at the meter |
| Action | Check the gateway, then the meter wiring. Record the start and end of the outage |

While a feeder is stale, demand status for the plant may be understated. Treat demand with caution and apply SOP-03 on caution if the load is known to be high.

### Check 2: kWh register decreases or resets

| Item | Detail |
|---|---|
| Rule | The register value goes down, or returns to zero |
| Typical causes | Meter replacement, meter reset, rollover, or corrupted reading |
| Action | Do not compute energy across the decrease. Mark the interval as invalid. Record the old and new register values and the time |

A reset, if not handled, can create a very large negative or positive energy value for one interval. Confirm that the interval is excluded from bill reconciliation and from baselines such as the night-load comparison (SOP-04).

### Check 3: feeder minus sub-meters must be at least zero

For each feeder, the feeder reading minus the sum of its sub-meters must be at least zero. The difference is the unmetered load, such as lighting and small power.

| Result | Meaning | Action |
|---|---|---|
| At or above zero | Normal | None |
| Below zero | Sub-meters sum to more than the feeder: data fault | Check for a stale feeder, a swapped meter id, or a scaling error |

Check the meter ids, for example RF-01 to RF-03 and SMT-L1 to SMT-L3 on MDB-1, against the board assignment in the configuration.

### Check 4: gaps

| Item | Detail |
|---|---|
| Rule | Missing 60-second readings, even if shorter than the stale limit |
| Action | Count missing readings per day per meter. Note gaps that fall inside a 15-minute demand interval, because they bias the interval |

Short gaps may be filled in analysis with an indication that the data was estimated. Long gaps are not filled; the interval is marked incomplete.

## Escalation

| Finding | Who | When |
|---|---|---|
| One stale meter | Facilities engineer | Same shift |
| Several stale meters or a feeder | Facilities engineer and energy coordinator | Immediately |
| Register reset | Energy coordinator | Same day |
| Negative residual on a feeder | Energy coordinator | Same day |

## Effects on other procedures

| Procedure | Effect of bad data |
|---|---|
| SOP-03 | Wrong projected demand |
| SOP-04 | False or missed leak signal from the night load |
| SOP-05 | False or missed low power factor event |

## Records

The energy coordinator keeps a data quality log with the meter id, the type of finding, the start and end time, the action taken and the closure date. The log is reviewed in the monthly energy review (EM-01).

## Related documents

- EM-01 Energy Policy
- EM-02 Demand Management
- EM-04 Glossary
