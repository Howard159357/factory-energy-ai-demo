# EM-03 Tariff Guide

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EM-03 |
| Revision | A |
| Owner role | Finance analyst |
| Applies to | Plant electricity bill, regular contract of 1,250 kW |

## Basis of the tariff

The demo plant tariff follows Taipower's published high-voltage three-segment time-of-use structure, with a fixed peak. The table was approved on 2025-11-17. Amounts are in NT$ including 5% tax. The illustrative exchange rate is NT$32 = US$1. The summer season runs from 16 May to 15 October.

## Time-of-use periods and energy prices

### Summer (16 May - 15 October)

| Day type | Period | Hours | Price (NT$/kWh) |
|---|---|---|---|
| Weekday | Peak | 16:00-22:00 | NT$9.39 |
| Weekday | Half-peak | 09:00-16:00 and 22:00-24:00 | NT$5.85 |
| Weekday | Off-peak | Otherwise | NT$2.53 |
| Saturday | Saturday rate | 09:00-24:00 | NT$2.60 |

### Other months

| Day type | Period | Hours | Price (NT$/kWh) |
|---|---|---|---|
| Weekday | Half-peak | 06:00-11:00 and 14:00-24:00 | NT$5.47 |
| Weekday | Off-peak | Otherwise | NT$2.32 |
| Saturday | Saturday rate | 06:00-11:00 and 14:00-24:00 | NT$2.41 |
| Sunday | Off-peak | All day | Off-peak price of the season (NT$2.32 in other months) |

Sundays are off-peak all day. In summer, the 16:00-22:00 weekday peak overlaps the overtime shift (17:00-20:00) and the hottest hours, so starts and optional load are best avoided there.

## Demand charges

The demand charge is billed per kW of contract capacity per month.

| Contract type | Summer | Other months |
|---|---|---|
| Regular | NT$223.60 | NT$166.90 |
| Off-peak and Saturday | NT$44.70 | NT$33.30 |

The demo plant holds only a regular contract, with a capacity of 1,250 kW.

## Exceedance charges

When demand in a 15-minute interval exceeds the contract capacity, the excess is billed at that period's contract price multiplied by 2 up to 10% over the contract, and multiplied by 3 beyond that. Ten percent over the contract is 125 kW (1,375 kW total).

### Worked example 1: off-peak (summer Monday, 08:15)

An excess of 74.4 kW at 08:15 on a summer Monday, an off-peak period, is billed at the off-peak contract price of NT$44.70:

74.4 x 44.70 x 2 = NT$6,652 (US$208)

### Worked example 2: peak (summer Monday, 16:00)

The same 74.4 kW excess at 16:00, a peak period, is billed at the regular contract price of NT$223.60:

74.4 x 223.60 x 2 = NT$33,277 (US$1,040)

The same excess therefore costs about five times more at the peak than at off-peak, which is why avoiding exceedance is more important in the afternoon. Both examples are below the 10% line, so the multiplier is 2.

## Power factor adjustment

The monthly average power factor adjusts the whole bill by 0.1% for each percentage point from 80%. Below 0.80 the adjustment is a surcharge; above 0.80 it is a credit. The credit is capped at a power factor of 0.95, which gives a maximum credit of 1.5%.

| Monthly average PF | Effect on the bill |
|---|---|
| Below 0.80 | Surcharge of 0.1% per percentage point below 80% |
| 0.84 | Credit of 0.4% (4 points above 80%) |
| 0.95 or above | Maximum credit of 1.5% |

### Example: 0.84

At a monthly average of 0.84, the credit is 0.4% of the bill.

### Example: 0.95

At a monthly average of 0.95, the credit is 1.5%, the maximum. Improving beyond 0.95 gives no further credit.

The difference between 0.95 and 0.84 is therefore 1.1% of the bill. Incident S8 (2025-11-03 to 2025-11-12), in which the MDB-3 capacitor bank tripped and the board PF fell from 0.96 to 0.84, is an example of what loses the credit. See SOP-05.

## Cost of a leak

Wasted continuous power is valued at the year-average energy rate of about NT$4.12/kWh:

Annual cost = kW x 8,760 h x 4.12

### Example: an 18 kW compressed-air leak

18 x 8,760 x 4.12 = about NT$650,000 per year, or about US$20,000 per year. This is the size of the leak reached in incident S4. See SOP-04.

## Practical rules from the tariff

1. Exceedance penalties are higher at peak than off-peak, so protect the summer weekday 16:00-22:00 window first.
2. The demand charge is paid on the contract whether or not it is used, so the contract is not exceeded for convenience.
3. Idle energy is most expensive at peak.
4. Power factor credit is small but needs no capital cost beyond keeping capacitor banks working.

## Related documents

- EM-02 Demand Management
- SOP-03 Demand Exceedance Response
- SOP-04 Compressed Air Leak
- SOP-05 Power Factor Check
