# Analysis organization

Use one numbered folder per research direction. Keep the code, a short method
note, and generated outputs together so each result can be reproduced without
searching across the repository.

```text
analyses/
  00_data_access/       # connection and source-data feasibility checks
  01_rainfall/          # macOS rainfall access and coverage checks
  common/                         # shared read-only database connection
  02_rq1_revisions/                # RQ1: revision size and frequency
  03_rq2_revision_direction/       # RQ2: direction and flip-flops
  04_rq3_revision_usefulness/      # RQ3: updates versus observed outcomes
  05_rq4_accuracy_by_lead/         # RQ4: temperature/RH accuracy and baselines
  06_rq5_bias/                     # RQ5: signed bias, season and year
  07_rq6_psr_calibration/          # RQ6: PSR calibration and event verification
  08_rq7_error_factors/            # RQ7: conditions associated with errors
    README.md
    run_analysis.py
    results/
```

Generated files belong in the analysis folder's `results/` directory. Result
contents must not contain credentials or unnecessarily large raw extracts.
Small, reviewed research aggregates and plots may be versioned. The
rainfall procedure reads the existing database without saving raw observations.
Its requested research CSVs and plots are aggregate outputs in
`01_rainfall/results/`.

## Task 1 sequence

Task 2 (RQ8–RQ9, external-model comparison) is on hold. Work through the Task 1
questions one at a time; each folder owns its method note, scripts and results.
Existing rainfall files are preserved rather than moved or copied.

| RQ | Directory | Status |
| --- | --- | --- |
| RQ1 | `02_rq1_revisions` | Implemented; executed results and independent SQL checks |
| RQ2 | `03_rq2_revision_direction` | Executed: numeric FFI, sign reversals and PSR transitions |
| RQ3 | `04_rq3_revision_usefulness` | Executed: temperature and validated daily-report RH revision usefulness |
| RQ4 | `05_rq4_accuracy_by_lead` | Executed: temperature/RH accuracy and matched reference skill |
| RQ5 | `06_rq5_bias` | Executed: temperature/RH bias, season/year/lead and bootstrap intervals |
| RQ6 | `07_rq6_psr_calibration` | Executed: proxy reliability, coded Brier bounds, hit rate/FAR; not exact territorial verification |
| RQ7 | `08_rq7_error_factors` | Executed: all named factor directions, stratified contrasts, regression and linear SHAP |

Start with [the Part 1 findings and remaining gaps](PART1_FINDINGS.md). Every RQ
has a `results/findings.md`; run instructions are
in its README. Shared dependencies are in `requirements.txt`; the connection
uses the repository-root `.env` and is enforced read-only. Analysis work does
not change the database, so it does not need a schema-document refresh.

Shared checks and summary generation, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe -m unittest discover -s analyses/02_rq1_revisions -p test_revisions.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
.\.venv\Scripts\python.exe analyses/common/build_part1_findings.py
```

The independent verifier records exactly which aggregates were checked; its
receipt is not full independent verification of uncertainty or fitted models.
Keep the reports' proxy, missing-measurement and retrospective-factor caveats
when using these outputs in the project. RH observations come from retained
daily JSON reports, not the mean-RH CSV; see the RQ4 source audit and canonical
guide for the validated mapping and the absent CSV-style completeness flag.
Exact territorial PSR calibration remains unproven; accepting the research
proxy changes that question's operational definition and needs team agreement.
