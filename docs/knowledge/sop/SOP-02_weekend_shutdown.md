# SOP-02 Weekend Shutdown

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-02 |
| Revision | A |
| Owner role | Shift supervisor |
| Applies to | RF-01, RF-02, RF-03, SMT-L1, SMT-L2, SMT-L3, WS-01, TEST-01, IM-01, IM-02, IM-03, IM-04, and areas MDB-1 to MDB-6 |

## Purpose

This procedure lists what is switched off at the end of the working week, area by area, and what stays on. It prevents idle energy over the weekend, the largest single source of which is a reflow oven left in standby.

## Timing

The plant runs a half plant on Saturday: SMT-L1, SMT-L2, IM-01 and IM-02 on the day shift. Sunday and holidays are maintenance only. The shutdown checklist is therefore done in two steps: a Friday step for equipment not needed on Saturday, and a Saturday step at the end of the Saturday day shift for the rest. For a holiday, treat the last working day as Friday.

## Why reflow ovens must be OFF, not standby

A reflow oven in standby draws 36% of its 70 kW rating, which is 25.2 kW, for as long as it is left. A properly switched-off oven uses about 340-350 kWh per oven-weekend. In incident S5 (2025-10-17 to 2025-10-20) RF-02 was left in standby all weekend and the weekend energy was about 1,556 kWh against about 346 kWh normal. The excess is about 1,210 kWh from a single oven. The off-schedule rule would flag this, but only after 120 minutes at above 20% of rating; the saving comes from preventing it.

The reflow ovens stay on for 30 minutes after the line stops. Switch them off after that time, and only when no boards are inside.

## Checklist by area

### SMT Area (MDB-1)

| Item | Action |
|---|---|
| RF-01, RF-02, RF-03 | Confirm no boards inside, then switch fully OFF after the 30-minute tail. Not standby. |
| SMT-L1, SMT-L2 | Clear line, power down at the end of the Saturday day shift |
| SMT-L3 | Power down at the end of the Friday day shift |

### Assembly and Test (MDB-2)

| Item | Action |
|---|---|
| WS-01 | Drain flux, switch OFF |
| TEST-01 | Close programs, power down stations |
| BI-01, BI-02 | Stay on. Batches run independently of the production schedule |

### Injection Molding (MDB-3)

| Item | Action |
|---|---|
| IM-03, IM-04 | Complete the cycle, purge the barrel, heaters OFF on Friday night shift end (these run around the clock on workdays) |
| IM-01, IM-02 | Complete the cycle, purge, heaters OFF at the end of the Saturday day shift |

Never stop a molder mid-cycle.

### HVAC and Chilled Water (MDB-4)

Chillers and the cooling tower stay on for burn-in and the server room. Confirm lead/lag staging is normal.

### Compressed Air (MDB-5)

Compressors stay on for maintenance and the continuous loads. Close the air to the shut-down areas so that leaks are not fed, and confirm the trim machine settles at its low load.

### Facilities and Office (MDB-6)

| Item | Action |
|---|---|
| DC-01 | Stays on |
| EV-01 | Disconnect idle sessions; the bank stays powered |
| Office lighting and air conditioning | Off at the end of the day |

## What stays on over the weekend

Burn-in rooms, chillers and cooling tower, compressors, and the server room. These are the Sunday and holiday maintenance loads.

## Verification

1. After the shutdown, check the sub-meter status of each shut-down machine: it should be OFF (at or below 3% of rating).
2. Check that no reflow oven is IDLE or RUNNING.
3. Record the plant base load. The night base load is about 500 kW; a figure well above this suggests something has been left on.

## Records

The shift supervisor records the time of each shutdown and any exception. The energy coordinator reviews weekend energy each Monday.

## Related documents

- EQ-01 Reflow Oven Manual
- EQ-06 Injection Molder Manual
- EQ-04 Wave Solder Machine Manual
- SOP-01 Monday Start-up
