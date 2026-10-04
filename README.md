# COMP3522 HKO Weather Forecast Project

This repository contains reproducible analyses for evaluating Hong Kong
Observatory (HKO) forecasts. Each analysis direction lives in its own folder
under `analyses/`, together with a `results/` folder for its generated CSVs and
plots.

Task 1 is being investigated in RQ order; Task 2 is currently on hold.
See [`analyses/README.md`](analyses/README.md) for the folder map and progress,
and [`analyses/02_rq1_revisions/README.md`](analyses/02_rq1_revisions/README.md)
for the first completed revision analysis.
The [Part 1 findings index](analyses/PART1_FINDINGS.md) brings together executed
RQ1–RQ7 results and their remaining evidence gaps. Temperature and validated
daily-report RH results are available; PSR calibration uses a disclosed
rainfall research proxy, not verified official territorial event labels.

## First database feasibility check

The first analysis is a small, read-only database fetch:

```text
analyses/
  00_data_access/
    fetch_data.ps1
    README.md
    results/          # generated locally; review before versioning
```

See [`analyses/00_data_access/README.md`](analyses/00_data_access/README.md) for
environment setup and the run command.

For the current macOS rainfall and temperature-error analysis, see
[`analyses/01_rainfall/README.md`](analyses/01_rainfall/README.md). It uses
Python, reads the existing server database, and saves only aggregate research
results locally.

The fetch deliberately:

- reads credentials only from PostgreSQL environment variables;
- makes the database session read-only;
- fully qualifies every database object with the `project` schema;
- uses validated psql variables in date-bounded queries; and
- preserves forecast vintages and source-file provenance.

## External-model data management (Windows)

See [`data_management/model_forecasts/README.md`](data_management/model_forecasts/README.md)
for NOAA GFS archive sources, download commands and import into the database
referenced by the root `.env`. Downloads and database imports are separate;
the importer creates only new external-model tables and leaves HKO tables intact.
The same guide explains the separate historical ECMWF IFS access requirements.

[`DATABASE_AGENT_GUIDE.md`](DATABASE_AGENT_GUIDE.md) is the single schema
reference and includes verified live definitions and external-model import status.
Database modifications must refresh it;
see [`AGENTS.md`](AGENTS.md) for the repository's maintenance rule.
