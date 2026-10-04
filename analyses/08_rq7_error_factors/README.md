# RQ7: Conditions associated with errors and revisions

Executed for temperature error and revision outcomes, including all named factor directions.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

Rainfall, ≥2 °C day-to-day changes, fixed-eight-station spread, season and bulletin-narrative proxies. Common-support stratified contrasts with 7-day block bootstrap intervals. Additive OLS trains 2022–2024 and tests 2025; cluster coefficient intervals and exact interventional linear SHAP are exported. Realized factors are post-event explanatory context, not available operational predictors. Weak holdout fit and substantial panel exclusions limit conclusions.

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/08_rq7_error_factors/run_analysis.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [station_panel.csv](results/station_panel.csv)
- [join_coverage.csv](results/join_coverage.csv)
- [factor_thresholds.csv](results/factor_thresholds.csv)
- [factor_descriptive.csv](results/factor_descriptive.csv)
- [stratified_contrasts.csv](results/stratified_contrasts.csv)
- [regression_coefficients.csv](results/regression_coefficients.csv)
- [model_diagnostics.csv](results/model_diagnostics.csv)
- [shap_group_importance.csv](results/shap_group_importance.csv)
- [feature_correlations.csv](results/feature_correlations.csv)
- [factor_shap.png](results/factor_shap.png)
- [tmin_stratified.png](results/tmin_stratified.png)
- [tmax_stratified.png](results/tmax_stratified.png)

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.
