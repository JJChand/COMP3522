# RQ7: Conditions associated with temperature errors and revisions

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

tmax absolute error: rain10 high-versus-low difference +0.256 °C after lead/season stratification (5,418 common-support cases).

tmax absolute error: change_high high-versus-low difference +0.281 °C after lead/season stratification (7,639 common-support cases).

tmax absolute error: spread_high high-versus-low difference -0.168 °C after lead/season stratification (7,639 common-support cases).

tmax absolute revision: rain10 high-versus-low difference +0.035 °C after lead/season stratification (4,816 common-support cases).

tmax absolute revision: change_high high-versus-low difference +0.029 °C after lead/season stratification (6,789 common-support cases).

tmax absolute revision: spread_high high-versus-low difference -0.030 °C after lead/season stratification (6,789 common-support cases).

tmin absolute error: rain10 high-versus-low difference +0.084 °C after lead/season stratification (5,418 common-support cases).

tmin absolute error: change_high high-versus-low difference +0.344 °C after lead/season stratification (7,648 common-support cases).

tmin absolute error: spread_high high-versus-low difference +0.024 °C after lead/season stratification (7,648 common-support cases).

tmin absolute revision: rain10 high-versus-low difference +0.003 °C after lead/season stratification (4,816 common-support cases).

tmin absolute revision: change_high high-versus-low difference +0.028 °C after lead/season stratification (6,797 common-support cases).

tmin absolute revision: spread_high high-versus-low difference +0.001 °C after lead/season stratification (6,797 common-support cases).

All four models are explanatory associations. Their 2025 holdout diagnostics and SHAP rankings are exported; chronological holdout does not make realized weather available at issuance or establish causality.

The fixed-panel join retains 850/1,460 tmax error target dates, 851/1,460 tmin error target dates. The error-model holdout R² values are tmax 0.032, tmin 0.008; these low values limit how much variation the fitted models explain.

tmin error model: lead has the largest grouped holdout SHAP magnitude (0.180 °C); this ranks fitted-model attributions, not causal importance.

tmax error model: lead has the largest grouped holdout SHAP magnitude (0.232 °C); this ranks fitted-model attributions, not causal importance.

## Concrete results

| metric | outcome_kind | factor | mean_difference_c | ci95_low | ci95_high |
| --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | rain10 | 0.2562 | 0.0163 | 0.5048 |
| tmax | absolute_error | change_high | 0.2814 | 0.1616 | 0.4078 |
| tmax | absolute_error | spread_high | -0.1684 | -0.3148 | -0.0132 |
| tmax | absolute_revision | rain10 | 0.0354 | -0.0061 | 0.0891 |
| tmax | absolute_revision | change_high | 0.0291 | -0.0028 | 0.0603 |
| tmax | absolute_revision | spread_high | -0.0302 | -0.0590 | 0.0007 |
| tmin | absolute_error | rain10 | 0.0842 | -0.1477 | 0.2798 |
| tmin | absolute_error | change_high | 0.3444 | 0.2137 | 0.4650 |
| tmin | absolute_error | spread_high | 0.0241 | -0.0636 | 0.1241 |
| tmin | absolute_revision | rain10 | 0.0025 | -0.0427 | 0.0451 |
| tmin | absolute_revision | change_high | 0.0277 | -0.0080 | 0.0630 |
| tmin | absolute_revision | spread_high | 0.0012 | -0.0251 | 0.0306 |

### Season and bulletin-narrative comparisons

| metric | outcome_kind | factor | comparison | reference | n_cases | mean_difference_c | ci95_low | ci95_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | regime | cyclone_mention | other | 1230 | 0.2544 | -0.0318 | 0.5371 |
| tmax | absolute_error | regime | trough_mention | other | 2101 | -0.0810 | -0.2401 | 0.0676 |
| tmax | absolute_error | regime | monsoon_mention | other | 1121 | 0.3901 | 0.0474 | 0.7238 |
| tmax | absolute_error | season | MAM | DJF | 4426 | 0.3582 | 0.1354 | 0.5554 |
| tmax | absolute_error | season | JJA | DJF | 3661 | -0.1838 | -0.3805 | 0.0177 |
| tmax | absolute_error | season | SON | DJF | 3994 | 0.0179 | -0.1874 | 0.2129 |
| tmax | absolute_revision | regime | cyclone_mention | other | 1134 | 0.0609 | -0.0248 | 0.1346 |
| tmax | absolute_revision | regime | trough_mention | other | 1873 | -0.0115 | -0.0787 | 0.0579 |
| tmax | absolute_revision | regime | monsoon_mention | other | 986 | 0.0043 | -0.1139 | 0.1243 |
| tmax | absolute_revision | season | MAM | DJF | 3933 | 0.0743 | 0.0281 | 0.1215 |
| tmax | absolute_revision | season | JJA | DJF | 3253 | -0.0847 | -0.1289 | -0.0382 |
| tmax | absolute_revision | season | SON | DJF | 3549 | 0.0299 | -0.0149 | 0.0798 |
| tmin | absolute_error | regime | cyclone_mention | other | 1230 | 0.1541 | -0.0153 | 0.3496 |
| tmin | absolute_error | regime | trough_mention | other | 2101 | 0.0554 | -0.1307 | 0.2235 |
| tmin | absolute_error | regime | monsoon_mention | other | 1121 | 0.2237 | -0.0720 | 0.5492 |
| tmin | absolute_error | season | MAM | DJF | 4435 | 0.0892 | -0.0822 | 0.2725 |
| tmin | absolute_error | season | JJA | DJF | 3670 | -0.2213 | -0.3755 | -0.0786 |
| tmin | absolute_error | season | SON | DJF | 4003 | -0.0350 | -0.1975 | 0.1281 |
| tmin | absolute_revision | regime | cyclone_mention | other | 1134 | 0.0010 | -0.0527 | 0.0669 |
| tmin | absolute_revision | regime | trough_mention | other | 1873 | 0.0172 | -0.0341 | 0.0737 |
| tmin | absolute_revision | regime | monsoon_mention | other | 986 | 0.0346 | -0.0618 | 0.1360 |
| tmin | absolute_revision | season | MAM | DJF | 3941 | -0.0303 | -0.0756 | 0.0171 |
| tmin | absolute_revision | season | JJA | DJF | 3261 | -0.1583 | -0.2006 | -0.1190 |
| tmin | absolute_revision | season | SON | DJF | 3557 | -0.0164 | -0.0661 | 0.0313 |

### Fixed-panel join coverage

| metric | outcome_kind | eligible_cases | matched_cases | excluded_cases | matched_dates |
| --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | 13103 | 7639 | 5464 | 850 |
| tmax | absolute_revision | 11643 | 6789 | 4854 | 849 |
| tmin | absolute_error | 13103 | 7648 | 5455 | 851 |
| tmin | absolute_revision | 11643 | 6797 | 4846 | 850 |

### Chronological model check

| metric | outcome_kind | n_cases | mae_c | rmse_c | r_squared | n_negative_predictions |
| --- | --- | --- | --- | --- | --- | --- |
| tmax | absolute_error | 1854 | 0.8471 | 1.0910 | 0.0317 | 0 |
| tmax | absolute_revision | 1648 | 0.4740 | 0.5246 | 0.0075 | 0 |
| tmin | absolute_error | 1854 | 0.6635 | 0.8338 | 0.0085 | 0 |
| tmin | absolute_revision | 1648 | 0.4245 | 0.4781 | -0.0225 | 0 |

## Methods and source evidence

Daily-latest forecasts and consecutive-issue-day revisions, both endpoints leads 1–9. Outcome units are °C. HKO-point rainfall ≥10 mm; absolute HKO day-to-day extrema change; range across a fixed eight-station panel requiring all eight complete numeric readings; target-date season. Narrative proxy hierarchy: cyclone/typhoon/storm/depression mention, then trough, then monsoon, then other, using the later/selected issue’s general-situation text. This is a bulletin-level mention, not target-day event membership. Binary contrasts require ≥10 unique dates in each group per lead×season stratum (season contrasts adjust lead only). Weights are fixed common-support case counts. 95% intervals use 1,000 resamples of fixed 7-day calendar blocks; invalid draws are excluded and an interval needs ≥900 valid draws. Additive OLS fits 2022–2024, tests 2025, with lead/season/regime dummies, rain, continuous change/spread and a linear year term; revision models add elapsed hours. Zero-variance/collinear terms are explicitly omitted. Coefficient intervals use 7-day cluster sandwich covariance and asymptotic normal approximation. Exact interventional linear SHAP is beta×(feature−training mean); dummy attributions are summed within factor before mean absolute magnitude. [Official linear SHAP definition](https://shap.readthedocs.io/en/latest/generated/shap.LinearExplainer.html). Additivity is asserted for every holdout row. Station mappings, missing joins, correlations, thresholds and all coefficients are exported.

## Limitations

Realized rainfall, temperature changes and spatial spread are post-event context. Selection requires a complete fixed panel, so missingness may bias coverage; excluded dates/cases are reported, not imputed. Panel range includes elevation/location differences and is not forecast uncertainty. Narrative labels can mention remote or future systems. Exploratory contrasts and coefficient tests have no multiple-testing correction. Seven-day blocks do not guarantee removal of longer serial dependence. Correlated factors can redistribute interventional SHAP credit. OLS may produce negative magnitudes, reported without clipping; poor holdout fit limits explanations. This factor-model analysis covers temperature outcomes. RH endpoint verification is reported separately in RQ3–RQ5; the fixed station-panel range here is temperature spread, not humidity spread.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/08_rq7_error_factors/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
