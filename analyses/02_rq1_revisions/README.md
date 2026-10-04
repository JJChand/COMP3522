# RQ1: successive forecast revisions

Task 1(a)(i): how much does the forecast for a fixed target day change between
successive releases, and do revisions shrink as that day approaches?

Status: implemented; inspect `results/findings.md` and `results/run_metadata.json`
for the last successful execution and its coverage. This folder does not do Task 2.

## Run on Windows

From the repository root, with the existing `.env`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r analyses/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s analyses/02_rq1_revisions -p "test_*.py"
.\.venv\Scripts\python.exe analyses/02_rq1_revisions/run_analysis.py
.\.venv\Scripts\python.exe analyses/02_rq1_revisions/verify_results.py
```

On macOS/Linux use `.venv/bin/python` instead. Existing process environment
variables take precedence over `.env`; credential values are never logged.
The database session is enforced read-only. No database changes or external
downloads are needed. Default target period is 2022-01-01 through 2025-12-31.

## Definitions and comparisons

- One trajectory per `valid_date`, ordered by `bulletin_time_hkt`, not retrieval
  time. Numeric variables: Tmin, Tmax (°C), RH minimum/maximum (percentage points).
- Revision = later forecast − earlier forecast. Mean absolute revision includes
  zero changes. Revision frequency = nonzero changes / pairs with both values.
  Published numeric precision is respected using Decimal arithmetic.
- Duplicate target/time rows are collapsed only when the complete daily payload
  agrees (including weather/wind/PSR). Source IDs are retained in a duplicate
  audit. Conflicting duplicates stop the run; the database is never deduplicated.
- Pair the trajectory before filtering: require both leads in 1–9 and both
  numeric values for the relevant metric. Missing values are not bridged.
- Three separately reported scopes: all archived successive target-date pairs;
  primary adjacent archived pairs with elapsed time ≤24 hours; sensitivity using
  latest archived vintage per target/issue day over consecutive issue dates.
  The primary scope also excludes pairs skipping an observed intervening
  bulletin. None proves that all actual HKO releases were archived.
- Group pairs by the **later** lead. Daily-latest comparisons lack later lead 9
  because the predecessor would be lead 10. Same-day updates can exist at lead 9.
- Lead, cadence and target-year breakdowns prevent hiding differences in timing.
  A matched target-date near (1–3) versus far (7–8) comparison gives each date
  equal weight; its difference is not a monotonicity test or a causal effect.
  Lead 9 is left out of this contrast because it is structurally unavailable in
  the daily-latest scope and is not a comparable predecessor horizon.
- 95% percentile intervals use 1,000 target-date cluster bootstrap draws, seed
  3522. Within-date vintage dependence is preserved. Serial dependence between
  different dates is not modeled; intervals are exploratory.
- PSR is categorical: only category-change frequency here. Direction/flip-flops
  belong to RQ2, and accuracy/usefulness require observations in RQ3.

## Files and outputs

`forecast_query.sql` is the parameterized source query. `run_analysis.py` runs
quality checks, computation and figures; `plot_results.py` can rerender figures
from CSVs. `test_revisions.py` tests edge cases without a database connection.
`verify_results.py` independently recalculates every numeric scope/lead group
in SQL using `validation_query.sql`, reconciles the CSVs and saves
`results/verification.json`. It does not modify the database.

The `results/` folder contains aggregate CSVs (lead, year, cadence, gap coverage,
matched near/far and PSR changes), two PNG plots, a duplicate provenance audit,
`run_metadata.json` and `findings.md`. No raw forecast values are written.
The metadata fingerprints the ordered source rows and query and records package
versions, parameters, counts and source objects. A rerun requires access to the
same database snapshot to reproduce that exact fingerprint.

Custom bounds: `--start YYYY-MM-DD --end YYYY-MM-DD` (end exclusive);
`--bootstrap 2000 --seed 3522` changes interval replication. Custom runs overwrite
this folder's generated results; the source scripts and rainfall work are not
changed. `--no-plots` produces only the analytical CSVs and notes.
