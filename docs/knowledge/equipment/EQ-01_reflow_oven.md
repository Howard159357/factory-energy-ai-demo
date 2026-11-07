# EQ-01 Reflow Oven Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-01 |
| Revision | A |
| Owner role | SMT process engineer |
| Applies to | RF-01, RF-02, RF-03 |

## Purpose and scope

This manual covers the three reflow ovens on board MDB-1 (SMT Area). Reflow ovens are heat-dominated loads: most of their energy goes into holding the process zones at temperature, so their power depends on whether boards are flowing, not on how many boards are inside. The ovens are the largest single block of load in the SMT area and the most common cause of avoidable weekend energy.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| RF-01 | Reflow Oven 1 | MDB-1 | 70 | 0.98 |
| RF-02 | Reflow Oven 2 | MDB-1 | 70 | 0.98 |
| RF-03 | Reflow Oven 3 | MDB-1 | 70 | 0.98 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 70 kW unit |
|---|---|---|
| Heat-up from warm | 80% | 56.0 |
| Heat-up from cold (after a long stop) | 95% | 66.5 |
| Running (line producing) | 44% | 30.8 |
| Idle or standby | 36% | 25.2 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 70 kW | 14.0 | 2.1 |

Heat-up lasts 45 minutes. Three ovens heating from warm together draw 168 kW, which is why their start times are staggered in SOP-01.

## Start-up sequence

### Timing

Each oven is switched on 35-60 minutes before its SMT line starts, so that the 45-minute heat-up is finished when the first board arrives. Ovens are never all switched on in the same minute.

### Sequence

1. Confirm the oven is not holding boards from a previous shift.
2. Check that the conveyor area is clear and the exhaust is running.
3. Switch the oven on and confirm the meter shows the heat-up level (80%, or 95% from cold).
4. After 45 minutes confirm the power has fallen to the 44% running level before releasing the line.

### Cold starts

After a long stop, such as a weekend, the oven heats at 95% instead of 80%. Stagger the three ovens by 15 minutes following SOP-01.

## Shutdown

At the end of production the oven stays on for 30 minutes after its line stops, to clear boards that are still inside. Boards must be cleared before any reduction. At the end of the working week the ovens are switched fully OFF, not left in standby. A standby oven holds 36% of rating all weekend. In incident S5 (2025-10-17 to 2025-10-20) RF-02 was left in standby and used about 1,556 kWh over the weekend against about 346 kWh normal. A correctly shut-down oven uses about 340-350 kWh per oven-weekend. See SOP-02.

## Power factor behaviour

The base power factor is 0.98 because the load is mostly resistive heating. It is not sensitive to load, so the reflow ovens do not usually cause a low-PF event on MDB-1. A low board PF on MDB-1 is more likely to come from the SMT line placement equipment (EQ-02) or from a tripped capacitor bank.

## Energy-saving notes

- Switch ovens off, not to standby, for the weekend and for holidays.
- Do not switch ovens on earlier than 60 minutes before the line starts; the lower bound of 35 minutes is enough when the oven is already warm.
- Stagger heat-up so that the three ovens do not add up on the 15-minute demand.
- Standby at 36% (25.2 kW per oven) is still a large load; avoid it unless boards are inside.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Check exhaust flow indicator and conveyor operation at start-up. |
| Weekly | Inspect zone heaters and thermocouple readings for drift. |
| Monthly | Clean flux residue from the exhaust and cooling zone. |
| Quarterly | Verify temperature profile with a profiling board and review the sub-meter reading against the running level. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. Cold starts of all three ovens raise demand quickly. |
| Simultaneous start rule | Fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes (reflow ovens, molders, wave solder, chillers, fixed compressors). It fires about 5-8 minutes after the start. The three ovens count toward the six-machine total. |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. A weekend oven left in standby is above 14.0 kW and triggers this rule. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-1 as a whole. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-02 Weekend Shutdown (per-area shutdown checklist)
- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
