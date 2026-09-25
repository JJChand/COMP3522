"""Calibrate PSR against a fixed, complete 22-station rainfall proxy."""

from __future__ import annotations

import csv
import getpass
import random
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from fetch_rainfall import configuration


RESULTS = Path(__file__).resolve().parent / "results"
CATEGORIES = ("Low", "Medium Low", "Medium", "Medium High", "High")
BANDS = {"Low": "<30%", "Medium Low": "30-44%", "Medium": "45-54%",
         "Medium High": "55-69%", "High": ">=70%"}

TARGET = """
WITH panel AS (
    SELECT s.observation_series_id
    FROM project.hko_observation_series AS s
    JOIN project.hko_daily_observation AS o
      ON o.observation_series_id = s.observation_series_id
    WHERE s.series_code IN ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
      AND o.observation_date >= DATE '2022-01-01'
      AND o.observation_date < DATE '2026-01-01'
    GROUP BY s.observation_series_id
    HAVING count(*) = 1461
), station_days AS (
    SELECT o.observation_date AS valid_date,
           count(*) AS n_station_rows,
           count(*) FILTER (
               WHERE o.data_completeness = 'C'
                 AND (o.value_numeric IS NOT NULL OR o.value_text = 'Trace')
           ) AS n_usable,
           avg(CASE WHEN o.data_completeness = 'C' THEN
                    CASE WHEN o.value_numeric IS NOT NULL THEN o.value_numeric
                         WHEN o.value_text = 'Trace' THEN 0::numeric END
               END) AS rain_lower_mm,
           avg(CASE WHEN o.data_completeness = 'C' THEN
                    CASE WHEN o.value_numeric IS NOT NULL THEN o.value_numeric
                         WHEN o.value_text = 'Trace' THEN 0.05::numeric END
               END) AS rain_upper_mm
    FROM panel AS p
    JOIN project.hko_daily_observation AS o
      ON o.observation_series_id = p.observation_series_id
    WHERE o.observation_date >= DATE '2022-01-01'
      AND o.observation_date < DATE '2026-01-01'
    GROUP BY o.observation_date
), target AS (
    SELECT valid_date,
           (rain_lower_mm >= 10)::int AS significant_rain,
           (rain_lower_mm < 10 AND rain_upper_mm >= 10) AS trace_ambiguous
    FROM station_days
    WHERE n_station_rows = (SELECT count(*) FROM panel)
      AND n_usable = n_station_rows
)
"""

QUALITY = TARGET + """
SELECT (SELECT count(*) FROM panel) AS panel_stations,
       (SELECT count(*) FROM station_days) AS days_with_station_rows,
       count(*) AS complete_target_days,
       count(*) FILTER (WHERE trace_ambiguous) AS trace_ambiguous_days
FROM target
"""

CASES = TARGET + """
, ranked_forecast AS (
    SELECT f.valid_date, btrim(f.psr) AS psr, f.lead_days,
           row_number() OVER (
               PARTITION BY i.bulletin_time_hkt::date, f.valid_date
               ORDER BY i.bulletin_time_hkt DESC, f.forecast_issue_id DESC
           ) AS issue_day_rank
    FROM project.hko_forecast_daily AS f
    JOIN project.hko_forecast_issue AS i
      ON i.forecast_issue_id = f.forecast_issue_id
    WHERE f.valid_date >= DATE '2022-01-01'
      AND f.valid_date < DATE '2026-01-01'
      AND f.lead_days BETWEEN 1 AND 9
)
SELECT f.valid_date, f.psr,
       CASE WHEN f.lead_days BETWEEN 1 AND 3 THEN '1-3'
            WHEN f.lead_days BETWEEN 4 AND 6 THEN '4-6'
            ELSE '7-9' END AS lead_group,
       count(*) AS n_forecasts,
       sum(t.significant_rain) AS n_events
FROM ranked_forecast AS f
JOIN target AS t ON t.valid_date = f.valid_date
WHERE f.issue_day_rank = 1 AND NOT t.trace_ambiguous
  AND f.psr IS NOT NULL AND f.psr <> ''
GROUP BY f.valid_date, f.psr, lead_group
ORDER BY f.valid_date, f.psr, lead_group
"""


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]


def summarize(rows: list[dict], field: str | None, draws: int = 500) -> list[dict]:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["valid_date"]].append(row)
    dates = list(by_date)
    keys = [(category, group) for category in CATEGORIES
            for group in (("1-3", "4-6", "7-9") if field else ("all",))]
    totals = {key: [0, 0, set()] for key in keys}
    for row in rows:
        key = (row["psr"], row[field] if field else "all")
        totals[key][0] += row["n_forecasts"]
        totals[key][1] += row["n_events"]
        totals[key][2].add(row["valid_date"])

    samples = defaultdict(list)
    rng = random.Random(3522)
    for _ in range(draws):
        counts = defaultdict(lambda: [0, 0])
        for _ in dates:
            for row in by_date[rng.choice(dates)]:
                key = (row["psr"], row[field] if field else "all")
                counts[key][0] += row["n_forecasts"]
                counts[key][1] += row["n_events"]
        for key, (n, events) in counts.items():
            if n:
                samples[key].append(100 * events / n)

    result = []
    for category, group in keys:
        n, events, valid_days = totals[(category, group)]
        if not n:
            continue
        rates = samples[(category, group)]
        record = {"psr_category": category}
        if field:
            record["lead_group"] = group
        record.update({
            "n_forecasts": n,
            "n_valid_days": len(valid_days),
            "n_significant_rain_forecasts": events,
            "observed_rate_pct": round(100 * events / n, 1),
            "cluster_ci_low_pct": round(percentile(rates, 0.025), 1),
            "cluster_ci_high_pct": round(percentile(rates, 0.975), 1),
            "hko_probability_band": BANDS[category],
        })
        result.append(record)
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
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
            if cursor.fetchone() != {"db": "course_project", "read_only": "on"}:
                raise RuntimeError("Expected a read-only course_project connection")
            cursor.execute(QUALITY)
            quality = cursor.fetchone()
            cursor.execute(CASES)
            rows = cursor.fetchall()

    if quality["panel_stations"] != 22 or not quality["complete_target_days"]:
        raise RuntimeError(f"Unexpected fixed-panel coverage: {quality}")
    unknown = {row["psr"] for row in rows} - set(CATEGORIES)
    if unknown or not rows:
        raise RuntimeError(f"Unexpected or absent PSR categories: {sorted(unknown, key=str)}")
    overall = summarize(rows, None)
    by_lead = summarize(rows, "lead_group")
    RESULTS.mkdir(exist_ok=True)
    write_csv(RESULTS / "psr_target_coverage.csv", [quality])
    write_csv(RESULTS / "psr_calibration.csv", overall)
    write_csv(RESULTS / "psr_calibration_by_lead_group.csv", by_lead)
    print(f"PSR proxy: {quality['panel_stations']} fixed stations, "
          f"{quality['complete_target_days']} complete days, "
          f"{quality['trace_ambiguous_days']} Trace-sensitive days")
    for row in overall:
        print(f"{row['psr_category']}: {row['observed_rate_pct']}% "
              f"(95% date-cluster bootstrap {row['cluster_ci_low_pct']}–"
              f"{row['cluster_ci_high_pct']}%, {row['n_forecasts']} forecasts; "
              f"HKO band {row['hko_probability_band']})")
    print(f"Aggregate CSV results: {RESULTS}")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as exc:
        raise SystemExit(
            "Database connection failed. Check the conflicting VPN and Tailscale, then rerun."
        ) from exc
