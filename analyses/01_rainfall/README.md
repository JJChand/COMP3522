# 01 - Rainfall data access on macOS with Python

The [database schema guide](../../DATABASE_AGENT_GUIDE.md) says that the
`course_project` server already holds the 2022–2025 9-day forecast vintages
and daily rainfall observations. Check its live coverage before importing any
new source data. The Python program in this folder reads the existing tables
and prints small results in Terminal. It does not save rainfall files on this
Mac or write to PostgreSQL.

If your `.venv` and database `.env` are already configured, the complete
run without GPT is **one command** from this repository's root. Disconnect
the conflicting VPN, keep Tailscale connected, and copy only the command text
into Terminal (not the fence):

```text
.venv/bin/python analyses/01_rainfall/run_final.py
```

It runs both course analyses, makes the aggregate CSVs and plots, and writes
`analyses/01_rainfall/results/research_conclusions.md`. It prompts once if
the database password is absent from `.env`. The steps below explain each
part and how to inspect failures.

## Data to retrieve

| Purpose | Existing database source | Keep |
| --- | --- | --- |
| PSR forecast | `project.hko_forecast_daily` + `project.hko_forecast_issue` | `forecast_issue_id`, `bulletin_time_hkt`, `valid_date`, `lead_days`, `psr` |
| Observed daily rainfall | `project.v_hko_daily_observation` | `observation_date`, `series_code`, `station_name`, `value_text`, `value_numeric`, `data_completeness`, `source_relative_path` |
| Station coordinates, when needed for spatial weights | `project.hko_station` | `station_code`, `station_name`, `latitude`, `longitude` |

Use observation series `obs_hko_daily_rainfall` and
`obs_spatial_daily_rainfall`. Keep every forecast bulletin vintage rather
than deduplicating by valid date. `Trace` is preserved as source text and must
not silently become zero. The station names in observations have no enforced
join to station codes; review that mapping before spatial weighting.

The HKO gridded nowcast is a short-horizon forecast, not the observed daily
rainfall target. The current 9-day API response cannot reconstruct archived
2022–2025 bulletin vintages. Temperature and multistation JSON series are not
needed for the initial PSR calibration.

## 1. Prepare Python while your normal internet connection works

Open Terminal in this repository:

```sh
cd /Users/chandler/Code/COMP3522
python3 -m venv .venv
.venv/bin/python -m pip install "psycopg[binary]"
.venv/bin/python -m pip install shapely pyproj
```

This installs the PostgreSQL driver and two geometry libraries in the
ignored `.venv/` directory. The plot commands use the Mac's `python3` with
Matplotlib; if it is absent, install it for that interpreter before the
complete run.
The project code and procedure live in `analyses/01_rainfall/`. The script
uses Python's standard library to read `.env`; it does not need
`python-dotenv`, pandas, or SQLAlchemy.

## 2. Set the **database** account

Your screenshot shows `psql` trying the local socket
`/tmp/.s.PGSQL.5432` as user `chandler`. That is the Mac login, not a role on
the course database. `psql` also does not automatically read `.env`, even
after `cp .env.example .env`.

The Python program **does** read the repository-root `.env`. That file is
already present and is ignored by Git. Open it in an editor and ensure:

```text
PGHOST=100.85.176.85
PGPORT=5432
PGDATABASE=course_project
PGUSER=YOUR_ASSIGNED_DATABASE_ACCOUNT
PGPASSWORD=
```

Replace `YOUR_ASSIGNED_DATABASE_ACCOUNT` with the PostgreSQL account assigned
to you by the database owner. The schema guide lists team accounts, but your
Mac username does not tell us which account is yours. If you have no assigned
database account, the owner must provide or create one before you can connect.
Leave `PGPASSWORD` blank to have the Python program prompt without saving it.
If it is already populated, the program can use it; never share or commit the
password.

Environment variables set in Terminal take precedence over `.env`. If you
previously exported an incorrect `PGUSER` or `PGHOST`, clear it with
`unset PGUSER PGHOST` before running the program.

Check the configuration **without connecting** and without printing secrets:

```sh
.venv/bin/python analyses/01_rainfall/fetch_rainfall.py config
```

The program refuses `PGUSER=chandler`, a local `PGHOST`, a missing account,
or a database other than `course_project`.

## 3. Check live coverage with the conflicting VPN off

Keep the database desktop, PostgreSQL, and Tailscale running. Disconnect only
the VPN that prevents this Mac from reaching the database, then run:

```text
.venv/bin/python analyses/01_rainfall/fetch_rainfall.py check --start 2022-01-01 --end 2026-01-01
```

The program connects in a read-only session and prints the connected database
and role, rainfall coverage by station/series, counts of nonnumeric and
`Trace` values, PSR coverage, and station-metadata count. The date range is
half-open: `--start` is included, `--end` is excluded.

To inspect a small sample without creating a CSV:

```text
.venv/bin/python analyses/01_rainfall/fetch_rainfall.py sample --start 2022-01-01 --end 2022-02-01 --limit 20
```

The printed rows include forecast issue time and source path, plus observed
rainfall text, numeric value, and completeness. Output goes only to Terminal.
Do not add `>` redirection if you do not want a local file.

After the initial coverage check, inspect nonnumeric values, candidate station
codes, and the number of complete stations per day:

```text
.venv/bin/python analyses/01_rainfall/fetch_rainfall.py audit --start 2022-01-01 --end 2026-01-01
```

The station-name matches are candidates for manual review, not an approved
spatial join.

## 4. Decide if anything must be imported

If the live coverage includes the PSR forecasts and rainfall observations
needed for your study, use the existing `course_project.project` tables.
No new raw-data fetch or import is needed for those dates.

If a specific date or station is genuinely missing, first identify that
exact gap and its HKO source. The canonical schema imports source provenance
through `project.hko_source_file`, series definitions through
`project.hko_observation_series`, and daily values through
`project.hko_daily_observation`. The schema guide does not contain the host's
importer implementation, so a new import must follow that importer or a
reviewed extension to those tables. Do not create a duplicate rainfall table
or invent a source-file path. No raw source CSV needs to be saved on this Mac.

The documented database has station points but no Hong Kong land-boundary
polygon. The area-weighted analysis below reads official geometry directly
into memory; it saves only station weights and aggregate results.

## 5. Findings from the 2022–2025 server audit

The `check` and `audit` runs cover 2022-01-01 through 2025-12-31. The server
already contains the rainfall observations and PSR forecast vintages needed
for this period. There is **no rainfall fetch or import to run now**.

| Finding | Treatment |
| --- | --- |
| 22 rainfall series have all 1,461 dates; Clear Water Bay has 1,096 dates starting 2023-01-01 | Use the fixed 22-series panel for the initial four-year comparison. Investigate Clear Water Bay's source path before using it in a year-comparable spatial target. Its station metadata says it began operating in 2018, so operation date does not explain the 2022 gap. |
| All 233 nonnumeric values other than `Trace` are `***` with no completeness marker | Treat as unavailable, never as zero. HKO's [daily rainfall data dictionary](https://data.weather.gov.hk/weatherAPI/doc/data_dictionary_daily_total_rainfall.pdf) defines `***` as unavailable and `C` as complete. |
| `Trace` occurs in 556 rows | Preserve the original text. HKO defines it as rainfall below 0.05 mm in its [daily rainfall display](https://www.hko.gov.hk/en/cis/dailyElement.htm?ele=RF&y=2022). A calculation may use 0 mm as an explicit approximation, followed by a sensitivity check using 0.05 mm. |
| 1,089 of 1,461 dates have every *available* station complete when `Trace` counts as valid | Do not discard every other date without testing the effect. Calculate daily usable spatial coverage after station weights are known, and mark days with inadequate coverage as unknown. |
| Every observation station name has one exact candidate station code in `project.hko_station` | Review the 23 name-to-code pairs against source titles and coordinates, then record the approved mapping before calculating spatial weights. |

For the **separate PSR calibration question**, construct a Hong Kong land-area
weighted rainfall event using the 22 fixed stations. A date qualifies only
when all 22 values are complete numeric rainfall or `Trace`; no missing area
weight is silently filled. Classify at least 10 mm only when treating `Trace`
as either 0 or just under 0.05 mm gives the same label. Join that event to
each selected forecast issue day and lead. This is an explicit station-based
estimate of HKO's “generally over Hong Kong” target, not an official observed
territory-wide rainfall series. Keep Python code in this folder and do not
download raw source CSVs to the Mac.

## Preliminary research result

The [CSV](./results/psr_calibration_preliminary.csv) and
[plot](./results/psr_calibration_preliminary.png) reproduce the five observed
PSR-category rates from the earlier project note. They are **exploratory**:
that query used an unweighted 22-station average and kept only 682 of 1,461
days. The note did not provide category sample sizes or forecast-vintage
selection, so confidence intervals and a final calibration claim cannot be
calculated from these percentages. The grey plot bars show the
[HKO-published PSR probability bands](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm).
The CSV is a small aggregated research result, not a local copy of raw
rainfall observations. Regenerate the plot with `python3
analyses/01_rainfall/plot_preliminary.py` when Matplotlib is available.

## 6. Next step: answer the temperature forecast question

**Working question:** Are HKO 9-day Tmax/Tmin forecasts less accurate on days
with more rainfall? The PSR chart above does not answer this. Use rainfall at
**HKO Headquarters** for this comparison because the temperature observations
used to score the forecasts are from that same station. A territory-wide rain
target is a separate requirement for PSR calibration.

The read-only Python analysis uses the existing server tables. For each valid
date it matches complete HKO Headquarters Tmax, Tmin, and rainfall
observations; `Trace` counts as below 0.05 mm and is represented by 0 mm for
the **≥10 mm versus <10 mm grouping only**. It takes the latest forecast
bulletin for each issue date and valid date, retains lead days 1–9, and
calculates Tmax and Tmin MAE and bias separately. The rainfall group describes
weather realized on the valid date; use it to explain errors retrospectively,
not as information available when the forecast was issued.

With the conflicting VPN disconnected and Tailscale connected, copy **only**
this single command into Terminal:

```text
.venv/bin/python analyses/01_rainfall/analyze_temperature_rain.py --start 2022-01-01 --end 2026-01-01
```

The program saves seven small aggregate CSVs in `results/`:

| File | What it establishes |
| --- | --- |
| `temperature_rain_coverage.csv` | Dates with usable rainfall and temperature observations. |
| `temperature_error_by_rain_overall.csv` | Tmax/Tmin MAE and bias for each rainfall group, with forecast counts. |
| `temperature_error_by_rain_and_lead.csv` | The same comparison at each forecast lead day, including distinct valid-date counts. |
| `temperature_mae_difference_overall.csv` | Rainy minus other-day MAE and a 95% valid-date cluster bootstrap interval. |
| `temperature_mae_difference_by_lead.csv` | The same difference for each lead; positive means higher error on ≥10 mm days. |
| `temperature_error_by_rain_and_year.csv` | Check whether the comparison holds in each year. |
| `temperature_error_by_rain_and_month.csv` | Check calendar-month differences across the four years. |

It also prints the overall MAE differences so they can be shared without
uploading raw data. If system Python has Matplotlib, make the lead-day plot
after the CSV command finishes:

```text
python3 analyses/01_rainfall/plot_temperature_rain.py
```

**Decision rule for the course answer:** First check coverage and group
counts. State whether MAE on ≥10 mm days is higher or lower than on <10 mm
days for Tmax and Tmin, report each difference in °C, and check whether the
direction is consistent across lead days and across the exported year and
month summaries. Check whether the overall date-cluster bootstrap interval
excludes zero before claiming a reliable general pattern.
Rainfall and temperature error may both vary with season; this comparison is
an association, not evidence that rainfall causes forecast errors. Keep the
PSR calibration result as a separate supporting question until its
territory-wide observed rainfall target is validated.

## 7. Next step: recompute PSR calibration from the server

The preliminary five-rate chart has no sample counts or uncertainty. The
read-only script below selects the 22 rainfall series with a record on each
2022–2025 date, keeps dates where every station has complete numeric or
`Trace` rainfall, and defines the event using their **unweighted mean**. It
treats `Trace` as an interval from 0 to less than 0.05 mm and excludes a day
if that interval could change the 10 mm event label. It retains one latest
bulletin per issue date and valid date, then calculates PSR-category event
rates and 95% bootstrap intervals clustered by valid date. Forecasts for the
same valid date share the same observed outcome; the cluster intervals account
for that repetition.

With the conflicting VPN disconnected and Tailscale connected, run this
single line:

```text
.venv/bin/python analyses/01_rainfall/analyze_psr.py
```

The program writes only small aggregates: `psr_target_coverage.csv`,
`psr_calibration.csv`, and `psr_calibration_by_lead_group.csv`. It prints the
five category rates and counts. Once those CSVs exist, make the plot with:

```text
python3 analyses/01_rainfall/plot_psr.py
```

This is a **station-mean proxy** for sensitivity comparison. For the primary
PSR result, install two geometry libraries while ordinary internet works:

```text
.venv/bin/python -m pip install shapely pyproj
```

Then, with the conflicting VPN disconnected and Tailscale connected, run:

```text
.venv/bin/python analyses/01_rainfall/analyze_psr_area.py
```

The script fetches the [18 official Home Affairs district
boundaries](https://data.gov.hk/en-data/dataset/hk-had-json1-hong-kong-administrative-boundaries)
and [CSDI topographic sea-fill
polygons](https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637221775627_85634/FeatureServer/7)
directly into memory. It subtracts the sea from the district union and uses
the remaining land polygon to clip 22 station Voronoi areas. No raw geometry
or rainfall file is saved. A geometry check with synthetic station points
produced about 1,115.65 km² of land, within 0.1% of the [Lands Department's
1,114.57 km² figure](https://www.landsd.gov.hk/en/resources/mapping-information/hk-geographic-data.html).
The live run still checks the actual database station mapping, that each
station lies within 250 m of the mask, and that weights sum to one. Review the
resulting `psr_area_weights.csv` before citing the calibration rates.

The script writes only small derived CSVs:

| File | What it establishes |
| --- | --- |
| `psr_area_weights.csv` | Matched station codes, cell areas, weights, and distance to the land mask. |
| `psr_area_target_coverage.csv` | Land-mask area, station count, complete target days, and Trace-sensitive days. |
| `psr_area_calibration.csv` | Area-weighted event frequency, sample count, and date-cluster bootstrap interval for each PSR category. |
| `psr_area_calibration_by_lead_group.csv` | The same comparison for lead days 1–3, 4–6, and 7–9. |

Plot this primary result with:

```text
python3 analyses/01_rainfall/plot_psr.py --area
```

The area-weighted target remains an approximation of HKO's wording, so compare
it with the unweighted station result. If a category's observed frequency
falls outside its HKO probability band, inspect its sample size, confidence
interval, lead groups, and proxy sensitivity before calling it miscalibrated.
The HKO probability band is the **issued forecast's meaning**: for example,
Medium Low predicts that significant rain will occur about 30–44 times per
100 forecasts with that label. It is not an independent observation or
arbitrary reference standard. The empirical event frequency tests that
forecast claim under our declared station-based proxy. Low (<30%) and High
(≥70%) have broad open-ended ranges; lying inside one of them alone is weak
evidence of calibration or practical skill. [HKO defines the categories and
their frequency interpretation here](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm).

Once all three analyses and both plots finish, create an offline Markdown
answer to **both** course questions from the fresh aggregate CSVs:

```text
python3 analyses/01_rainfall/report_results.py
```

Open `analyses/01_rainfall/results/research_conclusions.md`. It states the
rainy-day Tmax/Tmin MAE differences and uncertainty, and compares each PSR
category with its HKO probability band and the unweighted sensitivity result.
The report is derived entirely from aggregate CSVs; it saves no individual
forecast or rainfall observations.

The course answer is complete only when **both** questions have a reviewed
result: (1) Tmax/Tmin error differences by rainfall group with coverage,
counts, lead-day and year/month checks, and (2) PSR category rates with
counts, uncertainty, lead-group checks, and a declared observed-rainfall
target plus the unweighted sensitivity check. Report the result and its scope
directly; do not use the earlier preliminary five-rate plot as the final
conclusion.
