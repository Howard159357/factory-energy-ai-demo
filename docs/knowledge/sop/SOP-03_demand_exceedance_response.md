# SOP-03 Demand Exceedance Response

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | SOP-03 |
| Revision | A |
| Owner role | Energy coordinator |
| Applies to | Plant main incomer; EV-01, BI-01, BI-02, CH-01, CH-02, AC-01, AC-02, AC-03 |

## Purpose

This procedure sets out what the shift supervisor does when the demand status moves to WARNING or ALARM. The aim is to bring projected 15-minute demand back under the 1,250 kW contract before the interval ends.

## Trigger conditions

| Status | Condition |
|---|---|
| WARNING | P(exceed next hour) of 20% or more, or projected demand of 1,125 kW or more |
| ALARM | Projected demand above 1,250 kW, or P(exceed next hour) of 50% or more |

## Step 1: read the situation

1. Read the projected demand: (kWh so far in the interval + present kW x remaining minutes) / 15, with kWh converted to kW-minutes.
2. Compute the required reduction: projected demand minus 1,250 kW. For a WARNING based on probability, aim to reduce the present load enough to remove the risk.
3. Check the time left in the interval. A shed late in the interval has less effect on the average.
4. Check whether a start-up is in progress. If so, hold the next start group (SOP-01).

## Step 2: shed in playbook order

Apply the actions in this order and stop when projected demand is back under contract.

| Order | Action | Equipment | Share of present load |
|---|---|---|---|
| 1 | Pause EV charging | EV-01 | 100% |
| 2 | Delay the next burn-in loading | BI-01, BI-02 | 35% |
| 3 | Raise chilled-water setpoint +1 degC | CH-01, CH-02 | 4% |
| 4 | Lower compressed-air pressure 0.5 bar | AC-01, AC-02, AC-03 | 3.5% |

Never shed the server room, running molders mid-cycle, or reflow ovens with boards inside.

## Worked example: 74.4 kW to shed

At 16:00 on a summer weekday, projected demand is 1,324.4 kW, so 74.4 kW above contract is to be removed. This is the size of excess in the tariff examples (EM-03). The illustrative present loads are as follows.

| Action | Present load assumed | Share | Shed |
|---|---|---|---|
| Pause EV charging (EV-01) | 28 kW (all four chargers active) | 100% | 28.0 kW |
| Delay burn-in loading (BI-01, BI-02) | 102 kW (both rooms at 51 kW) | 35% | 35.7 kW |
| Chilled-water setpoint +1 degC | 300 kW of chiller load | 4% | 12.0 kW |
| Running total | | | 75.7 kW |

The first three actions together shed 75.7 kW, which is above the 74.4 kW required. The compressed-air pressure reduction is not needed. If chiller load were lower than assumed, the fourth action would be applied next.

The cost at stake: the same 74.4 kW excess costs NT$6,652 at off-peak and NT$33,277 at peak (EM-03).

## Step 3: confirm

1. Watch the projected demand over the next few minutes. It should fall below 1,250 kW.
2. If it does not, apply the next action and inform the energy coordinator.
3. If the WARNING was raised by a probability and not by projection, maintain the shed actions until P(exceed) falls below 20%.

## Step 4: record

Record in the shift log:

- Time and status (WARNING or ALARM)
- Projected demand at trigger
- Actions taken and their time
- Peak demand reached in the interval
- Probable cause (start-up, heat, equipment fault)

## Step 5: restore

Restore shed actions in reverse order once demand is stable and below the warning line of 1,125 kW: pressure, setpoint, burn-in loading, then EV charging. Do not restore all at once.

## Step 6: review

The energy coordinator reviews every ALARM the next working day. A repeated ALARM in one day is escalated to the plant manager. Causes are classified as start-up (SOP-01), heat wave (SOP-06), standby (SOP-02) or equipment fault.

## Roles

| Role | Duty |
|---|---|
| Shift supervisor | Applies the playbook and records |
| Facilities engineer | Applies setpoint and pressure changes |
| Energy coordinator | Reviews and reports |

## Related documents

- EM-02 Demand Management
- EM-03 Tariff Guide
- EQ-03 Burn-in Room Manual
- EQ-13 EV Charging Bank Manual
