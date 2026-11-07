# EQ-08 Cooling Tower and Pumps Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-08 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | CT-01 |

## Purpose and scope

This manual covers the cooling tower and condenser pumps CT-01 on board MDB-4. The tower load follows the chillers, with an added term for humid heat, so it rises on hot humid afternoons when chillers are also at their highest.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| CT-01 | Cooling Tower & Pumps | MDB-4 | 45 | 0.84 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 45 kW unit |
|---|---|---|
| Baseline term | 10% | 4.5 |
| Chiller term at 400 kW of chiller load | 40% | 18.0 |
| Humid-heat term per unit of factor | 15% x humid-heat factor | 6.8 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 45 kW | 9.0 | 1.3 |

The model is 10% + 40% x chiller load/400 kW + 15% x humid-heat factor. The three terms add together. Power therefore never falls below the 10% baseline while the tower is on.

## Start-up sequence

### Sequence

1. Check basin level and water treatment.
2. Start the condenser pumps and confirm flow.
3. Start the tower fan and confirm the meter shows at least the baseline term.
4. Release the chillers (EQ-07).

### Order

The tower and pumps start before the chillers. The tower is not staged with the chiller start group.

## Shutdown

Stop the chillers first, then the pumps and fan after a short run-on. The tower runs while any chiller is running.

## Power factor behaviour

The base power factor is 0.84, the lowest of the large loads. At no load it falls by about 0.12. The tower makes a visible contribution to the MDB-4 board PF.

## Energy-saving notes

- Keep the fill clean to reduce fan time.
- Do not run the tower with the chillers off.
- Reducing chiller load also reduces the tower term.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check basin level and make-up water. |
| Monthly | Inspect fan and drive, clean strainers. |
| Quarterly | Descale fill and check pump seals. |
| Quarterly | Compare tower power with the model. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02.  |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-4. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-06 Heat Wave Pre-cooling (high exceedance probability on hot afternoons)
- SOP-07 Meter Data Quality (stale, reset and gap checks)
