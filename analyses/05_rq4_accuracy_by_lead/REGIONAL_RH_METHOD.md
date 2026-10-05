# Regional relative-humidity intervals: metric and execution protocol

Status: preliminary Task 1 reference-sensitivity analysis, documented 2026-10-05.
Study year: 2025. See [the preliminary findings](results/regional_rh_findings.md).

This supplement asks how the comparison changes when a sampled regional RH
reference expands from 20 to 26 stations. It supports RQ4 measurement/accuracy
methodology and the spatial-reference questions relevant to RQ7. The existing
Headquarters daily-report analysis remains a separate track.

## Measurement definitions

| Object | Definition |
| --- | --- |
| Forecast F | HKO public nine-day daily RH minimum and maximum, from retained forecast vintages |
| Station interval I(s,d) | Minimum and maximum of valid sampled RH readings at station s during HKT date d |
| Regional interval R(S,d) | Minimum and maximum across all sampled readings at stations in fixed panel S on date d |
| R20 | The original, frozen 20-station feasibility panel |
| R26 | All 26 station sources acquired for 2025 |
| Day window | 00:00 HKT inclusive to next 00:00 HKT exclusive |
| Calendar lead | Valid date minus bulletin issue date; lead 1 does not guarantee a full 24-hour advance |
| Unit | RH endpoints in percent; distances and endpoint differences in percentage points (pp) |

The regional source publishes a one-minute mean at nominal ten-minute updates.
Its sampled min/max cannot be described as full-minute daily extrema. A range
across station daily means is also a different target: averaging removes
within-day variation.

The public forecast is not established here as a prediction of the extrema
across every regional station. Call the results **reference discrepancy or
station-panel sensitivity**, rather than official HKO accuracy. The forecast
min/max range is not a probabilistic interval with a stated coverage level.

## Station panels and data coverage

The frozen R20 codes are:

```text
CCH CWB HKA HKO HKS KLT KP KSC LFS PEN
SE1 SEK SKG SKW SSH TLS TU1 WGL WLP YCT
```

R26 additionally includes HKP, JKB, SHA, TKL, TY1 and TYW. All valid acquired
readings participate in the station/day intervals. Missing values are not
imputed, and partial-day observed ranges are retained with explicit flags.

For the primary paired comparison, require 144 unique numeric nominal
ten-minute slots at every station in the 26-station panel. Use the same complete
valid dates for R20 and R26. There are 89 eligible dates in 2025, with nine leads
each. Do not compare the original R20 average over 133 dates directly with the
R26 average over 89 dates and attribute the difference entirely to station scope.

The current HKO register identifies 33 RH-equipped land stations, including
31 automatic stations. That current inventory does not certify historical RH
operation throughout 2025. Seven historical subdaily sources remain missing:
BR1, NLS, SLW, TMS, TC, TWN and TW. Daily means cannot fill those extrema gaps.

## Execution procedure

1. Retain observation timestamps, station codes, numeric RH values and raw
   provenance. Sort duplicate station/observation-time captures by capture time
   and use the latest capture, following the frozen acquisition policy. Keep
   conflict records and the previously evaluated earliest-capture sensitivity.
2. Convert observation timestamps to HKT. Group by station and HKT date, calculate
   sampled min/max, and audit numeric nominal slots. Do not treat repeated archive
   captures as additional observation times.
3. Form R20 and R26 by taking the minimum of station minima and maximum of station
   maxima. Save completeness flags and partial observed ranges separately.
4. Use the archived bulletin update/issue time. Select the latest bulletin within
   each issue calendar day for each valid date and positive lead 1–9, as in the
   existing daily-latest design. Retain forecast IDs and source fingerprints.
   Do not substitute a final forecast snapshot for an earlier vintage.
5. Match on valid HKT date. For each date/lead, use exactly the same forecast ID,
   issue timestamp and forecast endpoints for both station references. Apply the
   common 89-date gate before calculating paired effects.
6. Calculate the distances below, summarize separately by lead, and retain
   case-level endpoint differences. An equally weighted nine-lead pooled summary
   is descriptive; its 801 pairs share only 89 weather dates.

## Hausdorff metric

For closed one-dimensional intervals A=[La,Ua] and B=[Lb,Ub]:

```text
dH(A,B) = max(abs(La-Lb), abs(Ua-Ub))
D20 = dH(F,R20)
D26 = dH(F,R26)
paired change = D26-D20
station-panel distance = dH(R20,R26)
```

A positive paired change means the same forecast is farther from R26 than R20.
The station-panel distance is a different quantity; it is not the change in
forecast discrepancy. Expanding the station set makes R26 contain R20, but
does not guarantee that D26 increases.

An implementation of the metric, using percent-valued endpoints:

```python
def hausdorff_interval(a, b):
    if a[0] > a[1] or b[0] > b[1]:
        raise ValueError("Interval endpoints must be ordered")
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

forecast = (35, 55)
d20 = hausdorff_interval(forecast, (27, 75))  # 20 pp
d26 = hausdorff_interval(forecast, (27, 85))  # 30 pp
change = d26 - d20                           # +10 pp
```

Report mean, median, quantiles, observed minimum/maximum and paired changes.
Endpoint, center and width diagnostics help explain the distance. In particular:

```text
dH = abs(centerA-centerB) + abs(widthA-widthB)/2
```

These are deterministic-range metrics. Do not apply a nominal-coverage interval
score without first establishing the necessary predictive-quantile semantics.

## Reading inclusion and endpoint diagnosis

Classify each numeric reading x against the same date/lead forecast:

```text
below:  x < forecast_min
inside: forecast_min <= x <= forecast_max
above:  x > forecast_max
outside = below + above
```

Compare the original 20 stations with the added six, using the same 89 dates,
144 readings per station/day and equal lead weights. These are reading-inclusion
diagnostics, not probabilistic calibration scores. A single new extreme can
alter Hausdorff, while many outside readings may leave the regional endpoints
unchanged.

For attribution, record whether R26 lowers the regional minimum or raises its
maximum, which new stations supply that endpoint, and whether that change affects
the larger forecast-endpoint discrepancy. Keep decreases and unchanged cases.

## Uncertainty, checks and tolerance

Mean/rate CIs use 2,000 circular seven-calendar-day block-bootstrap samples over
the full 365-day HKT calendar, retaining the missing-date mask; seed 3522.
Resample weather dates, not individual stations/readings. Pooled CIs first average
the nine leads within each date. Report the paired difference CI rather than
judging change by overlap of separate marginal CIs. Seven-day blocks follow the
existing exploratory protocol; no optimal-block-length claim is made.

Checks completed in the companion analysis include frozen input hashes, unique
station/time keys, valid RH bounds, 144-slot completeness, reconstructed
station-panel endpoints, matched forecast IDs/times, distance arithmetic,
reading-count accounting and direct example checks. CIs do not compensate for
the missing 276 dates, missing seven stations or spatial-target mismatch.

**No acceptable tolerance has been adopted.** Values 5/10/15 pp were explored
only as agreement scenarios. Define acceptable endpoint discrepancy from the
intended use, then evaluate on later data. A quantile of the same discrepancy
sample is a descriptive threshold, not an independently justified acceptable
standard. Sampling/reconstruction error also needs an independent aligned
reference before it can provide a validated error bound.

## Reproducibility boundary and sources

This documentation-only update summarizes work already executed outside this
repository. It does not include regional raw inputs, acquisition code or a
repository run command. The existing database-backed `run_analysis.py` computes
the Headquarters track and does not reproduce these regional findings.

Minimum inputs for a reimplementation are station/time RH observations and
forecast records with valid date, issue timestamp, forecast ID and RH endpoints.
The frozen canonical-observation gzip had SHA-256:

```text
846f8bd47f16e5620ab5bb4d028d5400f92d1f2c8279515e087d88062a32cfca
```

Official source context, checked 2026-10-05:

- [HKO one-minute mean RH dataset](https://data.gov.hk/en-data/dataset/hk-hko-rss-latest-one-minute-mean-rh).
- [HKO station register](https://www.hko.gov.hk/en/cis/stn.htm).
- [HKO nine-day forecast product](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm).

Archive availability is source/date-specific. Current readings and station
metadata do not establish historical 2025 coverage.
