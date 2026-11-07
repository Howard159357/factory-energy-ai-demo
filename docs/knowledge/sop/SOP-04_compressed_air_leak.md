# SOP-04 Compressed Air Leak

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-04 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | AC-01, AC-02, AC-03, DR-01 and the compressed air network on MDB-5 |

## Purpose

This procedure describes the inspection that follows when the night-load baseline detects a rising compressor load, and how the repair is verified. Compressed air leaks waste energy all hours, and the loss appears most clearly at night, when production demand is low.

## Trigger

The air-leak baseline compares compressor night load (02:00-05:00) with the median of the last 6 similar nights. The rule fires when the CUSUM (k = 0.5, h = 8 robust sigmas) crosses its limit and the night load is more than 3 kW above expectation.

## Reference case: incident S4

From 2025-09-01 to 2025-09-29 a leak grew to 18 kW. It was caught on 9 September. The weekday night load had risen from 96 kW to 114 kW, which is the 18 kW of the leak. After repair, the night load returned to 96 kW.

## Cost of a leak

At the year-average energy rate of about NT$4.12/kWh an 18 kW leak costs 18 x 8,760 x 4.12 = about NT$650,000 per year (about US$20,000). Smaller leaks cost in proportion. See EM-03.

## Procedure

### Step 1: confirm the signal

1. Check the night load of AC-01, AC-02 and AC-03 over the last nights.
2. Confirm the meters are reporting (SOP-07). A stale meter or a kWh register reset can imitate a change.
3. Check that no production activity at night explains the increase, for example a molder running (IM-03 and IM-04 run around the clock on workdays).

### Step 2: choose the time for the walk-down

Do the ultrasonic walk-down in a quiet period, ideally at night or on a Sunday, when machine noise is low and the leak is the largest part of the flow.

### Step 3: ultrasonic walk-down

1. Use an ultrasonic leak detector along the main headers and branches.
2. Start with the areas with the most pneumatic use, in particular injection molding.
3. Check fittings, quick couplers, hoses, filter and regulator units, drain valves and blow-off nozzles.
4. Check the air dryer area and the compressor room.

### Step 4: tag

1. Tag each leak with a numbered tag at the location.
2. Record location, type, and estimated size (small, medium, large).
3. Photograph the tag where practical.

### Step 5: repair

1. Isolate the section where possible and depressurize it.
2. Replace the faulty fitting, hose or valve.
3. Re-pressurize and recheck with the detector.
4. Remove the tag and record the closure.

### Step 6: verify

1. Watch the compressor night load for the next several nights.
2. The target is the return to the earlier baseline. In S4 the weekday night load returned to 96 kW.
3. If the night load does not return, repeat the walk-down; leaks may exist in more than one place.

## Record

| Field | Content |
|---|---|
| Date detected | |
| Night load before | |
| Leaks tagged and repaired | |
| Night load after | |
| Estimated yearly saving | Use the leak formula (kW x 8,760 h x 4.12) |

## Prevention

- Schedule a monthly walk-down of the air network.
- Lowering the compressed-air pressure by 0.5 bar also reduces leak flow and sheds about 3.5% of present compressor load.
- Do not hide a leak by starting AC-02; fix it.

## Roles

| Role | Duty |
|---|---|
| Energy coordinator | Reviews the alert |
| Facilities engineer | Leads the walk-down and repair |
| Shift supervisor | Releases the area for work |

## Related documents

- EQ-09 Fixed-Speed Air Compressor Manual
- EQ-10 VSD Air Compressor Manual
- EQ-11 Refrigerated Air Dryer Manual
- EM-03 Tariff Guide
