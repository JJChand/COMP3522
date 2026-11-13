# ECMWF Open Data: initial benchmark-feasibility investigation

This direction extends the repository's existing scripts/results/report layout.
It investigates **data access and preparation**, not a final model ranking.
The user's accepted temporal approximation is retained; final metric selection
and inferential analysis remain with the analysis teammate.

Start with [the findings report](results/findings.md). Exact observations from
the investigation are in the adjacent CSV/JSON evidence and PNG figures.

## Scope

- Operational deterministic IFS (`class=od`, `stream=oper`, `type=fc`), not
  AIFS, ensemble means, ERA5, hindcasts or observations.
- Every daily 00 UTC initialization in 2024–2025: **two index anchors**, +24
  and +168 hours. This is not proof of every lead, cycle or GRIB field.
- Complete engineering pilots for 2024-01-01 and 2025-01-01, using every
  published lead through +192 hours: 3-hour spacing through +144, then 6-hour.
- HKO Headquarters coordinates and bounded source/catalog reads from the
  repository-root `.env`, with PostgreSQL transactions enforced read-only.
- Native temperature fields, Celsius conversion, grid/interval provenance,
  four-neighbor and land–sea/orography checks, and daily HKT reconstruction.
- One **proposed**, not adopted, metric and a clearly synthetic worked example.

## Reproduce

Use the existing virtual environment and dependencies in
`analyses/requirements.txt` and `data_management/model_forecasts/requirements.txt`.
No ECMWF account, MARS key, AWS key or new package installation is needed by
these scripts. Do not supply a `.ecmwfapirc` to the public-data downloader.

From `E:\COMP3522` in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s analyses/10_ecmwf_open_data -p test_methods.py -v
.\.venv\Scripts\python.exe analyses/10_ecmwf_open_data/run_investigation.py
.\.venv\Scripts\python.exe analyses/10_ecmwf_open_data/supplementary_checks.py
.\.venv\Scripts\python.exe analyses/10_ecmwf_open_data/verify_results.py
.\.venv\Scripts\python.exe analyses/10_ecmwf_open_data/build_report.py
```

Network access and a working database connection are needed for the acquisition
and live-catalog steps. Offline verification/report generation use saved
evidence; method tests do not access either network or database. A database
connection failure is recorded explicitly; it is not credential-check success.

Successful public responses are cached with hashes and retrieval timestamps.
Reruns verify and reuse the cache. Unavailable responses are not cached as
completed data. At most four index workers are used; the complete GRIB pilots
are sequential. Byte-range downloads must return matching HTTP 206 ranges;
a full global multivariable HTTP 200 response is refused.

`cache/` is ignored by Git and retained locally for reproducibility. It contains
small index files and **global temperature-message subsets**, not Hong Kong
spatial crops. These files are not database records and are never passed to
the GFS-specific importer. Back up the cache if exact-byte reproducibility is
needed. Reviewed small CSV/JSON evidence and figures remain in `results/`.

## Safety and interpretation

There is **no database-writing option** in this investigation. The two existing
external-model tables are inspected for compatibility; no tables, views or
records are created, changed or deleted. The canonical schema remains
[`DATABASE_AGENT_GUIDE.md`](../../DATABASE_AGENT_GUIDE.md). The catalog receipt
is evidence of this check, not a replacement schema reference.

HKT reconstruction reuses the method in
[`benchmark/run_pilot.py`](../../benchmark/run_pilot.py): a conditional range
for **each daily endpoint**, with disclosed numerical padding. Its midpoint
is an explicit deterministic approximation, not an unbiased estimate or a
probabilistic interval. Instantaneous sampled extrema are kept separately.

Fixed 00 UTC pilots and a 20:00 HKT cutoff are diagnostic scenarios. Historical
model availability and latest-available-cycle selection are not established.
All output cases remain `primary_eligible=false`; this does not reject the
user's accepted approximation, but prevents a tiny engineering pilot being
mistaken for the completed benchmark.
