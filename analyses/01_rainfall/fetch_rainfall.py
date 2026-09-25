"""Read existing rainfall and PSR data from the course PostgreSQL server."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_NAMES = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")


def configuration() -> dict[str, str]:
    path = ROOT / ".env"
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key = key.removeprefix("export ").strip()
            if separator and key in ENV_NAMES:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                values[key] = value

    values.update({key: os.environ[key] for key in ENV_NAMES if os.environ.get(key)})
    required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError(
            f"Set {', '.join(missing)} in {path} or the shell environment."
        )
    if values["PGHOST"] in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("PGHOST points to this Mac; use the database server's Tailscale address.")
    if values["PGDATABASE"] != "course_project":
        raise ValueError("PGDATABASE must be course_project.")
    if values["PGUSER"] == "chandler":
        raise ValueError("chandler is your Mac account, not a database account. Set an assigned PGUSER.")
    try:
        port = int(values["PGPORT"])
    except ValueError as exc:
        raise ValueError("PGPORT must be a number.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PGPORT must be between 1 and 65535.")
    return values


def show(title: str, cursor) -> None:
    print(f"\n{title}")
    rows = cursor.fetchall()
    for row in rows:
        print(json.dumps(dict(row), default=str, ensure_ascii=False))
    print(f"Rows shown: {len(rows)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("config", "check", "audit", "sample"),
        nargs="?", default="check"
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.end <= args.start or not 1 <= args.limit <= 100:
        parser.error("--end must follow --start, and --limit must be between 1 and 100")

    config = configuration()
    if args.command == "config":
        print("Remote course_project configuration is set; no database connection attempted.")
        return 0

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError('Install the driver first: python -m pip install "psycopg[binary]"') from exc

    password = config.get("PGPASSWORD") or getpass.getpass("Database password: ")
    try:
        with psycopg.connect(
            host=config["PGHOST"],
            port=int(config["PGPORT"]),
            dbname=config["PGDATABASE"],
            user=config["PGUSER"],
            password=password,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database() AS database_name, current_user AS database_user, "
                    "inet_server_addr() AS server_address, "
                    "current_setting('transaction_read_only') AS read_only"
                )
                details = cursor.fetchone()
                if details["database_name"] != "course_project" or details["read_only"] != "on":
                    raise RuntimeError("Connected to the wrong database or a writable session.")
                print("\nConnection")
                print(json.dumps(details, default=str))

                if args.command == "check":
                    show("Rainfall coverage by series and station", cursor.execute(
                        """
                        SELECT s.series_code, s.station_name, s.unit,
                               min(o.observation_date) AS first_day,
                               max(o.observation_date) AS last_day,
                               count(*) AS rows,
                               count(*) FILTER (WHERE o.value_numeric IS NULL) AS nonnumeric_or_null,
                               count(*) FILTER (WHERE o.value_text = 'Trace') AS trace_rows
                        FROM project.hko_observation_series AS s
                        JOIN project.hko_daily_observation AS o
                          ON o.observation_series_id = s.observation_series_id
                        WHERE s.series_code IN
                              ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
                          AND o.observation_date >= %s
                          AND o.observation_date < %s
                        GROUP BY s.series_code, s.station_name, s.unit
                        ORDER BY s.series_code, s.station_name
                        """,
                        (args.start, args.end),
                    ))
                    show("PSR coverage", cursor.execute(
                        """
                        SELECT min(valid_date) AS first_day, max(valid_date) AS last_day,
                               count(*) AS forecast_rows,
                               count(DISTINCT valid_date) AS valid_days,
                               count(*) FILTER (WHERE psr IS NULL) AS missing_psr
                        FROM project.hko_forecast_daily
                        WHERE valid_date >= %s AND valid_date < %s
                          AND lead_days BETWEEN 1 AND 9
                        """,
                        (args.start, args.end),
                    ))
                    show("Station metadata", cursor.execute(
                        "SELECT count(*) AS stations FROM project.hko_station"
                    ))
                elif args.command == "audit":
                    show("Nonnumeric rainfall values other than Trace", cursor.execute(
                        """
                        SELECT s.station_name, o.value_text, o.data_completeness,
                               count(*) AS rows
                        FROM project.hko_observation_series AS s
                        JOIN project.hko_daily_observation AS o
                          ON o.observation_series_id = s.observation_series_id
                        WHERE s.series_code IN
                              ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
                          AND o.observation_date >= %s
                          AND o.observation_date < %s
                          AND o.value_numeric IS NULL
                          AND o.value_text IS DISTINCT FROM 'Trace'
                        GROUP BY s.station_name, o.value_text, o.data_completeness
                        ORDER BY rows DESC, s.station_name
                        """,
                        (args.start, args.end),
                    ))
                    show("Station-name matches to review", cursor.execute(
                        """
                        SELECT s.station_name AS observation_station,
                               array_agg(m.station_code ORDER BY m.station_code)
                                 FILTER (WHERE m.station_code IS NOT NULL)
                                 AS candidate_codes,
                               array_agg(m.first_operation_date ORDER BY m.station_code)
                                 FILTER (WHERE m.station_code IS NOT NULL)
                                 AS candidate_first_operation_dates
                        FROM (
                            SELECT DISTINCT station_name
                            FROM project.hko_observation_series
                            WHERE series_code IN
                                  ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
                        ) AS s
                        LEFT JOIN project.hko_station AS m
                          ON lower(trim(m.station_name)) = lower(trim(s.station_name))
                        GROUP BY s.station_name
                        ORDER BY s.station_name
                        """
                    ))
                    show("Daily usable-station summary", cursor.execute(
                        """
                        WITH days AS (
                            SELECT o.observation_date,
                                   count(*) AS station_rows,
                                   count(*) FILTER (
                                       WHERE o.value_numeric IS NOT NULL
                                         AND o.data_completeness = 'C'
                                   ) AS complete_numeric,
                                   count(*) FILTER (
                                       WHERE o.value_text = 'Trace'
                                         AND o.data_completeness = 'C'
                                   ) AS complete_trace
                            FROM project.hko_observation_series AS s
                            JOIN project.hko_daily_observation AS o
                              ON o.observation_series_id = s.observation_series_id
                            WHERE s.series_code IN
                                  ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
                              AND o.observation_date >= %s
                              AND o.observation_date < %s
                            GROUP BY o.observation_date
                        )
                        SELECT count(*) AS days, min(station_rows) AS min_station_rows,
                               max(station_rows) AS max_station_rows,
                               min(complete_numeric) AS min_complete_numeric,
                               max(complete_numeric) AS max_complete_numeric,
                               count(*) FILTER (
                                   WHERE complete_numeric = station_rows
                               ) AS all_stations_numeric_and_complete,
                               count(*) FILTER (
                                   WHERE complete_numeric + complete_trace = station_rows
                               ) AS all_stations_complete_including_trace
                        FROM days
                        """,
                        (args.start, args.end),
                    ))
                else:
                    show("PSR forecast sample", cursor.execute(
                        """
                        SELECT i.forecast_issue_id, i.bulletin_time_hkt,
                               f.valid_date, f.lead_days, f.psr,
                               sf.relative_path AS source_relative_path
                        FROM project.hko_forecast_daily AS f
                        JOIN project.hko_forecast_issue AS i
                          ON i.forecast_issue_id = f.forecast_issue_id
                        JOIN project.hko_source_file AS sf
                          ON sf.source_file_id = i.source_file_id
                        WHERE f.valid_date >= %s AND f.valid_date < %s
                          AND f.lead_days BETWEEN 1 AND 9
                        ORDER BY f.valid_date, i.bulletin_time_hkt
                        LIMIT %s
                        """,
                        (args.start, args.end, args.limit),
                    ))
                    show("Station rainfall sample", cursor.execute(
                        """
                        SELECT observation_date, series_code, station_name, unit,
                               value_text, value_numeric, data_completeness,
                               source_relative_path
                        FROM project.v_hko_daily_observation
                        WHERE series_code IN
                              ('obs_hko_daily_rainfall', 'obs_spatial_daily_rainfall')
                          AND observation_date >= %s AND observation_date < %s
                        ORDER BY observation_date, station_name
                        LIMIT %s
                        """,
                        (args.start, args.end, args.limit),
                    ))
    except psycopg.OperationalError as exc:
        raise RuntimeError(
            "Database connection failed. Check VPN/Tailscale, PGHOST, assigned PGUSER, and password."
        ) from exc
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
