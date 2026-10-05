# HQ grid rainfall nowcast: preliminary 2025 findings

Task 1 supplementary track. Target dates: 2025-01-01–2025-12-31.
Results describe successive-nowcast daily composites against the HKO Headquarters point gauge.

## Findings

The replay has 8,754 hourly samples and 35,016 native windows.
Forecast coverage is complete for 360 of 365 days.
Five dates lack 396 minutes of forecast coverage.
All 365 gauge observations have completeness code C.
The 53 Trace observations retain [0, 0.05) mm bounds.

Exact losses use 308 complete numeric common cases.
All source extremes remain in the primary result.

## Concrete results

| Metric | Estimate | 95% block-bootstrap CI |
|---|---:|---:|
| MAE (mm) | 5.578 | [2.695, 9.255] |
| RMSE (mm) | 27.640 | [9.807, 43.563] |
| Bias (mm) | -1.221 | [-4.159, 2.182] |

Zero-rain baseline MAE is 7.753 mm on the same cases.
MAE skill relative to that baseline is 0.281.
Paired MAE gain is 2.175 mm, with 95% CI [-1.229, 5.230].
That CI crosses zero.
This comparison does not establish consistent improvement over the zero-rain baseline.
Persistence and climatology have not been evaluated in this track.

CIs use 2,000 circular seven-calendar-day block-bootstrap draws.
The random seed is 3522.

Including Trace bounds across all 360 complete days gives MAE [4.823, 4.830] mm.
This is a censoring envelope, not a confidence interval.
Its population differs from the 308-day numeric-only result.

## Monthly exploratory results

| Month | Complete days | Numeric cases | Trace days | MAE mm | RMSE mm | Bias mm |
|---|---:|---:|---:|---:|---:|---:|
| 2025-01 | 31/31 | 26 | 5 | 0.117 | 0.440 | +0.068 |
| 2025-02 | 28/28 | 20 | 8 | 0.749 | 3.085 | -0.658 |
| 2025-03 | 31/31 | 24 | 7 | 1.629 | 5.104 | +0.602 |
| 2025-04 | 30/30 | 25 | 5 | 1.028 | 2.302 | -0.624 |
| 2025-05 | 31/31 | 23 | 8 | 19.581 | 81.088 | +16.294 |
| 2025-06 | 30/30 | 28 | 2 | 4.456 | 9.900 | -1.618 |
| 2025-07 | 31/31 | 30 | 1 | 11.376 | 25.506 | -6.090 |
| 2025-08 | 31/31 | 31 | 0 | 13.874 | 40.284 | -13.376 |
| 2025-09 | 28/30 | 26 | 2 | 8.766 | 19.865 | -4.323 |
| 2025-10 | 30/31 | 23 | 8 | 1.797 | 3.142 | +0.685 |
| 2025-11 | 30/30 | 25 | 5 | 0.428 | 1.347 | -0.050 |
| 2025-12 | 29/31 | 27 | 2 | 0.322 | 0.920 | +0.078 |

July and August show larger errors than the dry winter months.
These exploratory comparisons do not control weather difficulty or rainfall amount.
They do not establish a causal seasonal effect.

## Largest errors and source-spike influence

| Date | Composite mm | Gauge mm | Difference mm |
|---|---:|---:|---:|
| 2025-05-30 | 393.384 | 6.400 | +386.984 |
| 2025-08-05 | 161.442 | 368.900 | -207.458 |
| 2025-07-29 | 10.024 | 106.500 | -96.476 |
| 2025-07-22 | 26.036 | 95.700 | -69.664 |
| 2025-09-21 | 14.088 | 81.600 | -67.512 |

The 2025-05-30 source contains native half-hour values of 230.36 and 162.82 mm.
An independent redownload returned the same SHA-256.
The upstream cause remains unknown.
Both values remain in the primary result with diagnostic flags.
That day accounts for 63.6% of numeric squared error.

Post-hoc exclusion of that day gives MAE 4.336 mm and RMSE 16.693 mm.
This is an influence diagnostic, not evidence that the day is invalid.

## Coverage limitations

| Incomplete date | Missing minutes | Gauge original mm |
|---|---:|---|
| 2025-09-19 | 42 | 0.4 |
| 2025-09-24 | 96 | 170.1 |
| 2025-10-30 | 30 | Trace |
| 2025-12-06 | 210 | 0.0 |
| 2025-12-10 | 18 | 0.2 |

The excluded 2025-09-24 day has 170.1 mm of observed rain.
Missingness cannot be assumed independent of weather conditions.
Reported losses therefore describe complete common cases.

## Measurement and verification limits

The [method note](../README.md) defines availability, overlap handling and daily boundaries.
Within-window splits assume uniform rainfall intensity.
Grid-area rainfall and point-gauge rainfall have different spatial support.
The daily composite mixes horizons and forecast vintages.
It does not verify fixed-lead accuracy, nine-day PSR calibration or long-term improvement.

Raw hashes and HQ re-extraction were checked for all 8,754 samples.
The 181 January–June daily results exactly match the previous half-year replay.
Five pipeline checks passed.
Database observations matched the official CSV on all 365 dates.
Committed table counts, keys, date bounds and timestamps were checked.

The [verification receipt](verification.json) states the scope and source fingerprints.
These are preliminary descriptive findings, not a finalized benchmark.

## Annual comparison figure

![HQ-nearby annual rainfall comparison](daily_comparison.png)
