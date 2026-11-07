# EM-04 Glossary

*Fictional document for the DemoTronics demo plant. All content is synthetic.*

## Document control

| Field | Value |
|---|---|
| Document ID | EM-04 |
| Revision | A |
| Owner role | Energy coordinator |
| Applies to | All DemoTronics energy documents (EM, EQ and SOP series) |

## How to use this glossary

Terms are grouped by topic. Where a term has a plant-specific meaning, the meaning given here is the one used in all DemoTronics documents.

## Billing and demand terms

### 15-minute demand
The average power in kW over a fixed 15-minute interval. Billing demand is based on this value and not on instantaneous readings.

### Contract capacity
The kW demand the plant has contracted for. At DemoTronics this is 1,250 kW on a regular contract.

### Warning line
90% of contract capacity, which is 1,125 kW. A projected demand at or above this line raises WARNING.

### Projected demand
The expected 15-minute demand if the present load continues, calculated as (kWh so far in the interval + present kW x remaining minutes) / 15, with energy so far expressed in kW-minutes.

### P(exceed)
The forecast probability that demand will exceed the contract in the next hour. 20% or more raises WARNING; 50% or more raises ALARM.

### Exceedance
Demand above contract capacity in an interval. The excess is billed at the period's contract price x2 up to 10% over the contract and x3 beyond.

### Time-of-use (TOU)
A tariff in which the price of energy depends on the time of day and the day type. See EM-03.

### Peak, half-peak and off-peak
The three price periods of the three-segment tariff. Peak has the highest price and off-peak the lowest.

### Demand charge
The monthly charge per kW of contract capacity, independent of use.

## Electrical terms

### kWh register
The cumulative energy counter of a meter. It should only increase. A decrease or reset is a data-quality event (SOP-07).

### Active power (kW)
The real power that does work or produces heat.

### Reactive power (kvar)
Power that moves between source and load without doing work. Motors and transformers need it.

### Power factor (PF)
The ratio of active power to apparent power. A value of 1.00 means no reactive power is drawn. Lower values mean more reactive current for the same useful power.

### kvar
The unit of reactive power.

### Capacitor bank
Equipment that supplies reactive power locally so that it is not drawn from the grid. At DemoTronics the capacitor banks cancel 55% of each feeder's reactive power.

### Low power factor rule
The monitoring rule that fires when a board's 15-minute PF is below 0.90 with load above 10% of rating for 60 minutes or more.

### Feeder
A main distribution board (MDB-1 to MDB-6) that supplies an area. The feeders add up to the plant total.

### Sub-meter
A meter on a single machine or group, for example RF-01 or CH-02.

### Nominal line voltage
380 V, three-phase.

## Load and equipment terms

### Rated kW
The nameplate power of a machine. The sum of ratings is about 1,480 kW.

### Diversity
The fact that not all machines run at full load at once. The plant relies on a diversity of about 0.75.

### Base load
The load present all hours. At DemoTronics the night base load is about 500 kW.

### Idle energy
Energy used by a machine that is running or hot but not producing.

### Standby
A low-power state in which a machine is kept ready. A reflow oven in standby draws 36% of rating.

### VSD (variable speed drive)
A drive that changes motor speed to match demand. AC-03 is a VSD trim compressor.

### Lead/lag
The staging of two machines. The lead machine takes the load first; the lag machine is added only when needed. CH-01 is lead and CH-02 lag; AC-01 is base and AC-02 lag.

### Trim machine
A compressor that follows small changes in demand, so that the base machine can run steadily.

### Load/unload
The mode of a fixed-speed compressor that alternates between delivering air and running without delivering air.

### Barrel heat-up
The period in which an injection molder heats its barrel before production.

### Preheat
The period in which a machine such as the wave solder machine heats before production.

### Burn-in
A long thermal stress test of finished boards in a chamber.

## Monitoring terms

### RUNNING, IDLE, OFF
The equipment status classes: RUNNING above 20% of rating, IDLE above 3%, otherwise OFF.

### Stale meter
A meter with no reading for more than 180 seconds. Readings are normally every 60 seconds.

### CUSUM
A cumulative sum method that adds up small, repeated deviations from an expected value so that slow drifts become visible. It is used for the air-leak baseline.

### Robust sigma
A measure of spread that is not affected by occasional outliers.

### Night-load baseline
The compressor load between 02:00 and 05:00, compared with the median of the last 6 similar nights.

### Simultaneous start rule
The rule that fires when 6 or more machines go from below 15% to above 40% of rating within 3 minutes.

### Off-schedule rule
The rule that fires when a machine runs above 20% of rating at an hour it normally runs less than 5% of the time, for 120 minutes or more.

### Load-shed playbook
The ordered list of actions that reduce load in minutes. See EM-02.

### Never-shed list
The equipment that is not shed under any condition: the server room, running molders mid-cycle and reflow ovens with boards inside.

### Incident scenarios S2, S3, S4, S5, S8
Labelled events in the 2025 data used as references in the procedures.
