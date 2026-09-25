# COMP3522 HKO Weather Forecast Project

This repository contains reproducible analyses for evaluating Hong Kong
Observatory (HKO) forecasts. Each analysis direction lives in its own folder
under `analyses/`, together with a `results/` folder for its generated CSVs and
plots.

## First database feasibility check

The first analysis is a small, read-only database fetch:

```text
analyses/
  00_data_access/
    fetch_data.ps1
    README.md
    results/          # generated locally; contents are ignored by Git
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
