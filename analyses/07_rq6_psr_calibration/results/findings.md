# RQ6: PSR calibration and event verification

Target dates: 2022-01-01–2025-12-31. Task 1 only.

## Findings

The area-weighted proxy has 1,255 usable target days. Observed frequencies fall outside the published bands for: Medium, Medium Low. Midpoint-coded Brier score is 0.0923; the compatible per-case probability-band bounds are [0.0551, 0.1651], which are not confidence intervals. These results concern the defined rainfall proxy, so they do not alone establish calibration or miscalibration of the exact HKO event.

## Concrete results

| category | n_forecasts | event_rate | forecast_band_low | forecast_band_high | ci95_low | ci95_high |
| --- | --- | --- | --- | --- | --- | --- |
| High | 474 | 0.7342 | 0.7000 | 1.0000 | 0.6457 | 0.8188 |
| Low | 7837 | 0.0250 | 0.0000 | 0.3000 | 0.0180 | 0.0341 |
| Medium | 900 | 0.3844 | 0.4500 | 0.5500 | 0.3226 | 0.4468 |
| Medium High | 449 | 0.5546 | 0.5500 | 0.7000 | 0.4701 | 0.6366 |
| Medium Low | 1589 | 0.1611 | 0.3000 | 0.4500 | 0.1253 | 0.1926 |

### Categorical alarm verification (area proxy)

| alarm_rule | tp | fp | fn | tn | hit_rate | false_alarm_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| Medium_or_higher | 943 | 880 | 452 | 8974 | 0.6760 | 0.4827 |
| Medium High_or_higher | 597 | 326 | 798 | 9528 | 0.4280 | 0.3532 |
| High_or_higher | 348 | 126 | 1047 | 9728 | 0.2495 | 0.2658 |

## Methods and source evidence

HKO defines significant rain using daily rainfall reaching 10 mm broadly across Hong Kong and publishes five probability bands. [HKO product definitions](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm?tablenote=true). Primary proxy: weighted daily station mean ≥10 mm, using the existing 22-station land-clipped Voronoi weights. Their IDs/names/codes and weight sum are verified against the live catalog; the weight file checksum is saved. Only days with all 22 complete numeric/Trace records qualify. Trace is [0,0.05) mm; ambiguous threshold outcomes are excluded, not filled with invented measurements. Station-mean and HKO-point sensitivities are separate. Brier score = mean((p−event)²); category midpoints are an explicit coding assumption. Lower/upper endpoint codings and infimum/supremum bounds over unpublished per-case probabilities are exported. Alarms are categorical thresholds, not claims that every Medium forecast has p≥0.5. Hit rate=TP/(TP+FN); false alarm ratio=FP/(TP+FP), distinct from false-positive rate=FP/(FP+TN).

## Limitations

A station-area weighted average is an approximation to the territorial rainfall event, not its official verification label. Station availability and exclusion can select different weather conditions. The saved weights use a prior land geometry and rounded weights are normalized after a tight sum check, not recomputed from fresh geometry. Reliability depends on lead and target definition. Brier bounds are partial identification of the missing numeric probabilities, not recommended outcome-aware forecasts. A headline midpoint score must retain its coding assumption. Date clusters do not address inter-date serial dependence. The separate retained-report [rainfall source audit](rainfall_report_audit.json) does not resolve territorial labels: daily JSON rainfall matches the HKO-point CSV on all 1,223 numeric comparisons. Accumulated rainfall is year-to-date, and the average field has a cumulative-like annual trajectory, not daily rainfall. Neither is a valid daily territorial substitute.

## Reproduce

From the repository root: `.\.venv\Scripts\python.exe analyses/07_rq6_psr_calibration/run_analysis.py`.

Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; source fingerprints, parameters and versions are in `run_metadata.json`. Only reviewed aggregates and figures are exported, not raw forecast/observation values.
