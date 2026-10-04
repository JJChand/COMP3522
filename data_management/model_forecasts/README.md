# External forecast data: download and PostgreSQL import

This folder handles **data management**, not accuracy analysis. The executable
pipeline currently supports original NOAA GFS forecasts. ECMWF IFS acquisition
is described separately below; an IFS importer is **not** implemented here.
Existing HKO tables are never modified by this utility.

Initial verification on this workspace: `.env` connection and HKO station lookup
succeeded; the January 2024 five-file pilot downloaded and decoded successfully;
the import dry run validated 13 records; offline tests passed. The agent did
not execute the initial database-writing import. Subsequent live import status
and schema are captured in the root `DATABASE_AGENT_GUIDE.md`; refer to its live snapshot
rather than assuming these tables are still absent.

## 1. Where to get the data

| Data | Source / download mechanism | Credentials |
| --- | --- | --- |
| Original NOAA GFS forecasts | [NOAA public GFS archive on AWS](https://registry.opendata.aws/noaa-gfs-bdp-pds/), direct HTTPS GRIB2 files and `.idx` indexes | No API key or AWS account |
| Original ECMWF IFS forecasts from 2024–2025 | [ECMWF archive / MARS](https://www.ecmwf.int/en/forecasts/access-forecasts/access-archive-datasets), catalogue download or Python Web API | ECMWF account and appropriate archive entitlement; check institutional access and any charges |
| Existing HKO forecasts, observations, station coordinates | Your PostgreSQL database, connection settings in repository-root `.env` | Your existing `PG*` settings |

Example GFS file for the 00 UTC run on 1 January 2024, forecast hour 24:

```text
https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20240101/00/atmos/gfs.t00z.pgrb2.0p25.f024
```

Append `.idx` to get its variable index. The script uses
[NOAA's documented index + HTTP byte-range technique](https://www.cpc.ncep.noaa.gov/products/wesley/fast_downloading_grib.html)
to download only 2 m temperature messages (`TMP`, and `TMAX`/`TMIN` where present),
not every meteorological variable. These selected messages still cover the
**global grid**; byte ranges are variable subsets, not a Hong Kong spatial crop.
Only values at the requested station locations are imported into PostgreSQL.

## 2. Prepare the environment

Run in PowerShell from `E:\COMP3522`. No database credentials go in commands.
The script loads `E:\COMP3522\.env` automatically. Existing process environment
values take precedence; open a fresh terminal if stale `PG*` settings interfere.
Required keys: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r data_management/model_forecasts/requirements.txt
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py check
```

If `.venv` already exists, skip its creation. Activation is unnecessary.
`check` and `download` use read-only database connections. The existing database
must contain `project.hko_station`; the default station is `HKO`.
The `import` command requires permission to create tables in `project` and insert
into the new tables. It does not create another database or require PostGIS.

## 3. Download a small pilot first

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py download --start 2024-01-01 --end 2024-01-02 --cycles 0 --max-hour 24 --step-hours 6
```

This downloads five forecast files: hours 0, 6, 12, 18 and 24 from one run.
Dates select **run dates**, not target dates; `--end` is exclusive. All model
run times and forecast hours are UTC. The script checks the GRIB run time,
forecast hour, units and decode before saving a completion manifest.

Each forecast file produces a temperature-only `.grib2` subset, its `.idx`,
and a JSON manifest containing source URLs, retrieval time, SHA-256 checksum,
run/forecast metadata and the station-coordinate snapshot. They are stored in
`downloads/YYYYMMDD/HH/`, which is ignored by Git.

Downloading again skips checksum-valid completed files. An incomplete download
can be retried. If the station selection or coordinates change, use a separate
`--directory`; the script refuses to silently reuse a different station snapshot.
Network errors stop the command: previously completed files remain usable.
Missing archive files are errors, not fabricated observations.

## 4. Import into the database referenced by `.env`

**This command writes to the database.** Run it after reviewing the pilot:

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py import --dry-run
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py import
```

`--dry-run` checks checksums, metadata and decoded rows without connecting to or
writing to the database. Remove that flag for the actual import.

It creates two new tables in your existing `project` schema:

- `project.external_model_source`: one record per downloaded source subset,
  including model, UTC run time, forecast hour, URLs, checksum and manifest.
- `project.external_model_temperature`: one record per source, station and GRIB
  message; temperatures in Celsius plus original units, nearest-grid coordinates,
  distance and the exact forecast validity/interval times.

The raw GRIB files stay on disk; the database contains provenance and station
extracts, not global arrays. Back up both the database and `downloads/`.
Each source is imported transactionally. Reimporting the same files inserts no
duplicate rows. A later failure does not undo previously committed sources;
fix the error and rerun. No existing HKO records are updated or deleted.

The importer refreshes the live-snapshot section of `DATABASE_AGENT_GUIDE.md` after committed
schema setup and after the import attempt (including partially completed imports).
Documentation failures are reported as errors, not silently ignored. You can
also refresh it independently; this only reads the database:

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/schema_document.py
```

### Quantity and storage planning

The measured pilot is five subsets totaling **10,493,758 bytes (10.49 MB)** and
13 HKO temperature rows. Four positive-lead subsets average 2,404,378 bytes each;
this is a small January 2024 sample, not an archive-wide size measurement.

For `--max-hour 192 --step-hours 3`, there are 65 lead subsets per run. Assuming
temperature extrema exist at all positive leads, one station yields 193 rows per
run (one hour-zero TMP record plus 64 leads times three variables).

| Selection | Run count | Lead subsets | Approximate raw GRIB storage | Temperature rows per station (up to) |
| --- | ---: | ---: | ---: | ---: |
| One run | 1 | 65 | 155 MB | 193 |
| One run/day, 31 days | 31 | 2,015 | 4.8 GB | 5,983 |
| Four runs/day, 31 days | 124 | 8,060 | 19.2 GB | 23,932 |
| One run/day, 2024–2025 (731 days) | 731 | 47,515 | 113 GB | 141,083 |
| Four runs/day, 2024–2025 | 2,924 | 190,060 | 453 GB | 564,332 |

MB/GB are decimal. These are **planning extrapolations**, excluding `.idx`/JSON
sidecars, backups and additional December 2023 runs. Compression, season,
forecast lead and missing fields change actual sizes. The script currently
downloads full-global temperature messages, not a geographical crop; more
stations increase database rows, not GRIB download size for a fixed selection.
Database extracts are much smaller than the raw archive, but their disk size
also includes indexes and the relatively large source manifests. Measure a
month before allocating storage for two years.

To check the import using your database client:

```sql
SELECT model, min(run_time_utc), max(run_time_utc), count(*) AS source_files
FROM project.external_model_source
GROUP BY model;

SELECT station_code, step_type, short_name, count(*) AS temperature_records
FROM project.external_model_temperature
GROUP BY station_code, step_type, short_name
ORDER BY station_code, step_type, short_name;
```

For your teammate, this is a read-only handoff query, not an accuracy calculation:

```sql
SELECT s.model, s.run_time_utc, s.forecast_hour,
       t.station_code, t.parameter_name, t.step_type,
       t.interval_start_utc, t.valid_time_utc,
       (t.valid_time_utc AT TIME ZONE 'Asia/Hong_Kong') AS valid_time_hkt,
       t.temperature_c, t.grid_latitude, t.grid_longitude, t.grid_distance_km,
       s.source_url, s.retrieved_at_utc
FROM project.external_model_source AS s
JOIN project.external_model_temperature AS t USING (source_id)
ORDER BY s.run_time_utc, t.valid_time_utc, t.station_code, t.message_number;
```

## 5. Expand after the pilot

Example: one month, all four daily GFS cycles, three-hourly data to hour 192:

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py download --start 2024-01-01 --end 2024-02-01 --cycles 0 6 12 18 --max-hour 192 --step-hours 3
.\.venv\Scripts\python.exe data_management/model_forecasts/manage_gfs.py import
```

This is a **large download**: 65 lead files per run, up to three global temperature
messages per lead, four runs per day. Estimate disk/network needs from the pilot
before launching months or years. This implementation favors transparent,
sequential, resumable downloads over parallel bulk retrieval.
Use all four cycles if run selection remains undecided; once your teammate defines
the issue-time comparison rule, you may only need a subset of cycles.

The default horizon of 192 hours provides a buffer for seven-day target windows;
confirm the required horizon against the chosen HKO issue/target definition.
For target dates starting 1 January 2024, also download the necessary late-December
2023 runs (for example, start at 24 December) so early-January long leads are not
missing. Do not automatically use forecasts initialized after the HKO issue time.
Model initialization is **not** its publication time; historical availability is
not established by this downloader and is recorded as unknown in the manifest.

Use `--stations HKO OTHER_CODE` for multiple existing station codes. Coordinates
come from the local database, not from hard-coded locations. The current extraction
is nearest grid point, with no elevation adjustment or interpolation. It is a
recorded data-preparation choice your teammate should review for coastal stations.

## 6. ECMWF IFS: where and how

After account registration, **first verify archive access**. A registered account
and an API key do not by themselves establish permission to retrieve the
historical operational IFS product. Open the
[MARS catalogue](https://apps.ecmwf.int/mars-catalogue/) while signed in. If it is
restricted, inspect the [Archive Catalogue](https://apps.ecmwf.int/archive-catalogue/)
and the [ECMWF access rules](https://www.ecmwf.int/en/forecasts/accessing-forecasts);
ask the instructor/HKU or ECMWF support about archive research access rather than
substituting ERA5 or paying for access without review.

A suggested **one-run pilot selection**, to be checked against actual catalogue
availability, is operational deterministic forecasts (`class=od`, `stream=oper`,
`type=fc`, experiment version 1), surface level, 2 m temperature (`167.128`),
initialized 2024-01-01 at 00 UTC, forecast steps 0, 6, 12, 18 and 24 hours.
Where geographic subsetting is available, use a small surrounding area such as
24 N / 112 E / 21 N / 116 E (north/west/south/east), rather than the global grid.
Keep GRIB as the download format and save the generated MARS request.
These instantaneous samples test access and decoding only, not daily extremes.

After access succeeds, follow the official
[Web API setup](https://www.ecmwf.int/en/computing/software/ecmwf-web-api) and
[MARS Python examples](https://confluence.ecmwf.int/display/WEBAPI/Access+MARS)
to automate downloads. Retrieve your API key locally from
[the API key page](https://api.ecmwf.int/v1/key/); never paste it into chat or a
tracked file. Add an IFS-specific import adapter only after inspecting the
sample and request metadata. The catalogue request itself contains no API key
and can be shared after checking it for personal fields.

### Executable IFS access pilot

With `ecmwf-api-client` installed in `.venv` and the credential file configured:

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/download_ifs_pilot.py --check
.\.venv\Scripts\python.exe data_management/model_forecasts/download_ifs_pilot.py
```

`--check` is an offline check, not proof of archive entitlement. The second
command submits one historical field: 1 January 2024 at 00 UTC, +24 h, 2 m
temperature. It adds area `24/112/21/116` and output grid `0.25/0.25` to the
catalogue request. This is a small Hong Kong-area subset **regridded on ECMWF's
server**, not native IFS resolution. The exact request, checksum, run time,
retrieval time and decoded metadata are saved beside the GRIB under
`downloads/ifs_pilot/`. No credentials are saved in those files.

The pilot checks GRIB metadata, region, grid resolution and field count. It
does not connect to PostgreSQL and is not compatible with the GFS import
command. Keep database import separate until the IFS adapter has been added.
Do not treat a credential-check success as a successful download. Server/client
logs are reduced to fixed status messages to protect keys and personal details;
an access-rejection message means archive entitlement needs resolving.

1. Sign in to the [ECMWF MARS catalogue](https://apps.ecmwf.int/mars-catalogue/).
   Confirm that your account (or an HKU/instructor-provided account) can retrieve
   **operational historical deterministic IFS forecasts** for 2024–2025.
2. In the catalogue, select the deterministic forecast product for the period,
   initialization date/time, forecast steps and 2 m temperature. Restrict the
   geographic area to Hong Kong and its surrounding grid cells to reduce size.
   Avoid ERA5, ensemble means or later hindcasts as substitutes for original IFS.
3. Check actual availability and request size. Download a one-run GRIB pilot,
   and save the request metadata along with it. The catalogue can generate a
   request script for the supported Python Web API; use the generated request
   rather than guessing product codes or step availability across model upgrades.
4. Keep ECMWF API credentials out of Git and separate from PostgreSQL credentials.
   A valid PostgreSQL `.env` does **not** give access to ECMWF.
5. Once that sample and access are confirmed, add a dedicated IFS adapter that
   records the same provenance and station-extraction fields. **Do not pass IFS
   files to `manage_gfs.py import`**: it currently requires the GFS manifests.

ECMWF [real-time open data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
has a short rolling archive, so it is not by itself a 2024–2025 historical source.
[Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api) is another
interface, but inspect its model/date coverage and forecast-vs-hindcast provenance
before using it. It is not assumed equivalent to original operational IFS/GFS.

## 7. Data-management handoff rules

Preserve all runs and validity intervals. `TMP` is instantaneous 2 m temperature;
`TMAX`/`TMIN` messages are extrema over their encoded intervals, **not automatically
Hong Kong calendar-day maxima/minima**. Do not pre-label them as daily extremes.
This importer preserves the interval and leaves daily aggregation, lead-day
matching and error statistics to your teammate.

Local checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s data_management/model_forecasts
```
