"""Compare HKO temperature forecast errors on wetter and drier HKO station days."""

from __future__ import annotations

import argparse
import csv
import getpass
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from fetch_rainfall import configuration


RESULTS = Path(__file__).resolve().parent / "results"
SERIES = ("obs_hko_daily_tmax", "obs_hko_daily_tmin", "obs_hko_daily_rainfall")
ACTUAL = """
WITH actual AS (
    SELECT observation_date AS valid_date,
           max(value_numeric) FILTER (
               WHERE series_code = 'obs_hko_daily_tmax'
                 AND data_completeness = 'C') AS observed_tmax_c,
           max(value_numeric) FILTER (
               WHERE series_code = 'obs_hko_daily_tmin'
                 AND data_completeness = 'C') AS observed_tmin_c,
           max(CASE WHEN series_code = 'obs_hko_daily_rainfall'
                         AND data_completeness = 'C'
                    THEN CASE WHEN value_numeric IS NOT NULL THEN value_numeric
                              WHEN value_text = 'Trace' THEN 0::numeric END
               END) AS observed_rain_mm
    FROM project.v_hko_daily_observation
    WHERE series_code IN ('obs_hko_daily_tmax', 'obs_hko_daily_tmin',
                          'obs_hko_daily_rainfall')
      AND observation_date >= %(start)s
      AND observation_date < %(end)s
    GROUP BY observation_date
)
"""

PAIRS = ACTUAL + """
, ranked_forecast AS (
    SELECT f.valid_date, f.lead_days, f.forecast_tmax_c, f.forecast_tmin_c,
           row_number() OVER (
               PARTITION BY i.bulletin_time_hkt::date, f.valid_date
               ORDER BY i.bulletin_time_hkt DESC, f.forecast_issue_id DESC
           ) AS issue_day_rank
    FROM project.hko_forecast_daily AS f
    JOIN project.hko_forecast_issue AS i
      ON i.forecast_issue_id = f.forecast_issue_id
    WHERE f.valid_date >= %(start)s AND f.valid_date < %(end)s
      AND f.lead_days BETWEEN 1 AND 9
), pairs AS (
    SELECT f.valid_date, f.lead_days, v.metric,
           CASE WHEN a.observed_rain_mm >= 10
                THEN 'at_least_10_mm' ELSE 'under_10_mm' END AS rain_group,
           v.forecast_c - v.observed_c AS error_c
    FROM ranked_forecast AS f
    JOIN actual AS a ON a.valid_date = f.valid_date
    CROSS JOIN LATERAL (VALUES
        ('Tmax', f.forecast_tmax_c, a.observed_tmax_c),
        ('Tmin', f.forecast_tmin_c, a.observed_tmin_c)
    ) AS v(metric, forecast_c, observed_c)
    WHERE f.issue_day_rank = 1
      AND a.observed_rain_mm IS NOT NULL
      AND v.forecast_c IS NOT NULL AND v.observed_c IS NOT NULL
)
"""

COMPARISON = PAIRS + """
SELECT metric, lead_days, rain_group,
       count(*) AS n_forecasts,
       count(DISTINCT valid_date) AS n_valid_days,
       avg(abs(error_c)) AS mae_c,
       avg(error_c) AS bias_c
FROM pairs
GROUP BY metric, lead_days, rain_group
ORDER BY metric, lead_days, rain_group
"""

CASE_ERRORS = PAIRS + """
SELECT valid_date, metric, lead_days, rain_group, abs(error_c) AS absolute_error_c
FROM pairs
ORDER BY valid_date, metric, lead_days
"""

BY_YEAR = PAIRS + """
SELECT extract(year FROM valid_date)::int AS valid_year,
       metric, lead_days, rain_group,
       count(*) AS n_forecasts,
       count(DISTINCT valid_date) AS n_valid_days,
       avg(abs(error_c)) AS mae_c,
       avg(error_c) AS bias_c
FROM pairs
GROUP BY extract(year FROM valid_date)::int, metric, lead_days, rain_group
ORDER BY valid_year, metric, lead_days, rain_group
"""

BY_MONTH = PAIRS + """
SELECT extract(month FROM valid_date)::int AS valid_month,
       metric, lead_days, rain_group,
       count(*) AS n_forecasts,
       count(DISTINCT valid_date) AS n_valid_days,
       avg(abs(error_c)) AS mae_c,
       avg(error_c) AS bias_c
FROM pairs
GROUP BY extract(month FROM valid_date)::int, metric, lead_days, rain_group
ORDER BY valid_month, metric, lead_days, rain_group
"""

COVERAGE = ACTUAL + """
SELECT count(*) AS days_with_any_observation,
       count(*) FILTER (WHERE observed_tmax_c IS NOT NULL) AS usable_tmax_days,
       count(*) FILTER (WHERE observed_tmin_c IS NOT NULL) AS usable_tmin_days,
       count(*) FILTER (WHERE observed_rain_mm IS NOT NULL) AS usable_rain_days,
       count(*) FILTER (WHERE observed_tmax_c IS NOT NULL
                          AND observed_tmin_c IS NOT NULL
                          AND observed_rain_mm IS NOT NULL) AS usable_all_three_days,
       count(*) FILTER (WHERE observed_rain_mm >= 10) AS days_at_least_10_mm
FROM actual
"""


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rounded(value) -> float:
    return round(float(value), 3)


def summarize(rows: list[dict], lead_days: int | None = None) -> list[dict]:
    groups = {}
    for row in rows:
        if lead_days is not None and row["lead_days"] != lead_days:
            continue
        key = (row["metric"], row["rain_group"])
        sums = groups.setdefault(key, {"n": 0, "absolute": 0.0, "signed": 0.0})
        n = row["n_forecasts"]
        sums["n"] += n
        sums["absolute"] += n * float(row["mae_c"])
        sums["signed"] += n * float(row["bias_c"])
    return [
        {"metric": metric, "rain_group": rain_group, "n_forecasts": values["n"],
         "mae_c": round(values["absolute"] / values["n"], 3),
         "bias_c": round(values["signed"] / values["n"], 3)}
        for (metric, rain_group), values in sorted(groups.items())
    ]


def difference_intervals(rows: list[dict], draws: int = 500) -> dict[tuple, tuple]:
    """Bootstrap rainy-minus-other MAE, resampling complete valid dates."""
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["valid_date"]].append(row)
    dates = list(by_date)
    rng = random.Random(3522)
    samples = defaultdict(list)
    for _ in range(draws):
        totals = defaultdict(lambda: [0, 0.0])
        for _ in dates:
            for row in by_date[rng.choice(dates)]:
                for key in ((row["metric"], row["lead_days"]),
                            (row["metric"], "all")):
                    bucket = totals[(key, row["rain_group"])]
                    bucket[0] += 1
                    bucket[1] += float(row["absolute_error_c"])
        for key in {item[0] for item in totals}:
            wet = totals.get((key, "at_least_10_mm"))
            other = totals.get((key, "under_10_mm"))
            if wet and other:
                samples[key].append(wet[1] / wet[0] - other[1] / other[0])
    return {
        key: (round(sorted(values)[round((len(values) - 1) * 0.025)], 3),
              round(sorted(values)[round((len(values) - 1) * 0.975)], 3))
        for key, values in samples.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()
    if args.end <= args.start:
        parser.error("--end must be later than --start")

    config = configuration()
    password = config.get("PGPASSWORD") or getpass.getpass("Database password: ")
    with psycopg.connect(
        host=config["PGHOST"], port=int(config["PGPORT"]),
        dbname=config["PGDATABASE"], user=config["PGUSER"], password=password,
        connect_timeout=10, options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database() AS db, "
                           "current_setting('transaction_read_only') AS read_only")
            state = cursor.fetchone()
            if state != {"db": "course_project", "read_only": "on"}:
                raise RuntimeError("Expected a read-only course_project connection")
            cursor.execute("""
                SELECT series_code, count(*) AS n
                FROM project.hko_observation_series
                WHERE series_code IN ('obs_hko_daily_tmax', 'obs_hko_daily_tmin',
                                      'obs_hko_daily_rainfall')
                GROUP BY series_code
            """)
            series_counts = {row["series_code"]: row["n"] for row in cursor.fetchall()}
            if series_counts != dict.fromkeys(SERIES, 1):
                raise RuntimeError(f"Expected one HKO series for each metric; found {series_counts}")
            params = {"start": args.start, "end": args.end}
            cursor.execute(COVERAGE, params)
            coverage = cursor.fetchone()
            cursor.execute(COMPARISON, params)
            rows = cursor.fetchall()
            cursor.execute(CASE_ERRORS, params)
            case_errors = cursor.fetchall()
            cursor.execute(BY_YEAR, params)
            by_year_rows = cursor.fetchall()
            cursor.execute(BY_MONTH, params)
            by_month_rows = cursor.fetchall()

    available = {(r["metric"], r["rain_group"]) for r in rows}
    expected = {(metric, group) for metric in ("Tmax", "Tmin")
                for group in ("under_10_mm", "at_least_10_mm")}
    if not rows or not expected <= available:
        raise RuntimeError("Tmax and Tmin both need forecasts in both rainfall groups; no results written")
    intervals = difference_intervals(case_errors)
    RESULTS.mkdir(exist_ok=True)
    coverage = {"start_inclusive": args.start, "end_exclusive": args.end,
                "calendar_days": (args.end - args.start).days, **coverage}
    write_csv(RESULTS / "temperature_rain_coverage.csv", list(coverage), [coverage])
    by_lead = [
        {**{key: row[key] for key in ("metric", "lead_days", "rain_group", "n_forecasts", "n_valid_days")},
         "mae_c": rounded(row["mae_c"]), "bias_c": rounded(row["bias_c"])}
        for row in rows
    ]
    write_csv(RESULTS / "temperature_error_by_rain_and_lead.csv", list(by_lead[0]), by_lead)
    for file_name, stratum, source_rows in (
        ("temperature_error_by_rain_and_year.csv", "valid_year", by_year_rows),
        ("temperature_error_by_rain_and_month.csv", "valid_month", by_month_rows),
    ):
        output_rows = [
            {**{key: row[key] for key in
                (stratum, "metric", "lead_days", "rain_group", "n_forecasts", "n_valid_days")},
             "mae_c": rounded(row["mae_c"]), "bias_c": rounded(row["bias_c"])}
            for row in source_rows
        ]
        if output_rows:
            write_csv(RESULTS / file_name, list(output_rows[0]), output_rows)
    overall = summarize(rows)
    write_csv(RESULTS / "temperature_error_by_rain_overall.csv", list(overall[0]), overall)
    overall_differences = []
    for metric in ("Tmax", "Tmin"):
        selected = {r["rain_group"]: r for r in overall if r["metric"] == metric}
        wet, other = selected["at_least_10_mm"], selected["under_10_mm"]
        lower, upper = intervals[(metric, "all")]
        overall_differences.append({
            "metric": metric,
            "mae_difference_c": round(wet["mae_c"] - other["mae_c"], 3),
            "cluster_ci_low_c": lower, "cluster_ci_high_c": upper,
            "n_forecasts_at_least_10_mm": wet["n_forecasts"],
            "n_forecasts_under_10_mm": other["n_forecasts"],
        })
    write_csv(RESULTS / "temperature_mae_difference_overall.csv",
              list(overall_differences[0]), overall_differences)
    per_lead = {}
    for row in by_lead:
        per_lead.setdefault((row["metric"], row["lead_days"]), {})[row["rain_group"]] = row
    differences = []
    for (metric, lead), groups in sorted(per_lead.items()):
        if len(groups) == 2:
            wet, other = groups["at_least_10_mm"], groups["under_10_mm"]
            lower, upper = intervals[(metric, lead)]
            differences.append({
                "metric": metric, "lead_days": lead,
                "mae_difference_c": round(wet["mae_c"] - other["mae_c"], 3),
                "cluster_ci_low_c": lower, "cluster_ci_high_c": upper,
                "n_forecasts_at_least_10_mm": wet["n_forecasts"],
                "n_forecasts_under_10_mm": other["n_forecasts"],
            })
    if not differences:
        raise RuntimeError("No lead day has forecasts in both rainfall groups")
    write_csv(RESULTS / "temperature_mae_difference_by_lead.csv",
              list(differences[0]), differences)

    print("Read-only analysis complete. No raw observations were saved.")
    print(f"Days with usable rainfall and both temperatures: {coverage['usable_all_three_days']}/"
          f"{coverage['calendar_days']}")
    for metric in ("Tmax", "Tmin"):
        selected = {r["rain_group"]: r for r in overall if r["metric"] == metric}
        if len(selected) == 2:
            wet, other = selected["at_least_10_mm"], selected["under_10_mm"]
            print(f"{metric}: MAE {wet['mae_c']:.3f}°C (≥10 mm, {wet['n_forecasts']} forecasts) "
                  f"vs {other['mae_c']:.3f}°C (<10 mm, {other['n_forecasts']} forecasts); "
                  f"difference {wet['mae_c'] - other['mae_c']:+.3f}°C ")
            interval = next(r for r in overall_differences if r["metric"] == metric)
            print(f"{metric}: 95% date-cluster bootstrap interval "
                  f"{interval['cluster_ci_low_c']:+.3f} to "
                  f"{interval['cluster_ci_high_c']:+.3f}°C")
            lead_rows = [r for r in differences if r["metric"] == metric]
            higher = sum(r["mae_difference_c"] > 0 for r in lead_rows)
            print(f"{metric}: higher MAE on ≥10 mm days in {higher}/{len(lead_rows)} "
                  "lead-day comparisons")
    print(f"CSV results: {RESULTS}")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as exc:
        raise SystemExit(
            "Database connection failed. Check the conflicting VPN and Tailscale, then rerun."
        ) from exc
