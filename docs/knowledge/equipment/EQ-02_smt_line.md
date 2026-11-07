# EQ-02 SMT Line Manual (Printer and Placement)

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-02 |
| Revision | A |
| Owner role | SMT process engineer |
| Applies to | SMT-L1, SMT-L2, SMT-L3 |

## Purpose and scope

This manual covers the printer and placement equipment of the three SMT lines on board MDB-1. The lines are small electrical loads compared with the reflow ovens, but they set the rhythm of the whole SMT area: when a line starts, its oven must already be hot, and its activity drives the ICT/FCT test bank (EQ-05).

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| SMT-L1 | SMT Line 1 Printer & Placement | MDB-1 | 18 | 0.90 |
| SMT-L2 | SMT Line 2 Printer & Placement | MDB-1 | 18 | 0.90 |
| SMT-L3 | SMT Line 3 Printer & Placement | MDB-1 | 18 | 0.90 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 18 kW unit |
|---|---|---|
| Running | 72% | 13.0 |
| Lunch | 30% | 5.4 |
| Standby | 4% | 0.7 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 18 kW | 3.6 | 0.5 |

Standby at 4% is only just above the 3% IDLE line, so a line in standby is reported as IDLE rather than OFF. Lunch is staggered: SMT-L1 at 11:45, SMT-L2 at 12:00 and SMT-L3 at 12:15, so the lines never drop together.

## Start-up sequence

### Timing

The line starts after its reflow oven has finished heat-up. The oven is switched on 35-60 minutes earlier (see EQ-01).

### Sequence

1. Confirm the oven for the line has reached its running level.
2. Power up the printer, then the placement machines.
3. Run the line-clearance check and load the first program.
4. Confirm the sub-meter shows the running level of 72% within a few minutes.

### Schedule

On workdays SMT-L1 runs around the clock; SMT-L2 runs the day shift (to 20:00 on overtime days); SMT-L3 runs the day shift. On Saturday only SMT-L1 and SMT-L2 run, on the day shift. Sundays and holidays have no SMT production.

## Shutdown

At the end of the run, clear the line and move the machines to standby before the oven stays on for its 30 minutes of tail time. For the weekend, power the line down fully as part of SOP-02.

## Power factor behaviour

The base power factor is 0.90. This is lower than the reflow ovens because the placement drives and vacuum pumps are motor loads. At standby the power factor is lower than at full load, by up to about 0.12 at no load. A drop in the MDB-1 board PF during a standby period is therefore normal and short; a sustained fall below 0.90 for 60 minutes is not.

## Energy-saving notes

- Keep the lunch stagger so the lines step down in sequence.
- Move idle lines to standby (4%) and not to lunch level (30%) when a long wait is planned.
- Do not start the third line before it is needed.
- Match the oven schedule to the line schedule; an oven hot for a line that is not running wastes more energy than the line itself.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check vacuum and air supply at the placement heads. |
| Weekly | Clean printer stencil station and inspect feeders. |
| Monthly | Inspect drive belts and lubricate guide rails. |
| Quarterly | Verify placement accuracy and compare running kW with the sub-meter record. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. SMT-L3 above 3.6 kW outside its day shift would be flagged. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-1 as a whole. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-02 Weekend Shutdown (per-area shutdown checklist)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
