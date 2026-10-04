# Part 1: executed findings and remaining evidence gaps

Target dates: 2022-01-01–2025-12-31. Local database, read-only. Task 2 remains on hold.

All RQ folders contain executed concrete results and a findings report. This is **not a claim that every originally named verification component is complete**: PSR verification uses spatial proxies, and their equivalence to the official territorial event is not established. RH daily-report endpoints are now validated and scored; they are explicitly provisional and have no CSV completeness flag.

## Coverage and report index

| RQ | Status | Findings report |
| --- | --- | --- |
| RQ1 | Previously executed and independently verified | [Revision size/frequency](02_rq1_revisions/results/findings.md) |
| RQ2 | Executed: temperature/RH revisions and PSR categories | [RQ2 report](03_rq2_revision_direction/results/findings.md) |
| RQ3 | Executed: temperature and validated daily-report RH revision usefulness | [RQ3 report](04_rq3_revision_usefulness/results/findings.md) |
| RQ4 | Executed: temperature/RH accuracy and matched reference skill | [RQ4 report](05_rq4_accuracy_by_lead/results/findings.md) |
| RQ5 | Executed: temperature/RH bias by lead, season and year | [RQ5 report](06_rq5_bias/results/findings.md) |
| RQ6 | All named metrics executed against disclosed rainfall proxies, not exact HKO territorial labels | [RQ6 report](07_rq6_psr_calibration/results/findings.md) |
| RQ7 | All named factor directions executed for temperature errors and revisions; post-event context | [RQ7 report](08_rq7_error_factors/results/findings.md) |

## RQ2: back-and-forth revisions

| metric | unit | mean_target_ffi | n_adjacent_nonzero_sign_pairs | adjacent_reversal_rate_pct | compressed_reversal_rate_pct |
| --- | --- | --- | --- | --- | --- |
| tmin | degC | 0.0198 | 61 | 26.2295 | 47.8385 |
| tmax | degC | 0.0310 | 133 | 30.8271 | 47.6208 |
| rh_min | percentage_points | 0.1811 | 125 | 44.0000 | 55.0643 |
| rh_max | percentage_points | 0.1190 | 54 | 57.4074 | 64.9792 |

FFI is in the original measurement unit, not a reversal percentage. Adjacent reversals require two immediately adjacent nonzero changes; compressed reversals skip zeros, not archive gaps. PSR transition counts are categorical.

| scope | n_pairs | n_changed | change_rate_pct |
| --- | --- | --- | --- |
| consecutive_le24h | 46607 | 1846 | 3.9608 |
| daily_latest | 11643 | 1760 | 15.1164 |

## RQ3: are changes useful?

| metric | n_pairs | usefulness_rate_pct | ci95_low_pct | ci95_high_pct | mean_absolute_error_reduction | error_reduction_unit |
| --- | --- | --- | --- | --- | --- | --- |
| rh_max | 2555 | 57.1429 | 55.7945 | 58.5806 | 0.9307 | percentage_points |
| rh_min | 3859 | 60.7411 | 59.5508 | 61.9063 | 1.3371 | percentage_points |
| tmax | 4080 | 62.5490 | 61.3306 | 63.8549 | 0.2982 | degC |
| tmin | 3039 | 63.7381 | 62.2953 | 65.1637 | 0.3130 | degC |

Changed-only rates must not be confused with all-pair rates. Temperature errors use °C; RH uses percentage points. Primary lead-9 temperature comparisons have seven changed pairs per variable and concern same-day boundary updates; RH counts are separate.

## RQ4: lead-time accuracy and skill

| metric | lead_days | n | mae | rmse |
| --- | --- | --- | --- | --- |
| tmax | 1 | 1460 | 0.9503 | 1.2008 |
| tmax | 9 | 1451 | 1.7936 | 2.2810 |
| tmin | 1 | 1460 | 0.6887 | 0.8843 |
| tmin | 9 | 1451 | 1.3436 | 1.7641 |

Units: °C; HKO Headquarters point station, not a territory-wide mean.

### RH endpoint accuracy

| metric | lead_days | n | mae | rmse |
| --- | --- | --- | --- | --- |
| rh_max | 1 | 1460 | 4.5870 | 6.1434 |
| rh_max | 9 | 1451 | 6.2109 | 8.6641 |
| rh_min | 1 | 1460 | 5.3514 | 6.8741 |
| rh_min | 9 | 1451 | 8.8684 | 11.3880 |

Units: percentage points. HKOReadingsMinRH/MaxRH daily JSON reports, joined on report_date, not bulletin publication date. All 1,461 dates pass numeric/date/range checks; the reports explicitly mark data as provisional with limited validation and lack a CSV-style completeness flag. [HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37.

### Matched reference skill

| metric | lead_days | baseline | n_matched | mae_skill | mse_skill |
| --- | --- | --- | --- | --- | --- |
| tmax | 1 | climatology_mean | 1460 | 0.5901 | 0.8219 |
| tmax | 1 | persistence_lag2 | 1460 | 0.6138 | 0.8620 |
| tmax | 9 | climatology_mean | 1451 | 0.2267 | 0.3585 |
| tmax | 9 | persistence_lag2 | 1451 | 0.3850 | 0.6445 |
| tmin | 1 | climatology_mean | 1460 | 0.6319 | 0.8598 |
| tmin | 1 | persistence_lag2 | 1460 | 0.6488 | 0.8908 |
| tmin | 9 | climatology_mean | 1451 | 0.2821 | 0.4430 |
| tmin | 9 | persistence_lag2 | 1451 | 0.4478 | 0.7141 |

Positive skill means lower error on the same matched cases. Climatology is frozen at 1991–2020; persistence is a retrospective past-day comparator because publication times are unverified. RH mean-range consistency is not RH-extrema MAE/RMSE.

| metric | lead_days | baseline | verification_period | n_matched | mae_skill | mse_skill |
| --- | --- | --- | --- | --- | --- | --- |
| rh_max | 1 | climatology_mean_2022 | 2023–2025 | 1096 | 0.3042 | 0.5624 |
| rh_max | 1 | persistence_lag2 | 2022–2025, available lagged dates only | 1458 | 0.4018 | 0.6714 |
| rh_max | 9 | climatology_mean_2022 | 2023–2025 | 1095 | 0.0850 | 0.1775 |
| rh_max | 9 | persistence_lag2 | 2022–2025, available lagged dates only | 1449 | 0.2825 | 0.4584 |
| rh_min | 1 | climatology_mean_2022 | 2023–2025 | 1096 | 0.4951 | 0.7646 |
| rh_min | 1 | persistence_lag2 | 2022–2025, available lagged dates only | 1458 | 0.5351 | 0.7913 |
| rh_min | 9 | climatology_mean_2022 | 2023–2025 | 1095 | 0.1804 | 0.3822 |
| rh_min | 9 | persistence_lag2 | 2022–2025, available lagged dates only | 1449 | 0.3618 | 0.5811 |

RH reference: freeze 2022 ±15-calendar-day means; verify only 2023–2025, never the training year. This one-year seasonal reference is not the temperature 1991–2020 normal. RH persistence is also a retrospective comparator.

## RQ5: signed bias

| metric | n_forecasts | mean_error_c | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- |
| tmax | 13103 | -0.2158 | -0.3547 | -0.0889 |
| tmin | 13103 | -0.0708 | -0.1705 | 0.0177 |

Units: °C; positive means over-forecasting. Seasonal/year tables and lead×season×year cross-tables are in the RQ5 report/folder; pooled differences are not causal improvements.

| metric | n_forecasts | mean_error_pp | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- |
| rh_max | 13103 | 3.0740 | 2.6238 | 3.5399 |
| rh_min | 13103 | 0.8350 | 0.1666 | 1.4991 |

RH units: percentage points; positive means over-forecasting. RH season/year/lead tables are saved separately.

## RQ6: PSR and rainfall proxies

| proxy | n_forecasts | event_rate | midpoint_bs | bs_lower_bound | bs_upper_bound |
| --- | --- | --- | --- | --- | --- |
| area_weighted_22 | 11249 | 0.1240 | 0.0923 | 0.0551 | 0.1651 |
| hko_point | 13103 | 0.1298 | 0.1045 | 0.0644 | 0.1795 |
| station_mean_22 | 11249 | 0.1232 | 0.0929 | 0.0556 | 0.1658 |

Midpoint Brier scores assume category midpoints; score bounds are not confidence intervals. The weighted 22-station daily-mean rainfall ≥10 mm event is not the exact territorial HKO verification label.

| alarm_rule | tp | fp | fn | tn | hit_rate | false_alarm_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| Medium_or_higher | 943 | 880 | 452 | 8974 | 0.6760 | 0.4827 |
| Medium High_or_higher | 597 | 326 | 798 | 9528 | 0.4280 | 0.3532 |
| High_or_higher | 348 | 126 | 1047 | 9728 | 0.2495 | 0.2658 |

Reliability diagrams, published bands, lead-group breakdowns and target coverage are in RQ6. The retained-report rainfall audit finds only point daily rainfall and cumulative-like fields, not a confirmed daily territorial label; see [the source audit](07_rq6_psr_calibration/results/rainfall_report_audit.json).

## RQ7: associated conditions

| metric | factor | n_cases | mean_difference_c | ci95_low | ci95_high |
| --- | --- | --- | --- | --- | --- |
| tmax | rain10 | 5418 | 0.2562 | 0.0163 | 0.5048 |
| tmax | change_high | 7639 | 0.2814 | 0.1616 | 0.4078 |
| tmax | spread_high | 7639 | -0.1684 | -0.3148 | -0.0132 |
| tmin | rain10 | 5418 | 0.0842 | -0.1477 | 0.2798 |
| tmin | change_high | 7648 | 0.3444 | 0.2137 | 0.4650 |
| tmin | spread_high | 7648 | 0.0241 | -0.0636 | 0.1241 |

High-versus-low differences after lead/season stratification; change-high means ≥2 °C day-to-day change and spread-high uses a fixed 2022 panel median. These estimates use common-support cases and 7-day block bootstrap intervals, not causal tests. Season and weather-narrative comparisons, revision outcomes, coefficients, correlations and holdout SHAP are included in the RQ7 report.

| metric | outcome_kind | eligible_cases | matched_cases | excluded_cases | matched_dates |
| --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | 13103 | 7639 | 5464 | 850 |
| tmax | absolute_revision | 11643 | 6789 | 4854 | 849 |
| tmin | absolute_error | 13103 | 7648 | 5455 | 851 |
| tmin | absolute_revision | 11643 | 6797 | 4846 | 850 |

| metric | outcome_kind | n_cases | r_squared | mae_c | train_mean_baseline_mae_c |
| --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | 1854 | 0.0317 | 0.8471 | 0.8730 |
| tmax | absolute_revision | 1648 | 0.0075 | 0.4740 | 0.4846 |
| tmin | absolute_error | 1854 | 0.0085 | 0.6635 | 0.6595 |
| tmin | absolute_revision | 1648 | -0.0225 | 0.4245 | 0.4045 |

The fixed-panel join excludes many days. Low/negative holdout R² limits explanations; linear SHAP ranks this model’s attributions, not established causal importance. Chronological holdout does not turn realized target-day weather into information available at issuance.

## Evidence and reproducibility

Each folder’s README gives the run command. `run_metadata.json` records input fingerprints and software versions; `verification.json` records the independent checks and their actual scope. Source SQL and shared method tests are in `common/`. Raw records and credentials are not exported.

| RQ | Independent aggregate groups checked |
| --- | ---: |
| RQ2 | 116 |
| RQ3 | 16 |
| RQ4 | 912 |
| RQ5 | 36 |
| RQ6 | 111 |
| RQ7 | 8 |

Independent live SQL covers RQ2 directions/PSR counts, RQ3 temperature/RH usefulness, RQ4 temperature/RH accuracy and matched temperature baselines, and RQ5 temperature/RH bias. Separately written Python checks daily-latest RH reference scores and all 732 frozen RH calendar bins (included in the RQ4 count). RQ6 checks cover all three proxies and all/1–3/4–6/7–9 lead groups: reliability counts/rates/bands, all Brier codings and bounds, confusion cells, hit rate, false alarm ratio, false-positive rate, coverage and unique exported grain. RQ7 checks cover joins/outcome means. These checks do not independently prove bootstrap intervals, FFI summaries, coefficient uncertainty or SHAP rankings; synthetic tests check representative method edge cases. Figures were visually inspected, including the corrected RQ3 legend/sample labels and aligned RQ4/RQ5 scales.

## What is needed to close the remaining scope?

The previously reported RH-extrema gap was a catalog-only inference: the daily JSON reports already contained matching endpoints. The read-only source audit now validates all 1,461 dates and the analysis scores them. No database import was needed. Daily mean RH was never substituted for the endpoints. The guide documents the corrected mapping and its missing-completeness-flag caveat.

Exact territorial PSR calibration needs the official realized event label or an agreed research definition accepting the documented spatial proxy. Operational persistence requires historical publication-availability evidence. These gaps are distinct from successful script execution.
