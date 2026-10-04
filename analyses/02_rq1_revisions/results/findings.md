# RQ1 — successive forecast revisions

Exploratory Task 1 results. This analysis does not evaluate forecast accuracy or compare agencies.

Target-date range: 2022-01-01 inclusive to 2026-01-01 exclusive.

## Coverage

Read 50,792 forecast-day rows from 5,658 archived issues; 1,461 of 1,461 target dates are represented.
Removed 9 identical duplicate target/time rows only in memory. No database changes. Lead zero is excluded; no numeric forecast nulls are filled.

## How large are the changes?

Primary scope: successive archived target-date vintages, adjacent in the observed bulletin timeline and at most 24 hours apart. Values below are mean absolute revision / percentage of pairs that changed. RH units are percentage points.

| Variable | Later lead 1 | Later lead 3 | Later lead 7 | Later lead 9 |
| --- | ---: | ---: | ---: | ---: |
| tmin (degC) | 0.113 / 10.9% | 0.050 / 5.0% | 0.074 / 6.9% | 0.005 / 0.5% |
| tmax (degC) | 0.150 / 14.3% | 0.076 / 7.2% | 0.104 / 9.3% | 0.005 / 0.5% |
| rh_min (percentage_points) | 0.647 / 11.5% | 0.397 / 6.8% | 0.563 / 9.2% | 0.074 / 1.1% |
| rh_max (percentage_points) | 0.349 / 6.2% | 0.248 / 4.4% | 0.381 / 6.3% | 0.051 / 1.0% |

## Does the change shrink near the target day?

This is a paired comparison: each included target date supplies an average absolute revision at leads 1–3 and 7–8. Target dates have equal weight. A negative near-minus-far difference means smaller near-day revisions; it does not imply every individual lead follows a monotonic trend. Lead 9 is excluded from this contrast because its predecessor coverage differs structurally and it is unavailable in the daily-latest scope.

| Scope | Variable | Matched dates | Near − far | 95% interval |
| --- | --- | ---: | ---: | --- |
| all_archived_pairs | tmin | 1454 | -0.008 | [-0.014, -0.002] |
| all_archived_pairs | tmax | 1454 | -0.005 | [-0.012, 0.002] |
| all_archived_pairs | rh_min | 1454 | -0.130 | [-0.168, -0.089] |
| all_archived_pairs | rh_max | 1454 | -0.154 | [-0.191, -0.119] |
| consecutive_le24h | tmin | 1454 | -0.007 | [-0.014, -0.001] |
| consecutive_le24h | tmax | 1454 | -0.005 | [-0.012, 0.003] |
| consecutive_le24h | rh_min | 1454 | -0.128 | [-0.167, -0.088] |
| consecutive_le24h | rh_max | 1454 | -0.152 | [-0.189, -0.117] |
| daily_latest | tmin | 1453 | -0.036 | [-0.058, -0.013] |
| daily_latest | tmax | 1453 | -0.036 | [-0.062, -0.010] |
| daily_latest | rh_min | 1453 | -0.574 | [-0.718, -0.418] |
| daily_latest | rh_max | 1453 | -0.619 | [-0.756, -0.483] |

Reading the table: negative intervals entirely below zero support smaller average near-day revisions for that scope and variable under this exploratory bootstrap. An interval spanning zero does not establish a difference. Use the full lead-day plots before describing a smooth or monotonic decline; the result can depend on release cadence.

## Interpretation limits

- Bulletin timings and archive capture vary. `all_archived_pairs` includes long gaps; the primary scope excludes them. `daily_latest` uses the latest archived forecast for each target/issue day, compared only over consecutive issue days.
- These are archived vintages, not proof that every real HKO release was captured. Do not describe revision frequency as changes per day.
- Lead 9 may have only within-day comparisons: a lead-10 forecast is outside the product. Daily-latest comparisons generally stop at later lead 8.
- Early January 2022 trajectories are left-truncated by the source archive; lead coverage and pair denominators are saved.
- Confidence intervals resample target-date clusters, preserving repeated vintages within dates. They do not address serial dependence between adjacent weather days.
- PSR is categorical. Its change frequency is saved separately; no numeric probability or equal-distance category score is invented.
- Zero revisions are retained in mean absolute revision and frequency denominators. Source precision limits measurable changes.
- This is RQ1 only. Revision direction and whether updates improve accuracy belong to RQ2 and RQ3.

## Reproducibility

SQL: `../forecast_query.sql`. Parameters, source fingerprint, coverage checks and software versions: `run_metadata.json`. Exact denominators and intervals: `revision_by_lead.csv`; gap audit: `pair_coverage.csv`; paired approach comparison: `near_far_comparison.csv`. No raw forecast values are exported.
