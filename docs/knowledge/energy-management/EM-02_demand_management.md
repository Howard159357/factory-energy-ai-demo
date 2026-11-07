# EM-02 Demand Management

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EM-02 |
| Revision | A |
| Owner role | Energy coordinator |
| Applies to | Plant main incomer, boards MDB-1 to MDB-6, all sub-metered equipment |

## Purpose

This document describes how the plant controls its 15-minute demand against the contract capacity, how warnings and alarms are raised, and which loads are shed, and in which order, when a limit is threatened.

## Key terms

The plant contract capacity is 1,250 kW, billed on 15-minute average demand. Demand is the average power over a fixed 15-minute interval, not an instantaneous reading. A short spike inside an interval matters only through its effect on the interval average.

## Demand status tiers

| Status | Condition |
|---|---|
| OK | Neither warning nor alarm condition holds |
| WARNING | P(exceed next hour) is 20% or more, or projected 15-minute demand is 1,125 kW (90% of contract) or more |
| ALARM | Projected 15-minute demand is above the 1,250 kW contract, or P(exceed next hour) is 50% or more |

The warning line of 1,125 kW is 90% of the contract. Summer normal peaks of 1,100-1,180 kW mean the plant often sits close to this line on hot afternoons.

## Projected demand

The projected demand for the current interval is calculated as:

Projected demand = (kWh so far in the interval + present kW x remaining minutes) / 15

Energy so far is converted to kW-minutes by multiplying kWh by 60 so that both terms use the same unit. The result is the average demand the interval will reach if the present load continues.

### Illustration

Suppose the first 9 minutes of an interval averaged 1,200 kW and the present load is 1,350 kW with 6 minutes remaining. The projected demand is (9 x 1,200 + 6 x 1,350) / 15 = 1,260 kW. This is above the contract, so the status is ALARM even though the interval has not finished.

### Behaviour early and late in the interval

Early in the interval the projection moves a lot with present load, because there is little accumulated energy. Late in the interval it is stable, because most of the energy has already been counted. A shed action taken late has less effect on the interval average than one taken early.

## Forecast-based warnings

In addition to the projection, a forecast gives the probability that demand will exceed the contract in the next hour, written P(exceed).

| P(exceed next hour) | Status raised |
|---|---|
| 20% or more | WARNING |
| 50% or more | ALARM |

Forecast-based warnings give time to act before the projection is affected. They are most useful on hot afternoons, when chillers and the cooling tower rise together (see SOP-06).

## Load-shed playbook

The playbook lists actions in order. The shares are engineering assumptions of the share of present load that can be shed within minutes.

| Order | Action | Equipment | Share of present load shed |
|---|---|---|---|
| 1 | Pause EV charging | EV-01 | 100% |
| 2 | Delay the next burn-in loading | BI-01, BI-02 | 35% |
| 3 | Raise chilled-water setpoint +1 degC | CH-01, CH-02 | 4% |
| 4 | Lower compressed-air pressure 0.5 bar | AC-01, AC-02, AC-03 | 3.5% |

The order puts the least disruptive actions first. EV charging is paused first because it has no effect on production.

### Never shed

The following are never shed:

- Server room (DC-01)
- Running molders mid-cycle (IM-01 to IM-04)
- Reflow ovens with boards inside (RF-01 to RF-03)

## Escalation

| Condition | Who acts | Action |
|---|---|---|
| WARNING | Shift supervisor | Read projected demand, prepare to apply playbook actions, hold non-essential start-ups |
| ALARM | Shift supervisor | Apply playbook actions in order until projected demand is under contract |
| ALARM repeats in one day | Energy coordinator | Review cause and notify plant manager |
| Cause traced to equipment fault | Facilities engineer | Inspect equipment |

Detailed steps are in SOP-03.

## Common causes of high demand

| Cause | Typical signature | Reference |
|---|---|---|
| Simultaneous start-up | Many machines rising together; the simultaneous start rule fires | SOP-01 |
| Heat wave | Chillers and cooling tower rise together | SOP-06 |
| Weekend standby left on | Reflow oven standby over the weekend | SOP-02 |

In incident S2 (2025-06-16 at 08:00), ten machines started at once: IM-01 to IM-04, RF-01 to RF-03, WS-01, CH-02 and AC-02. Demand reached 1,324 kW against the 1,250 kW contract. Staggering the same starts by 15 minutes gives 1,142 kW.

In incident S3 (2025-07-22 to 2025-07-24) a heat wave of up to +5.5 degC (39.9 degC) caused 21 intervals just above the contract.

## Cost of exceeding

Excess demand is billed at the contract price for the period multiplied by 2, or by 3 beyond 10% over the contract. See EM-03 for the worked examples.

## Related procedures

- SOP-01 Monday Start-up
- SOP-03 Demand Exceedance Response
- SOP-06 Heat Wave Pre-cooling
