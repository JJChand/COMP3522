# RQ2: Revision direction and flip-flops

Executed for temperature and RH forecast revisions, plus PSR category transitions.

Start with [the executed findings](results/findings.md). Detailed definitions,
limitations and concrete estimates are in that report, beside its aggregate CSVs
and static figures. Task 2 remains on hold.

## Method

FFI is path length minus range divided by N−2; continuous segments require N≥3. Primary pairs are adjacent archived bulletins ≤24 h apart, both leads 1–9. Daily-latest is a separate cadence sensitivity. Zero changes are retained; sign reversals have explicitly different adjacent/compressed denominators.

## Run from repository root

```powershell
.\.venv\Scripts\python.exe analyses/03_rq2_revision_direction/run_analysis.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/common -p test_task1.py -v
.\.venv\Scripts\python.exe analyses/common/verify_task1.py
```

Install the shared dependencies in `analyses/requirements.txt` if needed. The
connection reads the root untracked `.env` and enforces read-only transactions.
No database changes or raw-data exports are performed.

## Outputs

- [direction_by_lead.csv](results/direction_by_lead.csv)
- [flip_flop_summary.csv](results/flip_flop_summary.csv)
- [flip_flop_by_target_segment.csv](results/flip_flop_by_target_segment.csv)
- [psr_transition_counts.csv](results/psr_transition_counts.csv)
- [psr_transition_summary.csv](results/psr_transition_summary.csv)
- [revision_direction.png](results/revision_direction.png)

Every run writes `results/findings.md` and `results/run_metadata.json` with source
fingerprints and software versions. The cross-RQ verifier writes
`results/verification.json`; its stated scope is narrower than full independent
statistical verification. Synthetic tests check method edge cases. Shared source
SQL is in `../common/`. Database definitions remain solely in
`DATABASE_AGENT_GUIDE.md`.
