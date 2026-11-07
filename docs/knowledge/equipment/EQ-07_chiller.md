# EQ-07 Chiller Manual

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EQ-07 |
| Revision | A |
| Owner role | Facilities engineer |
| Applies to | CH-01, CH-02 |

## Purpose and scope

This manual covers the two chillers on board MDB-4 (HVAC and Chilled Water). Chillers are the largest electrical loads in the plant and respond to outdoor temperature. They are the main reason summer afternoons approach the contract capacity.

## Units covered

| Meter ID | Name | Board | Rated kW | Base PF |
|---|---|---|---|---|
| CH-01 | Chiller 1 | MDB-4 | 200 | 0.88 |
| CH-02 | Chiller 2 (Large) | MDB-4 | 250 | 0.88 |



## Operating states and power

Power is stated as a share of rated kW and as kW for each unit size.

| State | Share of rated | 200 kW unit | 250 kW unit |
|---|---|---|---|
| Manual start hold (150 min) | 30% | 60.0 | 75.0 |
| RUNNING boundary (above) | 20% | 40.0 | 50.0 |
| Full rating | 100% | 200.0 | 250.0 |

### Status classification

The command center classifies equipment as RUNNING above 20% of rating, IDLE above 3%, and OFF otherwise.

| Unit size | RUNNING above (kW) | IDLE above (kW) |
|---|---|---|
| 200 kW | 40.0 | 6.0 |
| 250 kW | 50.0 | 7.5 |

CH-01 is the lead chiller and takes cooling demand up to 180 kW. CH-02 stages in on the remainder, across a range of 60-240 kW. Chiller efficiency drops 5% per degC above 32 degC outdoor. A manually started chiller is held at 30% for 150 minutes.

## Start-up sequence

### Sequence

1. Confirm cooling tower pumps are running (see EQ-08).
2. Start CH-01 as the lead chiller.
3. Stage CH-02 in only when cooling demand exceeds what CH-01 can take.
4. Confirm chilled-water flow and supply temperature.

### Manual start

A chiller started manually is held at 30% for 150 minutes: 60.0 kW for CH-01 and 75.0 kW for CH-02. Do not start a chiller manually inside a peak window unless required.

### Start-up after a weekend

Chillers run through maintenance days. When a stop has occurred, stagger CH-02 as part of the first group in SOP-01.

## Shutdown

Reduce load, allow the chilled-water loop to equalize, and stop CH-02 first, then CH-01. Chillers are not routinely shut down for the weekend because burn-in and the server room still need cooling.

## Power factor behaviour

The base power factor is 0.88 at full load. At no load it falls by about 0.12. Chillers are the largest motor load on MDB-4, so a fault in the MDB-4 capacitor bank would be seen quickly.

## Energy-saving notes

- Raise the chilled-water setpoint by 1 degC to shed about 4% of present chiller load.
- Pre-cool on hot afternoons (SOP-06) rather than ramping both machines inside the peak.
- Keep condensers clean; efficiency already falls 5% per degC above 32 degC.
- Avoid manual starts that hold 30% for 150 minutes.

## Maintenance checklist

| Interval | Check |
|---|---|
| Weekly | Check supply and return temperatures. |
| Monthly | Inspect condenser and evaporator approach temperatures. |
| Quarterly | Clean condenser tubes and verify lead/lag staging. |
| Quarterly | Review the relation between outdoor temperature and chiller kW. |

## Monitoring alarms that apply

| Alarm or rule | Definition and relevance |
|---|---|
| Demand status (plant level) | ALARM if projected 15-minute demand exceeds the 1,250 kW contract or P(exceed next hour) is 50% or more; WARNING if P(exceed) is 20% or more or projected demand is 1,125 kW or more. See EM-02. A setpoint raise of 1 degC is a standard shed action. |
| Simultaneous start rule | Fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes (reflow ovens, molders, wave solder, chillers, fixed compressors). It fires about 5-8 minutes after the start. Chillers count toward the six-machine total. |
| Low power factor rule | Fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more. This is an early warning, well above the 0.80 surcharge line. Applies to MDB-4. |
| Data quality | Readings arrive every 60 s; a meter is stale after 180 s. See SOP-07.  |

## Related procedures

- SOP-01 Monday Start-up (staggered start-up after a weekend or holiday)
- SOP-03 Demand Exceedance Response (WARNING and ALARM handling)
- SOP-06 Heat Wave Pre-cooling (high exceedance probability on hot afternoons)
