# SOP-01 Monday Start-up

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-01 |
| Revision | A |
| Owner role | Shift supervisor |
| Applies to | RF-01, RF-02, RF-03, IM-01, IM-02, IM-03, IM-04, WS-01, CH-02, AC-02 |

## Purpose

This procedure sets the order in which equipment is started after a weekend or holiday, so that the plant does not start many machines together. It applies on the first workday after a Sunday or holiday, when the plant is largely cold.

## Why start-up is staggered

Incident S2 (2025-06-16 at 08:00) occurred when ten machines started at once: IM-01 to IM-04, RF-01 to RF-03, WS-01, CH-02 and AC-02. Demand reached 1,324 kW against a contract of 1,250 kW. Staggering the same starts by 15 minutes gives 1,142 kW, which is under the contract.

Cold machines draw more than warm ones during heat-up. Reflow ovens and molders heat at 95% of rating from cold, instead of 80% and 78%. The demand charge is applied to the 15-minute average, so spreading starts across separate intervals prevents the heat-up peaks from adding together.

## Start groups

Groups are started 15 minutes apart. Choose time T so that the last group has finished heat-up before it is needed for production.

| Group | Start time | Machines | Reason |
|---|---|---|---|
| 1 | T | CH-02, AC-02 | Chilled water and compressed air must be available before production equipment |
| 2 | T + 15 min | RF-01, RF-02, RF-03 | Ovens need 45 minutes of heat-up and must be hot 35-60 minutes before the SMT line starts |
| 3 | T + 30 min | IM-01, IM-02, IM-03, IM-04 | Barrel heat-up takes 40 minutes; molders start 0-75 minutes before the shift |
| 4 | T + 45 min | WS-01 | Preheat is 30 minutes, the shortest |

No group contains six or more machines, so the simultaneous start rule is not triggered.

## Preconditions

1. Confirm the projected demand status is OK (EM-02).
2. Confirm all meters involved are reporting; a stale meter is one with no reading for more than 180 seconds (SOP-07).
3. Confirm that the cooling tower and pumps (CT-01) are running before CH-02.
4. Confirm that no boards are inside the reflow ovens.

## Procedure

### Group 1: utilities

1. Start CH-02 and AC-02.
2. Confirm that chilled water and compressed air are within their normal range.
3. Check the demand status. If WARNING is raised, hold the next group until it clears.

### Group 2: reflow ovens

1. At T + 15 min start RF-01, RF-02 and RF-03.
2. Confirm that each oven shows the cold heat-up level (95% of rating).
3. Check that the other groups are not started early.

### Group 3: molders

1. At T + 30 min start IM-01, IM-02, IM-03 and IM-04.
2. Confirm barrel heat-up on each meter.
3. Verify that the hopper dryers and mold cooling are running.

### Group 4: wave solder

1. At T + 45 min start WS-01.
2. Confirm that it shows the preheat level (90% of rating).

## Checks after start-up

| Check | Expected |
|---|---|
| Demand status | OK, or WARNING without ALARM |
| Reflow ovens | Fall to 44% after heat-up when the line runs |
| Molders | Steady at 53% after heat-up |
| WS-01 | 55% after preheat |
| Simultaneous start alert | Not raised |

## If a limit is threatened

If WARNING or ALARM is raised during start-up, delay the next group and follow SOP-03. Never shed a reflow oven with boards inside or a running molder mid-cycle.

## Records

The shift supervisor records the start times of each group, the peak 15-minute demand during start-up and any alert raised.

## Related documents

- EQ-01 Reflow Oven Manual
- EQ-06 Injection Molder Manual
- EQ-04 Wave Solder Machine Manual
- EM-02 Demand Management
