# RQ6: PSR calibration

Executed against disclosed rainfall proxies; exact territorial calibration is not identified by the local observations.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

Validate existing 22-station weights against live IDs and station names. Complete fixed-panel days only; Trace bounds and ambiguous thresholds handled explicitly. Area-weighted ≥10 mm primary, unweighted and HKO-point sensitivities. Published PSR bands are not point probabilities: midpoint Brier coding, endpoint sensitivities and compatible score bounds are separate. Alarm thresholds have explicit hit-rate/FAR denominators.

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/07_rq6_psr_calibration/run_analysis.py
.\.venv\Scripts\python.exe analyses/07_rq6_psr_calibration/audit_rainfall_reports.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [reliability.csv](results/reliability.csv)
- [brier_scores.csv](results/brier_scores.csv)
- [contingency_tables.csv](results/contingency_tables.csv)
- [target_coverage.csv](results/target_coverage.csv)
- [validated_area_weights.csv](results/validated_area_weights.csv)
- [psr_reliability.png](results/psr_reliability.png)
- [rainfall_report_audit.json](results/rainfall_report_audit.json)

The retained daily-report rainfall audit rejects an apparent shortcut:
`HKOReadingsRainfall` matches the HKO Headquarters point CSV on all 1,223
numeric comparisons, while `HKOReadingsAccumRainfall` is year-to-date and
`HKOReadingsAvgRainfall` follows a cumulative-like annual profile. None supplies
confirmed daily territorial rainfall. The bounded source query is
`rainfall_report_audit_query.sql`; the audit exports aggregates, not raw records.

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.
