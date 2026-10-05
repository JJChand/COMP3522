# RQ4: Accuracy and baselines

Temperature and RH-extrema MAE/RMSE and matched baseline skill executed. RH daily-report readings are explicitly provisional with limited validation and have no CSV completeness flag; daily mean RH remains a separate consistency diagnostic.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

Daily-latest per target/issue day, positive leads 1–9, with all-vintage sensitivity. Frozen 1991–2020 ±2-calendar-day climatology. Persistence uses issue-day-minus-2 and minus-1; historical publication times are absent, so these are retrospective comparators, not proven operational references.

RH uses HKOReadingsMinRH/MaxRH joined on report_date, not publication date.
Its frozen ±15-calendar-day 2022 reference is evaluated only in 2023–2025;
it is not a 30-year climatological normal. The reproducible source audit checks
date grain, endpoint bounds, coverage and temperature/mean-RH sanity agreement:

```powershell
.\.venv\Scripts\python.exe analyses/05_rq4_accuracy_by_lead/audit_rh_sources.py
```

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/05_rq4_accuracy_by_lead/run_analysis.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [temperature_accuracy_by_lead.csv](results/temperature_accuracy_by_lead.csv)
- [baseline_skill_by_lead.csv](results/baseline_skill_by_lead.csv)
- [climatology_calendar_day.csv](results/climatology_calendar_day.csv)
- [rh_range_consistency_by_lead.csv](results/rh_range_consistency_by_lead.csv)
- [variable_feasibility.csv](results/variable_feasibility.csv)
- [temperature_accuracy.png](results/temperature_accuracy.png)
- [rh_accuracy_by_lead.csv](results/rh_accuracy_by_lead.csv)
- [rh_baseline_skill_by_lead.csv](results/rh_baseline_skill_by_lead.csv)
- [rh_climatology_calendar_day.csv](results/rh_climatology_calendar_day.csv)
- [rh_accuracy.png](results/rh_accuracy.png)
- [rh_source_audit.json](results/rh_source_audit.json)

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.

## Regional RH interval sensitivity (preliminary, 2025)

A separate documentation supplement compares this public forecast with sampled
multi-station RH envelopes. See [the metric and execution protocol](REGIONAL_RH_METHOD.md)
and [the preliminary regional findings](results/regional_rh_findings.md).
It uses 26 acquired station sources, with a paired 20-versus-26 comparison on
89 complete dates. These regional references have different spatial and sampling
semantics from the Headquarters daily-report track above.

This supplement records an analysis already executed in a companion workspace.
It contains method and findings documents only; regional raw inputs and analysis
scripts are not included in this update. The existing `run_analysis.py` does not
reproduce this supplement. No database import or schema change is part of it.
