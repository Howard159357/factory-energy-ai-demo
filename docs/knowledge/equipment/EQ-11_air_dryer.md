# EQ-11 Refrigerated Air Dryer Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-11 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | DR-01 |

## Purpose and scope

This manual covers the refrigerated air dryer DR-01 on board MDB-5. The dryer follows the airflow of the compressors and the ambient temperature. It is a small load but runs continuously.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| DR-01 | Refrigerated Air Dryer | MDB-5 | 7.5 | 0.82 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 7.5 kW unit |
|---|---|---|
| Baseline term | 30% | 2.2 |
| Airflow term at full airflow | 45% x airflow | 3.4 |
| Ambient term at full factor | 15% x ambient factor | 1.1 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 7.5 kW | 1.5 | 0.2 |

The model is 30% + 45% x airflow + 15% x ambient factor. The terms add together.

## Start-up sequence

### Sequence

1. Start the dryer before the compressors.
2. Confirm dew point indication.
3. Open the airflow after dew point is reached.

## Shutdown

The dryer stops after the compressors. It stays on while the air network is in use.

## Power factor behaviour

The base power factor is 0.82, the lowest of any equipment unit, and falls by about 0.12 at no load. The dryer is small, so its effect on the MDB-5 PF is modest.

## Energy-saving notes

- Match dryer operation to compressor operation.
- Keep the condenser clean.
- Avoid over-sizing the airflow.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check drain and dew point. |
| Monthly | Clean the condenser. |
| Quarterly | Check refrigerant circuit and control set points. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-5. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-04 Compressed Air Leak (night-load triggered inspection)
- SOP-05 Power Factor Check (capacitor bank verification)
