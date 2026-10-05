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

## Published findings

The [findings note](results/findings.md) reports losses, the dominant source spike, heavy-rain errors and coverage limitations.
The [annual figure](results/daily_comparison.png) compares daily composites with Headquarters observations.
Rainfall values use mm.
Trace observations retain [0, 0.05) mm bounds.
Complete days require 1,440 covered minutes.
Native windows, daily records and provenance remain in the database and local archive.

## Sources

- [Official Grid product](https://data.gov.hk/en-data/dataset/hk-hko-rss-gridded-rainfall-nowcast-in-hong-kong)
- [Official Grid field documentation](https://data.weather.gov.hk/weatherAPI/hko_data/F3/HKO_gridded_rainfall_nowcast_documentation.pdf)
- [Official daily rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall)
- [Historical archive API](https://data.gov.hk/en/help/api-spec)

Source pages were checked on 2026-10-04 HKT.
