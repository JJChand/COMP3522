# RQ3: Revision usefulness

Temperature and RH-extrema revision usefulness executed against HKO Headquarters outcomes. RH daily-report values are explicitly provisional with limited validation.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

Same target-day HKO Headquarters observation for both forecasts. Temperature uses complete CSV extrema; RH uses validated HKOReadingsMinRH/MaxRH JSON reports, not daily mean RH. Reports have no CSV completeness flag. Compare absolute errors; changed-only and all-pair rates are separate. Primary archive-adjacent ≤24 h pairs and daily-latest pairs are reported. Lead 9 temperature has seven changed primary pairs per variable and is a same-day boundary comparison; RH counts are exported separately.

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/04_rq3_revision_usefulness/run_analysis.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [usefulness_overall.csv](results/usefulness_overall.csv)
- [usefulness_by_lead.csv](results/usefulness_by_lead.csv)
- [join_coverage.csv](results/join_coverage.csv)
- [revision_usefulness.png](results/revision_usefulness.png)
- [rh_revision_usefulness.png](results/rh_revision_usefulness.png)

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.
