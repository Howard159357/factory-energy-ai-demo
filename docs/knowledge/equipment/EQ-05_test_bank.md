# EQ-05 ICT/FCT Test Bank Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-05 |
| Revision | A |
| Owner role | Test engineer |
| Applies to | TEST-01 |

## Purpose and scope

This manual covers the in-circuit and functional test stations TEST-01 on board MDB-2. The test bank follows the SMT lines: its power rises when boards arrive from placement and falls when the SMT area slows down.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| TEST-01 | ICT/FCT Test Stations | MDB-2 | 25 | 0.93 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 25 kW unit |
|---|---|---|
| No SMT activity | 15% | 3.8 |
| Full SMT activity | 75% (15% + 60%) | 18.8 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 25 kW | 5.0 | 0.8 |

The model is 15% + 60% x SMT activity, where SMT activity is a share between none and full. At 15% the bank is IDLE; the RUNNING boundary of 5.0 kW is crossed when SMT activity is above about 8%.

## Start-up sequence

### Timing

The test bank is powered on at the start of the day shift, together with the first SMT line.

### Sequence

1. Power on the test stations and the fixtures.
2. Run the self-test.
3. Load the test programs and confirm the meter shows at least the base level of 15%.

## Shutdown

Close the test programs, remove fixtures and power the stations down at the end of the shift. They are off over the weekend unless the shift supervisor asks for a rework test. See SOP-02.

## Power factor behaviour

The base power factor is 0.93 and includes power supplies and instrument loads. It is lower at light load, and this can contribute to a short dip on MDB-2.

## Energy-saving notes

- Power stations down when no boards are expected.
- Concentrate test work so that stations do not idle at the base level.
- Avoid parking stations powered with no boards queued.

## Maintenance checklist

| Interval | Check |
|---|---|
| Daily | Run the self-test at power-on. |
| Weekly | Check fixture connectors. |
| Monthly | Clean ventilation and inspect cabling. |
| Quarterly | Calibrate instruments and review the relation between SMT activity and test bank power. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Off-schedule rule | Fires when a scheduled machine is above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more. Triggered if the stations stay above 5.0 kW outside normal hours. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-2 as a whole. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-02 Weekend Shutdown (per-area shutdown checklist)
- SOP-05 Power Factor Check (capacitor bank verification)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
