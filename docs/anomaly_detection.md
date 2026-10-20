# Anomaly detection

Anomaly detection runs in three layers, from the most explainable to the least. Each layer
catches something the previous one cannot, and every detection records which layer produced it.
All data is synthetic; the plant is fictional.

| Layer | Method | Purpose |
|---|---|---|
| RULE | Explainable engineer rules | Known, nameable problems (simultaneous start-up, off-schedule running, low power factor, demand above contract) |
| BASELINE | CUSUM on nightly base load | Slow drifts that no single reading reveals (air leak) |
| ML | IsolationForest on daily fingerprints | "Something unusual happened" for patterns nobody wrote a rule for |

## Layer 1: rules (`anomaly/rules.py`)

- **Simultaneous start** (`SIMULTANEOUS_START`, high). A machine start is a 15-minute mean
  before the minute below 15% of rating and a 5-minute mean after it above 40% of rating.
  Starting categories: reflow ovens, injection molders, wave soldering, chillers, fixed-speed
  compressors. A detection needs at least 6 such machines starting within 3 minutes.
- **Off-schedule running** (`OFF_SCHEDULE_RUNNING`, medium). Scheduled categories (reflow ovens,
  SMT lines, injection molders, wave soldering) drawing more than 20% of rating at a day-type and
  hour where the usual share of running is below 5%. The usual share is computed
  leave-one-day-out, so one long incident does not teach the detector that it is normal. The run
  must last at least 120 minutes; gaps of up to 10 minutes are bridged.
- **Low power factor** (`LOW_POWER_FACTOR`, medium). Feeder 15-minute rolling power factor below
  0.90 while the feeder load is above 10% of its rating, for at least 60 minutes. Gaps of up to
  60 minutes are bridged. The 0.90 line is an early warning: under the Taipower tariff the bill
  only carries a surcharge below 0.80, but every point under 0.95 already reduces the monthly
  power-factor credit.
- **Demand exceedance** (`DEMAND_EXCEEDANCE`, high). A fixed 15-minute plant demand interval
  above the contract capacity.

## Layer 2: baseline drift (`anomaly/baseline.py`)

CUSUM runs on the nightly base load (mean of 02:00-05:00) of the **compressed-air system only**.
Weather-driven feeders such as HVAC are deliberately excluded: their night load follows the
temperature, so a drift test would need weather normalisation first (see limitations).

- Nights after a workday and nights after a rest day are compared separately, because
  around-the-clock lines are still running after a workday.
- Expected value: median of the last 6 normal nights of the same kind.
- Noise: robust sigma from the median absolute deviation (MAD), floored at
  max(1 kW, 2% of the median level).
- CUSUM allowance k = 0.5 and alarm threshold h = 8 (in sigmas). An alarm additionally needs the
  night to be more than 3 kW above expectation.
- The baseline is frozen while a drift lasts, so a slow leak is not learned as normal. The
  episode closes after 2 calm nights and learning resumes.

## Layer 3: machine learning (`anomaly/ml.py`)

An IsolationForest scores each equipment meter-day from a daily fingerprint: mean, 95th
percentile and standard deviation of load relative to rating, night and evening means, share of
time on, average power factor, one-hot day type and mean temperature. It reports `UNUSUAL_DAY`
with low severity.

- Holidays and the day after a holiday are suppressed as calendar-explained.
- Day type and temperature are context features. They help the forest model what is normal but
  are never offered as the explanation; the message names the most different load-shape feature.
- Only clearly isolated days are reported (contamination 1%, minimum score 0.015).
- Loads that barely move all year (coefficient of variation of the minute readings below 5%,
  such as the server room and the EV bank) are skipped: they have no daily shape to be unusual about, and the
  forest would only report noise.

## Detection time (`detected_at`)

Each detection carries `detected_at` (column `detected_ts`): the moment it could first have been
raised, as opposed to when the problem started. The dashboard replay uses it so nothing appears
early.

- Rules: start plus the time the rule needs to be sure: simultaneous start +8 min, off-schedule
  +120 min, low power factor +60 min; demand exceedance at the end of the interval.
- CUSUM: 06:00 after the alarm night (nightly batch).
- ML: 06:00 the next day (daily batch).

## Evaluation

Detections are scored against the simulator's ground-truth labels at event level.

- A detection matches a label when their intervals overlap within a tolerance of +/-30 minutes
  and they have the same event type and share a meter (or the label is plant-wide, `PLANT`).
- ML detections do not name a fault type, so they match any label on related equipment (for
  example sub-meters under a labelled feeder).
- `HEAT_WAVE` is context for the other scenarios and is not scored.
- **Precision** = detections matching a label / all detections.
  **Recall** = labels matched by at least one detection / labels.
  **Median delay** = median over found labels of (first matching `detected_at` - label start),
  never negative.

## Results

Default run (`--seed 42`, year 2025, all scenarios):

| | detections | precision | labels | recall | median delay |
|---|---|---|---|---|---|
| SIMULTANEOUS_START | 1 | 100% | 1 | 100% | 5 min |
| DEMAND_EXCEEDANCE | 23 | 100% | 23 | 100% | 0 min |
| OFF_SCHEDULE_RUNNING | 2 | 100% | 1 | 100% | 2.5 h |
| LOW_POWER_FACTOR | 2 | 100% | 1 | 100% | 1.1 h |
| AIR_LEAK | 1 | 100% | 1 | 100% | 8 days |
| layer RULE | 28 | 100% | 27 | 96% | |
| layer BASELINE | 1 | 100% | 27 | 4% | |
| layer ML | 19 | 68% | 27 | 11% | ~1.4 days |
| all layers | 48 | 88% | 27 | 100% | |

How to read this honestly:

- The air leak starts small, so the 8-day delay is expected: the CUSUM alarm fires only once the
  leak is large enough to be distinguishable from night-to-night noise, and is then reported at
  06:00 after that night.
- Layer recall is measured against all 27 scored labels. A specialised layer (BASELINE only looks
  at compressed air) therefore has low recall by design; the layers complement each other.
- ML "false positives" are mostly genuinely unusual days that the simulator did not label, such
  as hot afternoons and heat spells. That is why ML
  is presented as a low-severity hint layer rather than an alarm source.
- ML recall is low (11%), so no labelled incident depends on it; it only adds hints that the rules and baseline did not produce.
- Without being told what to look for, the forest still flagged the compressed-air days of the leak (AC-01..03, mid-late Sep) and the S5 weekend when RF-02 was left running (18-20 Oct); its other flags are chillers and the cooling tower on hot days (CH-02, CT-01), one RF-03 day and one EV-01 day, none labelled by the simulator.

## Running it

```bash
python -m factory_energy detect [--db data/plant.duckdb] [--no-ml]
```

Results are written to the `detections` table (id, layer, detector, event type, meter ids,
start, end, severity, score, message) and the scores above are printed. `--no-ml` skips the
IsolationForest layer, which is the slowest part.

## Limitations and next steps

- Weather-normalised baselines (for example regression against temperature) would let the drift
  test cover HVAC and other weather-driven feeders.
- The rules run in batch over the stored history; the dashboard replays them using `detected_at`
  rather than running a true streaming detector.
- Demand exceedance is detected after the fact; forecast-based early warnings come with load
  forecasting in P4.
- Thresholds are tuned on one synthetic plant; real meters would need re-tuning and data-quality
  checks (scenario S10).
