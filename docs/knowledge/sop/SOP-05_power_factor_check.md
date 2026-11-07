# SOP-05 Power Factor Check

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-05 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | Capacitor banks on boards MDB-1 to MDB-6 |

## Purpose

This procedure describes the check made when the low power factor rule fires on a board. The usual cause is a capacitor bank that is out of service, such as a tripped breaker or a blown fuse.

## Background

The capacitor banks cancel 55% of each feeder's reactive power. If a bank drops out, the board's reactive power rises and its power factor falls, while the active power stays the same. The monthly average PF adjusts the bill by 0.1% per percentage point from 80%, with a credit capped at 0.95 (1.5% credit). See EM-03.

## Trigger

The low power factor rule fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. It is an early warning, well above the 0.80 line at which a surcharge begins.

## Reference case: incident S8

From 2025-11-03 to 2025-11-12 the MDB-3 capacitor bank tripped. The PF of MDB-3 fell from 0.96 to 0.84.

### Bill impact

A monthly average of 0.96 is above the cap, so it earns the maximum credit of 1.5%. A monthly average of 0.84 earns a credit of 0.4%. The difference is 1.1% of the bill for as long as the average stays low. If the average fell below 0.80, a surcharge would apply instead of a credit.

## Expected PF values

| Condition | Typical PF |
|---|---|
| Healthy board with capacitor bank in service | Close to or above 0.95 (MDB-3 was 0.96 before S8) |
| Rule threshold | Below 0.90 |
| Capacitor bank out of service (S8) | 0.84 |
| Surcharge line | Below 0.80 |

The equipment base power factors are in the equipment manuals. Motors and drives fall about 0.12 at no load compared with full load, so a board at light load will show a lower PF than at full load. The rule requires load above 10% of rating to avoid this.

## Procedure

### Step 1: confirm the signal

1. Confirm the board's meters are reporting (SOP-07).
2. Check the board load: is it above 10% of rating?
3. Check for equipment that has been running unloaded for a long time, such as a compressor in unload mode, which lowers PF.

### Step 2: inspect the capacitor bank

Work is done by the facilities engineer under the plant electrical safety rules.

1. Check the bank's controller display for fault or step status.
2. Check the bank's breaker or fuses and the contactors for each step.
3. Look for signs of overheating, a swollen capacitor, or a tripped protection relay.
4. Do not enter the enclosure while the bank is energized unless the rules for live work are met.

### Step 3: restore

1. Isolate the bank, replace the failed fuse, contactor or capacitor, and re-energize.
2. If the failure repeats, keep the bank out of service and call the electrical contractor role for a full inspection.

### Step 4: verify

1. Watch the board 15-minute PF over the next hours. It should return towards its normal value (MDB-3 returned from 0.84 to about 0.96).
2. Confirm the low power factor rule clears.
3. Record the days the bank was out.

## Prevention

- Check the capacitor banks quarterly and record controller status.
- Review the monthly average PF on each board in the monthly energy review (EM-01).
- Keep spare fuses on site.

## Records

| Field | Content |
|---|---|
| Board | |
| Date and time rule fired | |
| PF before and after | |
| Fault found | |
| Days out of service | |

## Related documents

- EM-03 Tariff Guide
- EQ-06 Injection Molder Manual
- EQ-07 Chiller Manual
- EM-01 Energy Policy
