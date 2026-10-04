# RQ5: Bias by season and year

Temperature and RH-extrema signed-bias analyses executed. Temperature uses complete CSV observations; RH uses validated daily JSON report extrema, explicitly provisional with limited validation and no CSV completeness flag. RH errors are in percentage points.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

Forecast minus HKO Headquarters observation; positive is over-forecasting. Daily-latest cases, target-date DJF/MAM/JJA/SON and calendar year. Date-cluster and fixed 7-day block bootstrap intervals (1,000 draws). Cross-table exposes lead/season/year mix; all-vintage sensitivity remains separate.

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/06_rq5_bias/run_analysis.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [bias_overall.csv](results/bias_overall.csv)
- [bias_by_lead.csv](results/bias_by_lead.csv)
- [bias_by_season.csv](results/bias_by_season.csv)
- [bias_by_year.csv](results/bias_by_year.csv)
- [bias_by_season_year_lead.csv](results/bias_by_season_year_lead.csv)
- [all_vintage_bias_sensitivity.csv](results/all_vintage_bias_sensitivity.csv)
- [seasonal_bias.png](results/seasonal_bias.png)
- [rh_bias_overall.csv](results/rh_bias_overall.csv)
- [rh_bias_by_lead.csv](results/rh_bias_by_lead.csv)
- [rh_bias_by_season.csv](results/rh_bias_by_season.csv)
- [rh_bias_by_year.csv](results/rh_bias_by_year.csv)
- [rh_bias_by_season_year_lead.csv](results/rh_bias_by_season_year_lead.csv)
- [rh_all_vintage_bias_sensitivity.csv](results/rh_all_vintage_bias_sensitivity.csv)
- [rh_seasonal_bias.png](results/rh_seasonal_bias.png)

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.
