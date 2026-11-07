# EM-01 Energy Policy

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EM-01 |
| Revision | A |
| Owner role | Plant manager |
| Applies to | All DemoTronics Electronics Plant boards MDB-1 to MDB-6 and all sub-metered equipment |

## Policy statement

DemoTronics Electronics Plant makes printed circuit board assemblies (SMT), performs final assembly and test, and molds plastic housings. The plant commits to using energy deliberately: to keep its electrical demand inside the contract it holds, to avoid paying penalties that are preventable by procedure, and to remove waste that does not support production.

The plant is supplied at 380 V three-phase. It holds a regular contract capacity of 1,250 kW, billed on 15-minute average demand. The sum of equipment ratings is about 1,480 kW, so the plant relies on diversity (about 0.75): not all equipment runs at full load at once. Summer normal peaks run at 1,100-1,180 kW, and the night base load is about 500 kW. The margin between normal peaks and the contract is therefore small in summer, and discipline in how equipment is started and shed is the main protection.

## Objectives

| # | Objective | Measure |
|---|---|---|
| 1 | Stay under the contract capacity | 15-minute demand at or below 1,250 kW |
| 2 | Keep a healthy power factor | Monthly average PF at or above 0.95 |
| 3 | Cut idle energy | Reduce standby and idle consumption of reflow ovens, molders and compressors |
| 4 | Detect waste early | Compressed-air leaks and capacitor bank faults found by monitoring before they appear on the bill |

### Objective 1: stay under 1,250 kW

Demand above the contract is billed at a multiple of the contract price (see EM-03). The warning line is 90% of contract, which is 1,125 kW. The detail of how demand is monitored and how loads are shed is in EM-02 and SOP-03.

### Objective 2: monthly PF at or above 0.95

Power factor is averaged across the month. The tariff gives a credit for a monthly average above 0.80, capped at 0.95. Capacitor banks cancel 55% of each feeder's reactive power, so the capacitor banks must be kept in service. See EM-03 and SOP-05.

### Objective 3: cut idle energy

Idle energy is energy used while equipment produces nothing. The largest known examples are reflow ovens left in standby over a weekend (incident S5), fixed-speed compressors running unloaded, and molders held hot between jobs. See SOP-02.

## Roles and responsibilities

| Role | Responsibility |
|---|---|
| Plant manager | Owns this policy, approves objectives and receives the monthly review |
| Energy coordinator | Maintains the monitoring thresholds, reviews alerts, prepares the monthly energy review, and keeps the knowledge documents current |
| Facilities engineer | Owns chillers, cooling tower, compressors, air dryer, capacitor banks and EV charging; carries out leak surveys and power factor checks |
| Shift supervisor | Responds to demand WARNING and ALARM messages on shift, applies the load-shed playbook and records the outcome |
| Production engineers | Own start-up and shutdown order for SMT, molding and assembly equipment |
| IT infrastructure lead | Owns the server room, which is on the never-shed list |
| Finance analyst | Reconciles the bill against metered energy and reports exceedance and power factor adjustments |

### Escalation by role

The shift supervisor escalates to the energy coordinator when a demand ALARM is raised, and to the plant manager when an ALARM repeats within the same day. The facilities engineer is called whenever a low power factor rule or an air-leak baseline rule fires.

## Operating principles

1. Equipment is started in a staggered order and not all at once (SOP-01).
2. Reflow ovens are switched off at the weekend, not left in standby (SOP-02).
3. When a WARNING or ALARM is raised, loads are shed in the playbook order (EM-02, SOP-03).
4. The server room, running molders mid-cycle and reflow ovens with boards inside are never shed.
5. Meter data must be trustworthy before it is used for decisions (SOP-07).

## Review cadence

| Frequency | Review | Led by |
|---|---|---|
| Daily | Review of demand status, alerts and shed actions from the previous day | Energy coordinator |
| Weekly | Review of exceedance risks, idle energy and open actions | Energy coordinator with production engineers |
| Monthly | Review of peak demand, monthly power factor, bill reconciliation and incident log | Plant manager |
| Quarterly | Review of this policy, the playbook shares and the monitoring thresholds | Plant manager |

## Records

Records kept by the energy coordinator include the incident log (for example S2, S3, S4, S5 and S8), shed actions taken during WARNING and ALARM, power factor checks and meter data quality findings. Records are kept in line with the plant document retention schedule.

## Related documents

- EM-02 Demand Management
- EM-03 Tariff Guide
- EM-04 Glossary
- SOP-01 to SOP-07
