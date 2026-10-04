# RQ4: Accuracy across lead days and reference forecasts

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

tmin: daily-latest MAE rises from 0.689 °C at lead 1 to 1.344 °C at lead 9.

tmax: daily-latest MAE rises from 0.950 °C at lead 1 to 1.794 °C at lead 9.

rh_min: daily-latest MAE rises from 5.351 percentage points at lead 1 to 8.868 at lead 9.

rh_max: daily-latest MAE rises from 4.587 percentage points at lead 1 to 6.211 at lead 9.

RH extrema are scored against validated daily JSON reports. The separate mean-RH diagnostic measures whether the observed daily mean falls outside the forecast minimum/maximum range; an inside-range mean does not establish correct extrema.

## Concrete results

| metric | lead_days | n | mae | rmse | mae_ci95_low | mae_ci95_high |
| --- | --- | --- | --- | --- | --- | --- |
| tmax | 1 | 1460 | 0.9503 | 1.2008 | 0.9143 | 0.9874 |
| tmax | 3 | 1458 | 1.2058 | 1.5472 | 1.1573 | 1.2577 |
| tmax | 6 | 1455 | 1.4482 | 1.8584 | 1.3913 | 1.5115 |
| tmax | 9 | 1451 | 1.7936 | 2.2810 | 1.7236 | 1.8685 |
| tmin | 1 | 1460 | 0.6887 | 0.8843 | 0.6610 | 0.7158 |
| tmin | 3 | 1458 | 0.8652 | 1.1157 | 0.8293 | 0.9019 |
| tmin | 6 | 1455 | 1.0545 | 1.3509 | 1.0107 | 1.0988 |
| tmin | 9 | 1451 | 1.3436 | 1.7641 | 1.2824 | 1.4057 |

### RH endpoint accuracy (percentage points)

| metric | lead_days | n | mae | rmse | mae_ci95_low | mae_ci95_high |
| --- | --- | --- | --- | --- | --- | --- |
| rh_max | 1 | 1460 | 4.5870 | 6.1434 | 4.3698 | 4.7988 |
| rh_max | 3 | 1458 | 5.0165 | 6.7936 | 4.7798 | 5.2565 |
| rh_max | 6 | 1455 | 5.5388 | 7.6174 | 5.2789 | 5.7994 |
| rh_max | 9 | 1451 | 6.2109 | 8.6641 | 5.9014 | 6.5279 |
| rh_min | 1 | 1460 | 5.3514 | 6.8741 | 5.1472 | 5.5665 |
| rh_min | 3 | 1458 | 6.3704 | 8.1806 | 6.1166 | 6.6228 |
| rh_min | 6 | 1455 | 7.4914 | 9.6959 | 7.2137 | 7.8151 |
| rh_min | 9 | 1451 | 8.8684 | 11.3880 | 8.5147 | 9.2102 |

### RH matched baseline skill

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

### RH mean consistency, not endpoint accuracy

| lead_days | n_cases | outside_rate_pct | mean_outside_distance_pp |
| --- | --- | --- | --- |
| 1 | 1460 | 2.1233 | 0.0740 |
| 2 | 1459 | 3.9753 | 0.1570 |
| 3 | 1458 | 5.6241 | 0.2064 |
| 4 | 1457 | 7.1380 | 0.2780 |
| 5 | 1456 | 8.1044 | 0.3565 |
| 6 | 1455 | 9.9656 | 0.5100 |
| 7 | 1454 | 12.4484 | 0.7648 |
| 8 | 1453 | 14.3840 | 0.9443 |
| 9 | 1451 | 16.4714 | 1.0689 |

### Matched baseline skill (positive means lower error than reference)

| metric | lead_days | baseline | n_matched | forecast_mae | baseline_mae | mae_skill | mse_skill |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tmax | 1 | climatology_mean | 1460 | 0.9503 | 2.3181 | 0.5901 | 0.8219 |
| tmax | 1 | persistence_lag2 | 1460 | 0.9503 | 2.4604 | 0.6138 | 0.8620 |
| tmax | 9 | climatology_mean | 1451 | 1.7936 | 2.3195 | 0.2267 | 0.3585 |
| tmax | 9 | persistence_lag2 | 1451 | 1.7936 | 2.9165 | 0.3850 | 0.6445 |
| tmin | 1 | climatology_mean | 1460 | 0.6887 | 1.8711 | 0.6319 | 0.8598 |
| tmin | 1 | persistence_lag2 | 1460 | 0.6887 | 1.9611 | 0.6488 | 0.8908 |
| tmin | 9 | climatology_mean | 1451 | 1.3436 | 1.8715 | 0.2821 | 0.4430 |
| tmin | 9 | persistence_lag2 | 1451 | 1.3436 | 2.4329 | 0.4478 | 0.7141 |

## Methods and source evidence

Temperature uses complete (`C`) HKO Headquarters daily CSV observations; RH uses validated HKOReadingsMinRH/MaxRH JSON report values, joined on report_date. [HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. Positive leads 1–9. Main selection is latest archived per target/issue date; all-vintage scoring is a sensitivity. Frozen climatology pools 1991–2020 observations within ±2 calendar days using leap-reference month/day alignment; mean and median references are both exported. Training ends before the study. Persistence uses issue-day-minus-2 (primary retrospective proxy) and minus-1 (sensitivity). Skill is 1−MAE_forecast/MAE_reference and 1−MSE_forecast/MSE_reference, calculated on identical eligible cases, not unmatched averages. RH has no 1991–2020 extrema history in the local dataset. Its separate frozen 2022 ±15-calendar-day mean/median seasonal reference is scored only on 2023–2025, never on its training year. It is a one-year reference, not a 30-year climatological normal and is not directly comparable to the temperature baseline. Climatology calendar aggregates and all baseline scores are saved.

## Limitations

Historical observation publication times are absent, so persistence skill is not proven operationally available even with a two-day lag. Lead 9 may use an earlier issue-day bulletin than other targets because the product window changes within a day. Mean RH is not minimum/maximum RH. A positive outside-distance is a lower bound on at least one extrema error, but zero is not an accuracy score. RH reports explicitly mark displayed data as provisional with limited validation and have no CSV completeness flag. Range/date validation does not certify finalized values. The RH verification target is HKO Headquarters, not a territory-wide humidity range. Sampling intervals do not correct inter-date serial dependence.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/05_rq4_accuracy_by_lead/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
