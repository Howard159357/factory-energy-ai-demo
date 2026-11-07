# SOP-06 Heat Wave Pre-cooling

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-06 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | CH-01, CH-02, CT-01, AC-01, AC-02, AC-03, EV-01, BI-01, BI-02 |

## Purpose

This procedure describes how to prepare for a hot afternoon when the forecast shows a high probability that demand will exceed the 1,250 kW contract. It focuses on moving cooling energy earlier and avoiding new load in the peak window.

## Background

Summer normal peaks run at 1,100-1,180 kW, so the margin below the contract is small. In hot weather chiller efficiency drops 5% per degC above 32 degC outdoor, and compressors draw 1% more per degC above 30 degC at the intake. The cooling tower also follows chiller load and humid heat. Everything rises at the same time, in the afternoon.

### Reference case: incident S3

From 2025-07-22 to 2025-07-24 a heat wave of up to +5.5 degC (39.9 degC) produced 21 intervals just above the contract. The intervals were only just above it, so modest early action would have avoided most of them.

## Trigger

Start this procedure when any of the following holds on a hot summer weekday:

- The forecast gives P(exceed next hour) of 20% or more (WARNING) or 50% or more (ALARM) for the afternoon.
- The outdoor temperature forecast is well above the normal summer range, as in S3.
- The demand status is WARNING before 16:00.

## Timing against the tariff

The summer weekday peak is 16:00-22:00 at NT$9.39/kWh; 09:00-16:00 is half-peak at NT$5.85. Pre-cooling moves cooling energy into the half-peak window, before demand rises in the late afternoon. See EM-03.

## Procedure

### Step 1: before the afternoon

1. Check the outdoor temperature forecast with the energy coordinator.
2. Confirm that the condensers and the cooling tower are clean (EQ-07, EQ-08).
3. Confirm that both chillers are available and in lead/lag order, with CH-01 as lead.

### Step 2: pre-cool

1. Lower the chilled-water setpoint in the early afternoon, in steps agreed with the facilities engineer, so that the building and the process loops are cooler when the peak starts.
2. Keep CH-01 as the lead and stage CH-02 in early rather than during the peak.
3. Do not start a chiller manually inside the peak window: a manually started chiller is held at 30% for 150 minutes.

### Step 3: hold non-essential start-ups

1. Hold start-ups that are not required, including optional burn-in loading (BI-01, BI-02) and test runs.
2. Keep to the staggered order in SOP-01 for any start that must happen.
3. Delay the next burn-in loading if the status moves to WARNING.

### Step 4: EV pause readiness

1. Confirm that the EV-01 pause function works.
2. Warn staff at the EV bank that charging may be paused.
3. Pause charging as soon as WARNING is raised, since it removes up to 100% of the EV load (28 kW) without touching production.

### Step 5: compressed air

1. Check compressor intake temperature and filters.
2. Prepare to lower the compressed-air pressure by 0.5 bar if needed (3.5% of present compressor load).
3. Fix known leaks first (SOP-04).

### Step 6: during the peak

1. Monitor projected demand every interval.
2. If WARNING or ALARM is raised, follow SOP-03 and shed in playbook order.
3. Raise the chilled-water setpoint by +1 degC (4% of present chiller load) if the pre-cooling margin allows.

### Step 7: after the peak

1. Restore the setpoint and other changes gradually after 22:00.
2. Record the outcome in the shift log: peak 15-minute demand, actions taken and any intervals above contract.

## Never shed

Do not shed the server room, running molders mid-cycle or reflow ovens with boards inside.

## Roles

| Role | Duty |
|---|---|
| Energy coordinator | Reviews the forecast and decides to start |
| Facilities engineer | Adjusts chilled-water setpoint and checks plant |
| Shift supervisor | Holds start-ups and applies the playbook |

## Related documents

- EM-02 Demand Management
- EQ-07 Chiller Manual
- EQ-13 EV Charging Bank Manual
- SOP-03 Demand Exceedance Response
