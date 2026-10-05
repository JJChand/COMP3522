# Preliminary regional RH interval findings

Documented 2026-10-05; study year 2025. See [the metric and execution
protocol](../REGIONAL_RH_METHOD.md) for definitions, pairing and uncertainty.

Expanding the sampled reference from 20 to 26 stations raises the mean forecast
Hausdorff discrepancy by **0.50 pp** on the same 89 complete dates (95% day-block
CI **0.25–0.80**). The added stations more often exceed the forecast upper endpoint.
Most of the discrepancy increase is associated with the new regional maxima
supplied by Tsak Yue Wu (TYW, 北潭涌).

These are exploratory reference-sensitivity findings. They do not establish
official HKO accuracy, probabilistic calibration or full-year regional performance.
The existing Headquarters daily-report results remain a separate measurement track.

## 1. Acquired data and coverage

| Coverage item | Result |
| --- | ---: |
| Current RH-equipped land-station reference | 33 stations; 31 automatic |
| Acquired 2025 subdaily station sources | 26 |
| Numeric canonical readings across acquired year | 1,353,213 |
| Original fixed-20 complete dates | 133/365 |
| All-26 complete dates | 89/365 |
| Partial all-acquired observed envelopes retained | 276/365 |
| Complete 33-station dates | 0/365 |
| Primary paired forecast cases | 801, sharing 89 weather dates |

The six added stations are HKP (Hong Kong Park), JKB (Tseung Kwan O), SHA (Sha Tin),
TKL (Ta Kwu Ling), TY1 (Tsing Yi) and TYW (北潭涌). They were already present in the
acquired raw archive; this expansion includes them in the interval comparison.
The analysis uses all valid sampled readings, rather than station daily means.

The remaining seven subdaily sources are BR1, NLS, SLW, TMS, TC, TWN and TW.
Current 28-station hourly chart samples include the two Tsuen Wan stations, but
the retrieved dates are 2026-10-04–05; they were not used to fill 2025 gaps.
The current 33-station register does not certify full-year historical RH operation.

## 2. Paired forecast discrepancy: 20 versus 26 stations

Every row below uses the same 89 dates and the same forecast vintage for both
references. Distances are percentage points. Brackets give the paired mean
change's 95% block CI. Min/max are observed sample extrema, not CI endpoints.

| Calendar lead | R20 mean | R26 mean | Mean change [95% CI] | R20 min–max | R26 min–max |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 14.26 | 14.88 | +0.62 [0.35,0.95] | 4–27 | 4–30 |
| 2 | 15.06 | 15.48 | +0.43 [0.12,0.78] | 5–32 | 5–32 |
| 3 | 16.18 | 16.62 | +0.44 [0.13,0.79] | 5–36 | 5–36 |
| 4 | 16.28 | 16.78 | +0.49 [0.18,0.84] | 5–36 | 5–36 |
| 5 | 16.18 | 16.74 | +0.56 [0.28,0.90] | 5–39 | 5–39 |
| 6 | 16.70 | 17.25 | +0.55 [0.25,0.89] | 1–45 | 1–45 |
| 7 | 18.17 | 18.73 | +0.56 [0.26,0.90] | 5–55 | 5–55 |
| 8 | 18.92 | 19.36 | +0.44 [0.19,0.73] | 5–55 | 5–55 |
| 9 | 19.10 | 19.55 | +0.45 [0.23,0.71] | 5–55 | 5–55 |

Equal-lead pooled descriptive statistics:

| Statistic | R20 forecast distance | R26 forecast distance |
| --- | ---: | ---: |
| Mean [95% block CI] | 16.76 [15.21,18.35] | 17.26 [15.57,19.01] |
| Median | 16 | 17 |
| q25 / q75 | 11 / 21 | 11 / 22 |
| q90 / q95 | 25 / 29 | 28 / 30 |
| Minimum / maximum | 1 / 55 | 1 / 55 |

Of 801 pairs, 138 distances increase, 660 remain unchanged and three decrease.
The largest individual change is +10 pp; the smallest is −5 pp.

The minimum distance, 1 pp, occurs on 2025-02-25 at lead 6: forecast [55%,90%]
and both references [54%,90%]. The maximum, 55 pp, occurs on 2025-04-13 at
leads 7–9: forecast [70%,95%], R20=[15%,70%] and R26=[15%,86%]. The lower-end
55-pp discrepancy still dominates despite the higher observed upper endpoint.

## 3. Separate station change from date selection

The previous R20 headline used 133 complete dates. At lead 9 it reported a
mean of 18.71 pp. Restricting R20 to the paired 89 dates produces 19.10 pp;
switching the same dates to R26 produces 19.55 pp. The station-reference effect
is +0.45 pp, while about +0.39 pp comes from the date-selection change.

Also distinguish the two reconstructed references' own distance,
`dH(R20,R26)`, from the change in forecast discrepancy. On 89 dates, their direct
mean distance is 1.18 pp (95% CI 0.73–1.66), median 0, minimum 0 and maximum 16.
Their endpoints are identical on 59 dates. This 1.18 is not the +0.50 mean
forecast-distance change above.

## 4. Do added-station readings fall outside the forecast more often?

The table compares **original-20 readings with added-six readings**, not the
original 20 with the mixed 26-station population. It uses identical dates,
144 numeric readings per station/day and equal lead 1–9 weights.

| Reading position | Original 20 | Added six |
| --- | ---: | ---: |
| Below forecast minimum | 14.73% | 14.46% |
| Within forecast endpoints, inclusive | 65.68% | 61.47% |
| Above forecast maximum | 19.59% | 24.07% |
| Outside, either side | 34.32% | 38.53% |

The paired outside-rate difference is +4.21 pp (95% day-block CI 2.68–5.82).
Most added-station readings still lie inside. Their higher outside rate is
mainly on the upper side, rather than below the lower endpoint.

| Added station | Pooled outside proportion |
| --- | ---: |
| Hong Kong Park, HKP | 25.37% |
| Tseung Kwan O, JKB | 41.91% |
| Sha Tin, SHA | 31.33% |
| Ta Kwu Ling, TKL | 46.33% |
| Tsing Yi, TY1 | 31.97% |
| TYW, 北潭涌 | 54.24% |

HKP, SHA and TY1 are below the original-20 pooled proportion; JKB, TKL and TYW
are above it. This is a descriptive spatial difference on selected dates,
not a generalized station ranking or an explanation of geographic causes.
The same physical readings are compared repeatedly across leads; they are not
independent samples for uncertainty estimation.

## 5. Why does Hausdorff increase?

Hausdorff depends on the farther endpoint, not the number of outside readings.
The reference changes decompose as follows:

| Reference change | Weather dates | Forecast cases | Distance increases | Unchanged | Decreases |
| --- | ---: | ---: | ---: | ---: | ---: |
| Neither endpoint changes | 59 | 531 | 0 | 531 | 0 |
| Upper endpoint rises | 26 | 234 | 119 | 115 | 0 |
| Lower endpoint falls | 4 | 36 | 19 | 14 | 3 |

All 26 raised upper endpoints come from TYW. Thus 119/138 increases are associated
with its new upper extrema. Lower extensions come from TKL on two dates, TY1 on
one and TYW on one. The 115 upper-extension cases with unchanged distance are
still dominated by the lower-end discrepancy.

| Valid date / lead | Forecast | R20 | R26 | Distance change |
| --- | --- | --- | --- | ---: |
| 2025-11-21 / 1 | [35%,55%] | [27%,75%] | [27%,85%] | 20 → 30 |
| 2025-07-18 / 2 | [55%,95%] | [70%,100%] | [65%,100%] | 15 → 10 |

On 2025-11-21, TYW supplies the new maximum of 85%. Yet 121/144 of its readings
are inside the forecast, 20 above and three below. A minority of high readings
can increase the endpoint distance. The selected forecast was issued
2025-11-20 19:50 HKT (forecast ID 5505).

On 2025-07-18, TKL supplies a new minimum of 65%, closer to the forecast minimum
of 55%. The distance falls. That new minimum is itself inside the forecast.
The selected lead-2 forecast was issued 2025-07-16 20:50 HKT (ID 5003).
Lead 3 and 4 on the same date also decrease by 5 pp; these are the only decreases.
These examples were selected for extreme changes, not as typical days.

## 6. Width and averaging context

Across all 365 forecast valid dates, median forecast width is 25 pp at every
lead. In the original R20 comparison on 133 complete dates, the lead-1 forecast
is narrower than the sampled regional envelope on 130/133 dates (97.7%).
Its mean width is 26.99 pp, versus 47.44 pp for R20.

A separate same-15-station, same-182-date comparison found mean distance
19.57 pp (95% block CI 18.45–20.73) between the daily-means spatial range and
the sampled temporal envelope. This supports keeping those targets separate.
These different panels and date sets are context, not additional observations
in the paired 89-date result. Forecast width is not automatically uncertainty.

## 7. Interpretation and remaining gates

The expanded reference exposes higher regional sampled RH maxima that the
20-station reference omitted on some dates. This explains the arithmetic
increase in discrepancy; it does not establish a change in forecast skill or
the meteorological cause of TYW's differences.

Before making a stronger accuracy claim, resolve historical station eligibility,
the seven missing subdaily sources, sampled versus full-extrema semantics,
the public product's spatial target, and the weather distribution of excluded
dates. An observed envelope retains spatial and sampling uncertainty.

No acceptable Hausdorff tolerance has been selected. The exploratory 5/10/15-pp
agreement scenarios are not official accuracy criteria. A same-sample q95
threshold cannot independently define an acceptable forecast error.

This is a method/findings documentation supplement. Regional raw data, scripts,
database imports and schema changes are outside this update. The method document
states its execution and reproducibility boundary explicitly.
