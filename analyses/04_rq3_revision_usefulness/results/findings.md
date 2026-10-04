# RQ3: Are forecast revisions useful?

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

rh_max: 57.1% of 2,555 changed forecasts moved closer to the realized observation; 42.5% worsened and 0.4% tied. Mean absolute-error reduction 0.931 percentage points.

rh_min: 60.7% of 3,859 changed forecasts moved closer to the realized observation; 38.9% worsened and 0.4% tied. Mean absolute-error reduction 1.337 percentage points.

tmax: 62.5% of 4,080 changed forecasts moved closer to the realized observation; 35.3% worsened and 2.2% tied. Mean absolute-error reduction 0.298 °C.

tmin: 63.7% of 3,039 changed forecasts moved closer to the realized observation; 33.3% worsened and 3.0% tied. Mean absolute-error reduction 0.313 °C.

## Concrete results

| scope | metric | denominator | n_pairs | usefulness_rate_pct | ci95_low_pct | ci95_high_pct | mean_absolute_error_reduction | error_reduction_unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| consecutive_le24h | rh_max | changed_only | 2555 | 57.1429 | 55.7945 | 58.5806 | 0.9307 | percentage_points |
| consecutive_le24h | rh_max | all_pairs | 46607 | 3.1326 | 2.9805 | 3.2820 | 0.0510 | percentage_points |
| consecutive_le24h | rh_min | changed_only | 3859 | 60.7411 | 59.5508 | 61.9063 | 1.3371 | percentage_points |
| consecutive_le24h | rh_min | all_pairs | 46607 | 5.0293 | 4.8487 | 5.2057 | 0.1107 | percentage_points |
| consecutive_le24h | tmax | changed_only | 4080 | 62.5490 | 61.3306 | 63.8549 | 0.2982 | degC |
| consecutive_le24h | tmax | all_pairs | 46607 | 5.4756 | 5.3037 | 5.6616 | 0.0261 | degC |
| consecutive_le24h | tmin | changed_only | 3039 | 63.7381 | 62.2953 | 65.1637 | 0.3130 | degC |
| consecutive_le24h | tmin | all_pairs | 46607 | 4.1560 | 3.9836 | 4.3290 | 0.0204 | degC |
| daily_latest | rh_max | changed_only | 2459 | 57.1370 | 55.6991 | 58.6012 | 0.9549 | percentage_points |
| daily_latest | rh_max | all_pairs | 11643 | 12.0673 | 11.4707 | 12.6647 | 0.2017 | percentage_points |
| daily_latest | rh_min | changed_only | 3673 | 60.7678 | 59.6042 | 61.8935 | 1.3959 | percentage_points |
| daily_latest | rh_min | all_pairs | 11643 | 19.1703 | 18.5043 | 19.8200 | 0.4404 | percentage_points |
| daily_latest | tmax | changed_only | 3901 | 62.6250 | 61.4293 | 63.9512 | 0.3131 | degC |
| daily_latest | tmax | all_pairs | 11643 | 20.9826 | 20.3388 | 21.7276 | 0.1049 | degC |
| daily_latest | tmin | changed_only | 2956 | 63.9716 | 62.3977 | 65.4124 | 0.3218 | degC |
| daily_latest | tmin | all_pairs | 11643 | 16.2415 | 15.5891 | 16.9319 | 0.0817 | degC |

## Methods and source evidence

Each pair uses the same valid date, variable and HKO Headquarters observation. Temperature uses complete (`C`) numeric CSV values; RH uses validated daily-report HKOReadingsMinRH/MaxRH, not daily mean RH. Dates join to report_date, not bulletin_date. [HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. Primary pairs are adjacent archived vintages with gap≤24h and both leads 1–9. Benefit is earlier absolute error minus later absolute error; tolerance 1e−10 is used only for floating-point ties. Changed-only and all-pair rates are separately reported. Confidence intervals cluster by target date; lead breakdown and join exclusions are saved.

## Limitations

Retrospective usefulness is not something the forecaster knew at issuance. Equal absolute errors can occur even when the forecast changes across the observed value. RH daily reports explicitly mark data as provisional with limited validation and have no CSV completeness flag. Numeric/date/range checks do not certify finalized climatological values; the RH verification target is HKO Headquarters, not a territory-wide humidity range. Lead 9 temperature has only seven changed pairs per variable in the primary scope and compares same-day boundary updates; consult by-lead RH counts separately. Serial dependence and archive capture are not corrected.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/04_rq3_revision_usefulness/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
