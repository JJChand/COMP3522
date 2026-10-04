# RQ2: Revision direction and flip-flops

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

tmin: mean date-weighted FFI 0.0198 degC; adjacent nonzero reversal rate 26.2% (61 comparable sign pairs).

tmax: mean date-weighted FFI 0.0310 degC; adjacent nonzero reversal rate 30.8% (133 comparable sign pairs).

rh_min: mean date-weighted FFI 0.1811 percentage_points; adjacent nonzero reversal rate 44.0% (125 comparable sign pairs).

rh_max: mean date-weighted FFI 0.1190 percentage_points; adjacent nonzero reversal rate 57.4% (54 comparable sign pairs).

A nonzero FFI documents back-and-forth movement, not whether an update is useful.

## Concrete results

| scope | metric | n_target_dates | mean_target_ffi | adjacent_reversal_rate_pct | compressed_reversal_rate_pct |
| --- | --- | --- | --- | --- | --- |
| consecutive_le24h | tmin | 1460 | 0.0198 | 26.2295 | 47.8385 |
| consecutive_le24h | tmax | 1460 | 0.0310 | 30.8271 | 47.6208 |
| consecutive_le24h | rh_min | 1460 | 0.1811 | 44.0000 | 55.0643 |
| consecutive_le24h | rh_max | 1460 | 0.1190 | 57.4074 | 64.9792 |
| daily_latest | tmin | 1458 | 0.0855 | 44.9074 | 48.6310 |
| daily_latest | tmax | 1458 | 0.1318 | 47.3636 | 48.2579 |
| daily_latest | rh_min | 1458 | 0.7641 | 56.5752 | 55.7626 |
| daily_latest | rh_max | 1458 | 0.5014 | 64.1608 | 65.7817 |

### PSR category changes

| scope | n_pairs | n_changed | change_rate_pct |
| --- | --- | --- | --- |
| consecutive_le24h | 46607 | 1846 | 3.9608 |
| daily_latest | 11643 | 1760 | 15.1164 |

## Methods and source evidence

FFI = (sum of successive absolute changes − forecast range)/(N−2), for N≥3, in the variable’s original unit. [Official scores documentation](https://scores.readthedocs.io/en/latest/api.html#scores.continuous.flip_flop_index). Continuous trajectories are broken at missing values or disallowed gaps. FFI is averaged within target date then across dates. The adjacent rate requires both immediately neighboring revision signs to be nonzero; the compressed rate skips zero changes but never missing values/gaps. PSR uses ordinal direction only, never an equal-distance numeric FFI. Lead and full category transition counts are in the CSVs; 95% FFI intervals resample target dates.

## Limitations

Archived bulletins may omit actual releases. Daily-latest selection is a cadence sensitivity, not the same population. Short trajectories cannot have an FFI; zero-change sequences have zero FFI, not missing FFI. Intervals do not adjust for inter-date serial dependence. PSR categories are probability bands, not probabilities.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/03_rq2_revision_direction/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
