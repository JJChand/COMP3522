# HQ grid rainfall nowcast: 2025 daily proxy

This supplementary Task 1 track evaluates a nearby-HQ rainfall amount proxy.
It supports forecast validity and exploratory failure-condition analysis.
Start with the [preliminary findings](results/findings.md).

## Dataset

| Layer | Content | Rows |
|---|---|---:|
| `project.hko_grid_nowcast_hq_2025` | HQ-nearby native half-hour forecast windows | 35,016 |
| `project.hko_grid_nowcast_hq_daily_2025` | Daily composites, observations, coverage and errors | 365 |

The selected grid coordinate is 22.304°N, 114.182°E.
Truth comes from the official HKO Headquarters daily point gauge.
Study dates are 2025-01-01 through 2025-12-31.
Both database tables were imported and validated on 2026-10-05 HKT.
The [canonical database guide](../../DATABASE_AGENT_GUIDE.md) records types and primary keys.

HKO provides four half-hour accumulation windows through the next two hours.
Native lead-to-end values are 30, 60, 90 and 120 minutes.
Hourly archive targets select the latest existing capture at each target.
Two 2024-12-31 captures provide year-boundary padding.
These 8,754 sampled captures are not every published update.

## Measurement contract

Archive capture time is a conservative known-available proxy.
It is separate from the forecast's update time and later retrieval time.
Only windows starting at or after known availability enter the daily replay.
Overlapping windows are split into disjoint segments.
Each segment uses the latest eligible issue.

Daily windows use HKT 00:00–24:00 as an explicit research assumption.
Splitting a native half-hour window assumes uniform rainfall intensity within that window.
No observed rain enters forecast selection.
Unknown segments remain missing.
Incomplete daily composites remain blank.

The daily composite mixes successive nowcasts and horizons.
It is a spatial proxy against a nearby point gauge.
These losses do not verify fixed-lead half-hour accuracy or nine-day PSR calibration.
No aligned half-hour gauge truth was available for this analysis.

## Exported results

| File | Content |
|---|---|
| [daily_comparison.csv](results/daily_comparison.csv) | All 365 daily cases, bounds, coverage and allocated lead minutes |
| [monthly_summary.csv](results/monthly_summary.csv) | Monthly common-case losses and case counts |
| [overall_scores.csv](results/overall_scores.csv) | Numeric losses, block CIs and the zero-rain baseline |
| [coverage_gaps.csv](results/coverage_gaps.csv) | Five incomplete dates and their missing minutes |
| [largest_daily_errors.csv](results/largest_daily_errors.csv) | Five largest absolute numeric errors |
| [source_spike_evidence.json](results/source_spike_evidence.json) | Official archive URL, native values and matching redownload hashes |
| [verification.json](results/verification.json) | Verification scope, case counts, sensitivity and export hashes |
| [daily_comparison.png](results/daily_comparison.png) | Original annual comparison figure |

Rainfall columns use mm.
`observed_original` preserves `Trace`.
Trace bounds are [0, 0.05) mm; `observed_mm` remains blank.
`difference_mm` is composite minus gauge and requires complete numeric cases.
The lower and upper difference columns retain censoring bounds.

`coverage_complete` requires 1,440 covered minutes.
The four `lead_*_minutes` columns allocate elapsed time, not forecast counts.
`contains_extreme_source_value` flags contributing native values of at least 100 mm.
This diagnostic flag does not exclude data.
Full native windows and provenance remain in the database and local raw archive.

## Query existing database results

Use the repository's existing read-only connection setup.
The following bounded query reads the imported daily results:

```sql
SELECT date_hkt, daily_composite_mm, observed_original,
       coverage_complete, missing_minutes, difference_mm
FROM project.hko_grid_nowcast_hq_daily_2025
WHERE date_hkt BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'
ORDER BY date_hkt;
```

No new acquisition or database write is required to inspect these results.

## Sources

- [Official Grid product](https://data.gov.hk/en-data/dataset/hk-hko-rss-gridded-rainfall-nowcast-in-hong-kong)
- [Official Grid field documentation](https://data.weather.gov.hk/weatherAPI/hko_data/F3/HKO_gridded_rainfall_nowcast_documentation.pdf)
- [Official daily rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall)
- [Historical archive API](https://data.gov.hk/en/help/api-spec)

Source pages were checked on 2026-10-04 HKT.
