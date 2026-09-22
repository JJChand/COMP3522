# 00 - Database access feasibility

`fetch_data.ps1` performs a narrow, read-only test of the local PostgreSQL /
PostGIS database. It writes three CSV files and one metadata JSON file to the
adjacent `results/` directory:

- `connection_check.csv`: database, user, search path, and PostGIS version;
- `table_counts.csv`: live row counts for the seven core project objects;
- `forecast_temperature_sample.csv`: matched HKO Tmax/Tmin forecasts and HKO
  Headquarters observations, retaining bulletin vintage and source paths;
- `run_metadata.json`: query bounds and returned row counts.

The default sample is deliberately small (2022-01-01 through 2022-01-07,
inclusive) and excludes lead day 0.

## Setup

The script uses PostgreSQL's `psql` client, which is already installed on the
database desktop at `D:\PostgreSQL\bin\psql.exe`. Copy `.env.example` to `.env`
at the repository root, then enter your own database account details. `.env` is
ignored by Git and its values are never printed:

```powershell
Copy-Item .env.example .env
```

Alternatively, set the variables directly in the current PowerShell session:

```powershell
$env:PGHOST = 'localhost' # teammates use '100.85.176.85' through Tailscale
$env:PGPORT = '5432'
$env:PGDATABASE = 'course_project'
$env:PGUSER = '<your username>'
$env:PGPASSWORD = '<your password>'
```

For a remote connection, the host desktop, PostgreSQL, and Tailscale must be
running, and a VPN must not block Tailscale. On the database desktop, use
`localhost`.

## Run

```powershell
.\analyses\00_data_access\fetch_data.ps1
```

Optional bounds and sample size:

```powershell
.\analyses\00_data_access\fetch_data.ps1 `
  -StartDate 2022-01-01 `
  -EndDate 2022-02-01 `
  -Limit 200
```

`-EndDate` is exclusive. The script exits before connecting if `PGUSER` or
`PGPASSWORD` is absent from both the process environment and `.env`. Existing
process variables take precedence over `.env`. On a teammate's computer,
install PostgreSQL client tools or pass the client location with `-PsqlPath`.
