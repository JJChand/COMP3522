"""Calibrate PSR with fixed station Voronoi areas clipped to Hong Kong land."""

from __future__ import annotations

import getpass
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import psycopg
from psycopg.rows import dict_row
from pyproj import Transformer
from shapely import make_valid, voronoi_polygons
from shapely.geometry import MultiPoint, Point, shape
from shapely.ops import transform, unary_union

from analyze_psr import CATEGORIES, RESULTS, summarize, write_csv
from fetch_rainfall import configuration


DISTRICT_URL = (
    "https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/"
    "hksar_18_district_boundary.json"
)
SEA_URL = (
    "https://portal.csdi.gov.hk/server/rest/services/common/"
    "landsd_rcd_1637221775627_85634/FeatureServer/7/query?"
    + urlencode({
        "where": "CLASS='EWB' AND TYPE='SEF'",
        "outFields": "OBJECTID", "returnGeometry": "true", "outSR": "4326",
        "geometryPrecision": "6", "maxAllowableOffset": "0.0001",
        "f": "geojson",
    })
)

STATIONS = """
WITH panel AS (
    SELECT s.observation_series_id, s.station_name
    FROM project.hko_observation_series AS s
    JOIN project.hko_daily_observation AS o
      ON o.observation_series_id = s.observation_series_id
    WHERE s.series_code IN ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
      AND o.observation_date >= DATE '2022-01-01'
      AND o.observation_date < DATE '2026-01-01'
    GROUP BY s.observation_series_id, s.station_name
    HAVING count(*) = 1461
)
SELECT p.observation_series_id, p.station_name, m.station_code,
       m.longitude, m.latitude
FROM panel AS p
LEFT JOIN project.hko_station AS m
  ON lower(trim(m.station_name)) = lower(trim(p.station_name))
ORDER BY p.station_name
"""

TARGET = """
WITH weights AS (
    SELECT key::bigint AS observation_series_id, value::numeric AS weight
    FROM jsonb_each_text(%(weights)s::jsonb)
), station_days AS (
    SELECT o.observation_date AS valid_date,
           count(*) AS n_station_rows,
           count(*) FILTER (
               WHERE o.data_completeness = 'C'
                 AND (o.value_numeric IS NOT NULL OR o.value_text = 'Trace')
           ) AS n_usable,
           sum(w.weight * CASE WHEN o.data_completeness = 'C' THEN
               CASE WHEN o.value_numeric IS NOT NULL THEN o.value_numeric
                    WHEN o.value_text = 'Trace' THEN 0::numeric END END
           ) AS rain_lower_mm,
           sum(w.weight * CASE WHEN o.data_completeness = 'C' THEN
               CASE WHEN o.value_numeric IS NOT NULL THEN o.value_numeric
                    WHEN o.value_text = 'Trace' THEN 0.05::numeric END END
           ) AS rain_upper_mm
    FROM weights AS w
    JOIN project.hko_daily_observation AS o
      ON o.observation_series_id = w.observation_series_id
    WHERE o.observation_date >= DATE '2022-01-01'
      AND o.observation_date < DATE '2026-01-01'
    GROUP BY o.observation_date
), target AS (
    SELECT valid_date,
           (rain_lower_mm >= 10)::int AS significant_rain,
           (rain_lower_mm < 10 AND rain_upper_mm >= 10) AS trace_ambiguous
    FROM station_days
    WHERE n_station_rows = (SELECT count(*) FROM weights)
      AND n_usable = n_station_rows
)
"""

QUALITY = TARGET + """
SELECT (SELECT count(*) FROM weights) AS panel_stations,
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


def fetch_features(url: str) -> list[dict]:
    data = json.loads(subprocess.check_output(
        ["curl", "-fsSL", "--max-time", "40", url], timeout=45
    ))
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise RuntimeError(f"Official geometry endpoint returned no features: {url}")
    return data["features"]


def land_geometry():
    project = Transformer.from_crs(4326, 2326, always_xy=True).transform
    districts = unary_union([
        make_valid(shape(feature["geometry"]))
        for feature in fetch_features(DISTRICT_URL)
    ])
    sea = unary_union([
        make_valid(shape(feature["geometry"]))
        for feature in fetch_features(SEA_URL)
    ])
    land = make_valid(districts.difference(sea))
    land = transform(project, land)
    area_km2 = land.area / 1_000_000
    if not land.is_valid or not 1100 <= area_km2 <= 1130:
        raise RuntimeError(f"Land-mask area/validity check failed: {area_km2:.2f} km²")
    return land, project


def station_weights(stations: list[dict], land, project) -> list[dict]:
    if len(stations) != 22 or len({r["observation_series_id"] for r in stations}) != 22:
        raise RuntimeError(f"Expected 22 fixed rainfall stations; found {len(stations)} rows")
    if any(r["station_code"] is None for r in stations):
        raise RuntimeError("At least one rainfall station has no exact metadata match")
    if len({r["station_code"] for r in stations}) != 22:
        raise RuntimeError("Station metadata mapping is not one-to-one")
    points = [Point(*project(r["longitude"], r["latitude"])) for r in stations]
    offsets = [point.distance(land) for point in points]
    if max(offsets) > 250:
        far = [(row["station_name"], round(offset)) for row, offset in zip(stations, offsets)
               if offset > 250]
        raise RuntimeError(f"Station points farther than 250 m from land mask: {far}")
    cells = voronoi_polygons(MultiPoint(points), extend_to=land.envelope, ordered=True)
    if len(cells.geoms) != 22 or any(not cell.covers(point)
                                     for cell, point in zip(cells.geoms, points)):
        raise RuntimeError("Voronoi cells do not map one-to-one to the station points")
    result = []
    for row, cell, offset in zip(stations, cells.geoms, offsets):
        area = cell.intersection(land).area
        result.append({
            "observation_series_id": row["observation_series_id"],
            "station_code": row["station_code"],
            "station_name": row["station_name"],
            "cell_area_km2": round(area / 1_000_000, 4),
            "weight": area / land.area,
            "point_to_land_m": round(offset, 1),
        })
    if abs(sum(row["weight"] for row in result) - 1) > 0.001:
        raise RuntimeError("Voronoi weights do not cover the land mask")
    return result


def main() -> None:
    land, project = land_geometry()
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
            cursor.execute(STATIONS)
            stations = cursor.fetchall()
            weights = station_weights(stations, land, project)
            params = {"weights": json.dumps({str(r["observation_series_id"]): r["weight"]
                                              for r in weights})}
            cursor.execute(QUALITY, params)
            quality = cursor.fetchone()
            cursor.execute(CASES, params)
            rows = cursor.fetchall()

    if quality["panel_stations"] != 22 or not quality["complete_target_days"]:
        raise RuntimeError(f"Unexpected weighted target coverage: {quality}")
    unknown = {row["psr"] for row in rows} - set(CATEGORIES)
    if unknown or not rows:
        raise RuntimeError(f"Unexpected or absent PSR categories: {sorted(unknown, key=str)}")
    overall = summarize(rows, None)
    by_lead = summarize(rows, "lead_group")
    RESULTS.mkdir(exist_ok=True)
    weight_output = [{**row, "weight": round(row["weight"], 8)} for row in weights]
    write_csv(RESULTS / "psr_area_weights.csv", weight_output)
    write_csv(RESULTS / "psr_area_target_coverage.csv", [{
        "land_area_km2": round(land.area / 1_000_000, 2),
        "weight_sum": round(sum(r["weight"] for r in weights), 6), **quality,
    }])
    write_csv(RESULTS / "psr_area_calibration.csv", overall)
    write_csv(RESULTS / "psr_area_calibration_by_lead_group.csv", by_lead)
    print(f"Land mask: {land.area / 1_000_000:.2f} km²; "
          f"{len(weights)} station weights sum to {sum(r['weight'] for r in weights):.6f}")
    print(f"Complete target days: {quality['complete_target_days']}; "
          f"Trace-sensitive days: {quality['trace_ambiguous_days']}")
    for row in overall:
        print(f"{row['psr_category']}: {row['observed_rate_pct']}% "
              f"(95% date-cluster bootstrap {row['cluster_ci_low_pct']}–"
              f"{row['cluster_ci_high_pct']}%, {row['n_forecasts']} forecasts)")
    print(f"Aggregate CSV results: {RESULTS}")


if __name__ == "__main__":
    try:
        main()
    except psycopg.OperationalError as exc:
        raise SystemExit(
            "Database connection failed. Check the conflicting VPN and Tailscale, then rerun."
        ) from exc
