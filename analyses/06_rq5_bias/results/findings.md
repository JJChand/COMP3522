# RQ5: Systematic bias, season and year

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

tmax: overall mean error -0.216 °C; 7-day-block 95% interval [-0.355, -0.089].

tmin: overall mean error -0.071 °C; 7-day-block 95% interval [-0.171, +0.018].

rh_max: overall mean error +3.074 percentage points; 7-day-block 95% interval [+2.624, +3.540].

rh_min: overall mean error +0.835 percentage points; 7-day-block 95% interval [+0.167, +1.499].

Positive values mean over-forecasting; negative values mean under-forecasting. Seasonal and annual differences are descriptive, not causal changes in forecast quality.

## Concrete results

### Season

| metric | season | n_forecasts | mean_error_c | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- | --- |
| tmax | DJF | 3203 | -0.2625 | -0.4766 | -0.0193 |
| tmax | JJA | 3312 | -0.3172 | -0.5231 | -0.1165 |
| tmax | MAM | 3312 | -0.2125 | -0.5253 | 0.1188 |
| tmax | SON | 3276 | -0.0709 | -0.3299 | 0.1815 |
| tmin | DJF | 3203 | -0.0225 | -0.2038 | 0.1773 |
| tmin | JJA | 3312 | 0.0252 | -0.1361 | 0.1820 |
| tmin | MAM | 3312 | -0.0936 | -0.3281 | 0.1429 |
| tmin | SON | 3276 | -0.1921 | -0.3774 | -0.0076 |

### Year

| metric | year | n_forecasts | mean_error_c | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- | --- |
| tmax | 2022 | 3240 | -0.2717 | -0.5075 | -0.0297 |
| tmax | 2023 | 3285 | -0.2160 | -0.4931 | 0.0496 |
| tmax | 2024 | 3293 | -0.1560 | -0.4074 | 0.1158 |
| tmax | 2025 | 3285 | -0.2203 | -0.4379 | 0.0101 |
| tmin | 2022 | 3240 | -0.0327 | -0.2350 | 0.1808 |
| tmin | 2023 | 3285 | -0.1386 | -0.3084 | 0.0301 |
| tmin | 2024 | 3293 | -0.0578 | -0.2758 | 0.1570 |
| tmin | 2025 | 3285 | -0.0538 | -0.2194 | 0.1286 |

### RH season (percentage points)

| metric | season | n_forecasts | mean_error_pp | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- | --- |
| rh_max | DJF | 3203 | 1.7565 | 0.9433 | 2.6240 |
| rh_max | JJA | 3312 | 3.2588 | 2.6241 | 3.8645 |
| rh_max | MAM | 3312 | 3.2050 | 2.4123 | 4.0674 |
| rh_max | SON | 3276 | 4.0427 | 3.0575 | 5.2278 |
| rh_min | DJF | 3203 | 0.3618 | -0.8561 | 1.6590 |
| rh_min | JJA | 3312 | 1.0921 | 0.0970 | 2.0424 |
| rh_min | MAM | 3312 | 1.4577 | -0.0804 | 3.1052 |
| rh_min | SON | 3276 | 0.4081 | -0.9133 | 1.9091 |

### RH year (percentage points)

| metric | year | n_forecasts | mean_error_pp | calendar7day_block_ci95_low | calendar7day_block_ci95_high |
| --- | --- | --- | --- | --- | --- |
| rh_max | 2022 | 3240 | 3.3784 | 2.5326 | 4.2908 |
| rh_max | 2023 | 3285 | 1.9610 | 1.1807 | 2.7785 |
| rh_max | 2024 | 3293 | 3.2697 | 2.3461 | 4.0930 |
| rh_max | 2025 | 3285 | 3.6904 | 2.6985 | 4.5578 |
| rh_min | 2022 | 3240 | 1.7253 | 0.2954 | 3.1375 |
| rh_min | 2023 | 3285 | 0.3878 | -0.9497 | 1.7792 |
| rh_min | 2024 | 3293 | 0.1409 | -1.1761 | 1.3818 |
| rh_min | 2025 | 3285 | 1.0998 | 0.0297 | 2.0917 |

## Methods and source evidence

Same HKO Headquarters target observations and daily-latest vintage rule as RQ4. Temperature uses complete (`C`) CSV observations; RH uses validated report-date HKOReadingsMinRH/MaxRH. [HKO definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. Seasons use target months: DJF=December–February, MAM=March–May, JJA=June–August, SON=September–November. Year is target calendar year; DJF within a calendar year is not a continuous winter episode. Both target-date cluster and fixed 7-day calendar-block percentile intervals (1,000 draws, seed 3522) are exported. The cross-table controls descriptive comparisons for lead, season and year; all-vintage sensitivity is separate.

## Limitations

Intervals are exploratory and not multiple-testing-adjusted. Fixed 7-day blocks approximate serial dependence; weather episodes can persist longer. Pooled seasonal/year bias can change with lead mix, so consult the cross-table. RH reports explicitly mark data as provisional with limited validation and lack CSV-style completeness flags; validation does not certify finalized values. The RH verification target is HKO Headquarters, not a territory-wide humidity range. Mean RH is never substituted for endpoints.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/06_rq5_bias/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
