"""Download original NOAA GFS temperature messages and load station extracts.

check/download use read-only DB connections. Only import writes to the DB.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UTC = timezone.utc
BASE_URL = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
MANIFEST_VERSION = 1


def connect(read_only=True):
    import psycopg
    from dotenv import load_dotenv

    # Passwords with ${...}, # or other literal characters stay literal.
    load_dotenv(ROOT / ".env", override=False, interpolate=False)
    names = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ValueError("Set these keys in the repository .env: " + ", ".join(missing))
    return psycopg.connect(
        host=os.environ["PGHOST"], port=int(os.environ["PGPORT"]),
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"], connect_timeout=10,
        options="-c statement_timeout=120000" +
                (" -c default_transaction_read_only=on" if read_only else ""),
        application_name="comp3522_model_data_management",
    )


def station_records(codes):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT station_code, station_name, latitude, longitude "
                "FROM project.hko_station WHERE station_code = ANY(%s) "
                "ORDER BY station_code", (codes,),
            )
            records = [dict(zip(("station_code", "station_name", "latitude", "longitude"), row))
                       for row in cursor.fetchall()]
    found = {row["station_code"] for row in records}
    if found != set(codes):
        raise ValueError("Unknown station codes: " + ", ".join(sorted(set(codes) - found)))
    return records


def selected_ranges(index_text, fields):
    """Return exact byte ranges for chosen 2 m messages from the NOAA index."""
    lines = []
    for line in index_text.splitlines():
        parts = line.split(":")
        if len(parts) < 7:
            raise ValueError("Unexpected NOAA .idx line format")
        lines.append((int(parts[1]), parts, line))
    if not lines or any(b[0] <= a[0] for a, b in zip(lines, lines[1:])):
        raise ValueError("Empty or non-monotonic NOAA index")
    ranges = []
    for i, (offset, parts, line) in enumerate(lines):
        if parts[3] in fields and parts[4] == "2 m above ground":
            end = lines[i + 1][0] - 1 if i + 1 < len(lines) else None
            ranges.append((offset, end, line))
    if not ranges or not any(":TMP:" in item[2] for item in ranges):
        raise ValueError("No 2 m TMP message in the requested file")
    return ranges


def get_grib_subset(session, url, ranges):
    chunks = []
    for start, end, _ in ranges:
        header = f"bytes={start}-{'' if end is None else end}"
        with session.get(url, headers={"Range": header}, timeout=(15, 120), stream=True) as response:
            response.raise_for_status()
            if response.status_code != 206:
                raise ValueError("Server ignored byte range; refusing full global-file download")
            if not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                raise ValueError("Unexpected Content-Range")
            content = response.content
            if end is not None and len(content) != end - start + 1:
                raise ValueError("Truncated GRIB byte range")
            if not content.startswith(b"GRIB") or not content.endswith(b"7777"):
                raise ValueError("Downloaded range is not a complete GRIB message")
            chunks.append(content)
    return b"".join(chunks)


def decode_temperature(content, stations, run_time, forecast_hour):
    import eccodes as ec

    rows = []
    message_number = 0
    with io.BytesIO(content) as stream:
        # ecCodes file API needs a real file descriptor; use message boundaries
        # (GRIB2 has its total message length in bytes 8-15) for in-memory decode.
        while stream.tell() < len(content):
            prefix = stream.read(16)
            if len(prefix) != 16 or prefix[:4] != b"GRIB" or prefix[7] != 2:
                raise ValueError("Expected GRIB edition 2")
            size = int.from_bytes(prefix[8:16], "big")
            if size < 20:
                raise ValueError("Invalid GRIB length")
            message = prefix + stream.read(size - 16)
            if len(message) != size:
                raise ValueError("Truncated GRIB message")
            gid = ec.codes_new_from_message(message)
            try:
                message_number += 1
                actual_run = datetime.strptime(
                    f"{ec.codes_get(gid, 'dataDate'):08d}{ec.codes_get(gid, 'dataTime'):04d}",
                    "%Y%m%d%H%M",
                ).replace(tzinfo=UTC)
                if actual_run != run_time:
                    raise ValueError("GRIB initialization time differs from requested run")
                ec.codes_set(gid, "stepUnits", 1)  # hours
                start_step = float(ec.codes_get(gid, "startStep"))
                end_step = float(ec.codes_get(gid, "endStep"))
                if end_step != forecast_hour:
                    raise ValueError("GRIB valid time differs from requested forecast hour")
                if ec.codes_get(gid, "typeOfLevel") != "heightAboveGround" or ec.codes_get(gid, "level") != 2:
                    raise ValueError("Expected temperature at 2 m above ground")
                unit = str(ec.codes_get(gid, "units"))
                if unit not in ("K", "C", "degC"):
                    raise ValueError("Unrecognized temperature unit")
                for station in stations:
                    point = ec.codes_grib_find_nearest(
                        gid, station["latitude"], station["longitude"], npoints=1,
                    )[0]
                    value = float(point["value"])
                    if not math.isfinite(value) or value == ec.codes_get(gid, "missingValue"):
                        raise ValueError("Missing temperature at requested station")
                    longitude = (float(point["lon"]) + 180) % 360 - 180
                    rows.append({
                        "station_code": station["station_code"],
                        "message_number": message_number,
                        "parameter_id": int(ec.codes_get(gid, "paramId")),
                        "short_name": str(ec.codes_get(gid, "shortName")),
                        "parameter_name": str(ec.codes_get(gid, "name")),
                        "step_type": str(ec.codes_get(gid, "stepType")),
                        "interval_start_utc": (run_time + timedelta(hours=start_step)).isoformat(),
                        "valid_time_utc": (run_time + timedelta(hours=end_step)).isoformat(),
                        "target_latitude": station["latitude"],
                        "target_longitude": station["longitude"],
                        "grid_latitude": float(point["lat"]), "grid_longitude": longitude,
                        "grid_distance_km": float(point["distance"]),
                        "extraction_method": "nearest_grid_point",
                        "source_value": value, "source_unit": unit,
                        "temperature_c": value - 273.15 if unit == "K" else value,
                    })
            finally:
                ec.codes_release(gid)
    if not rows:
        raise ValueError("No decoded temperature records")
    return rows


def download(args):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    stations = station_records(args.stations)
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers["User-Agent"] = "COMP3522-weather-research/1.0"
    day = args.start
    written = 0
    while day < args.end:
        for cycle in args.cycles:
            run_time = datetime(day.year, day.month, day.day, cycle, tzinfo=UTC)
            run_dir = args.directory / f"{day:%Y%m%d}" / f"{cycle:02d}"
            run_dir.mkdir(parents=True, exist_ok=True)
            for hour in range(0, args.max_hour + 1, args.step_hours):
                name = f"gfs.t{cycle:02d}z.pgrb2.0p25.f{hour:03d}"
                url = f"{BASE_URL}/gfs.{day:%Y%m%d}/{cycle:02d}/atmos/{name}"
                stem = name + "." + "-".join(args.fields)
                subset = run_dir / (stem + ".grib2")
                metadata_path = run_dir / (stem + ".json")
                if metadata_path.exists():
                    manifest = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if manifest.get("station_snapshot") != stations:
                        raise ValueError("Cached station selection/coordinates differ. Use a new --directory for this station selection.")
                    if (subset.exists() and
                        hashlib.sha256(subset.read_bytes()).hexdigest() == manifest["subset_sha256"]):
                        print(f"Cached: {day} {cycle:02d} UTC f{hour:03d}")
                        continue
                    raise ValueError(f"Cached checksum mismatch: {subset}")
                response = session.get(url + ".idx", timeout=(15, 60))
                response.raise_for_status()
                index_text = response.text
                ranges = selected_ranges(index_text, args.fields)
                content = get_grib_subset(session, url, ranges)
                # Verify the decode before marking the download as complete.
                decode_temperature(content, stations, run_time, hour)
                digest = hashlib.sha256(content).hexdigest()
                manifest = {
                    "manifest_version": MANIFEST_VERSION,
                    "source_id": str(uuid.uuid5(uuid.NAMESPACE_URL, url + "#" + digest)),
                    "provider": "NOAA", "model": "GFS",
                    "product": "pgrb2.0p25", "run_time_utc": run_time.isoformat(),
                    "forecast_hour": hour, "source_url": url, "index_url": url + ".idx",
                    "retrieved_at_utc": datetime.now(UTC).isoformat(),
                    "subset_relative_path": subset.relative_to(args.directory).as_posix(),
                    "subset_sha256": digest, "subset_size_bytes": len(content),
                    "requested_fields": args.fields,
                    "selected_index_lines": [item[2] for item in ranges],
                    "byte_ranges": [[item[0], item[1]] for item in ranges],
                    "station_snapshot": stations,
                    "availability_time_utc": None,
                    "availability_note": "Historical publication time not established; retrieval time is provenance only.",
                }
                subset.write_bytes(content)
                (run_dir / (stem + ".idx")).write_text(index_text, encoding="utf-8")
                metadata_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                written += 1
                print(f"Downloaded: {day} {cycle:02d} UTC f{hour:03d}, {len(content):,} bytes")
        day += timedelta(days=1)
    print(f"Completed. New subsets: {written}. Directory: {args.directory}")


VALUE_COLUMNS = (
    "station_code", "message_number", "parameter_id", "short_name", "parameter_name",
    "step_type", "interval_start_utc", "valid_time_utc", "target_latitude",
    "target_longitude", "grid_latitude", "grid_longitude", "grid_distance_km",
    "extraction_method", "source_value", "source_unit", "temperature_c",
)


def load_download(path, directory):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported manifest version: {path}")
    subset = (directory / manifest["subset_relative_path"]).resolve()
    if not subset.is_relative_to(directory.resolve()):
        raise ValueError("Subset path escapes download directory")
    content = subset.read_bytes()
    if (hashlib.sha256(content).hexdigest() != manifest["subset_sha256"] or
        len(content) != manifest["subset_size_bytes"]):
        raise ValueError(f"Downloaded file checksum/size mismatch: {path}")
    expected_id = uuid.uuid5(uuid.NAMESPACE_URL, manifest["source_url"] + "#" + manifest["subset_sha256"])
    if str(expected_id) != manifest["source_id"]:
        raise ValueError("Source ID differs from content identity")
    run_time = datetime.fromisoformat(manifest["run_time_utc"])
    rows = decode_temperature(content, manifest["station_snapshot"], run_time, manifest["forecast_hour"])
    return manifest, rows


def import_downloads(args):
    import psycopg
    from psycopg.types.json import Jsonb
    from schema_document import refresh_schema_document

    paths = sorted(args.directory.glob("*/*/*.json"))
    if not paths:
        raise ValueError("No completed download manifests; run download first")
    if args.dry_run:
        total = 0
        for path in paths:
            _, rows = load_download(path, args.directory)
            total += len(rows)
            print(f"Validated: {path.name}, {len(rows)} records")
        print(f"Dry run complete: {len(paths)} sources, {total} records. No database connection or writes.")
        return
    source_columns = (
        "source_id", "provider", "model", "product", "run_time_utc", "forecast_hour",
        "source_url", "index_url", "retrieved_at_utc", "subset_relative_path",
        "subset_sha256", "subset_size_bytes",
    )
    # Column names are fixed constants; all imported values are bound parameters.
    source_sql = psycopg.sql.SQL(
        "INSERT INTO project.external_model_source ({}) VALUES ({}) "
        "ON CONFLICT (source_id) DO NOTHING"
    ).format(
        psycopg.sql.SQL(", ").join(map(psycopg.sql.Identifier, (*source_columns, "manifest"))),
        psycopg.sql.SQL(", ").join(psycopg.sql.Placeholder() for _ in range(len(source_columns) + 1)),
    )
    value_sql = psycopg.sql.SQL(
        "INSERT INTO project.external_model_temperature ({}) VALUES ({}) "
        "ON CONFLICT (source_id, station_code, message_number) DO NOTHING"
    ).format(
        psycopg.sql.SQL(", ").join(map(psycopg.sql.Identifier, ("source_id", *VALUE_COLUMNS))),
        psycopg.sql.SQL(", ").join(psycopg.sql.Placeholder() for _ in range(len(VALUE_COLUMNS) + 1)),
    )
    # Schema setup is transactional. Each source file is also imported atomically.
    with connect(read_only=False) as connection:
        connection.execute((HERE / "schema.sql").read_text(encoding="utf-8"))
    # Document committed DDL before any data import, even if a later file fails.
    try:
        refresh_schema_document()
    except Exception as exc:
        raise RuntimeError("Schema setup committed, but DATABASE_AGENT_GUIDE.md refresh failed. No temperature import was started; refresh the documentation before continuing.") from exc
    total = 0
    try:
        with connect(read_only=False) as connection:
            for path in paths:
                manifest, rows = load_download(path, args.directory)
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute(source_sql, [manifest[key] for key in source_columns] + [Jsonb(manifest)])
                        for row in rows:
                            cursor.execute(value_sql, [manifest["source_id"]] + [row[key] for key in VALUE_COLUMNS])
                            total += cursor.rowcount
                print(f"Imported/verified: {path.parent.name} {path.name}, {len(rows)} records")
    finally:
        # Captures committed counts, including a partially completed import.
        try:
            refresh_schema_document()
        except Exception as exc:
            raise RuntimeError("Import attempted; some database writes may have committed, but DATABASE_AGENT_GUIDE.md refresh failed. Refresh it before marking this task complete.") from exc
    print(f"Committed {total} new temperature rows; identical existing rows were skipped.")


def check(args):
    records = station_records(args.stations)
    with connect() as connection:
        db, writable = connection.execute(
            "SELECT current_database(), has_schema_privilege(current_user, 'project', 'CREATE')"
        ).fetchone()
    print(f"Connection OK. Database: {db}. Can create project tables: {writable}.")
    print(json.dumps(records, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    check_parser = subs.add_parser("check", help="Read-only connection/station check")
    check_parser.add_argument("--stations", nargs="+", default=["HKO"])
    downloader = subs.add_parser("download", help="Download and validate NOAA GFS GRIB subsets")
    downloader.add_argument("--start", type=date.fromisoformat, required=True, help="First run date (inclusive)")
    downloader.add_argument("--end", type=date.fromisoformat, required=True, help="Last run date (exclusive)")
    downloader.add_argument("--cycles", nargs="+", type=int, choices=(0, 6, 12, 18), default=[0])
    downloader.add_argument("--max-hour", type=int, default=192)
    downloader.add_argument("--step-hours", type=int, choices=(1, 3, 6), default=3)
    downloader.add_argument("--fields", nargs="+", choices=("TMP", "TMAX", "TMIN"), default=["TMP", "TMAX", "TMIN"])
    downloader.add_argument("--stations", nargs="+", default=["HKO"])
    downloader.add_argument("--directory", type=Path, default=HERE / "downloads")
    importer = subs.add_parser("import", help="Create external tables and commit downloaded station extracts")
    importer.add_argument("--directory", type=Path, default=HERE / "downloads")
    importer.add_argument("--dry-run", action="store_true", help="Validate/decode local files without connecting or writing to PostgreSQL")
    args = parser.parse_args()
    if args.command == "download":
        if args.end <= args.start or not 0 <= args.max_hour <= 240:
            parser.error("end must follow start, and max-hour must be between 0 and 240")
        if args.max_hour > 120 and args.step_hours == 1:
            parser.error("Use 3-hourly steps beyond forecast hour 120; GFS hourly files stop there")
        if "TMP" not in args.fields:
            parser.error("Include TMP in --fields")
        args.fields = sorted(set(args.fields))
        args.cycles = sorted(set(args.cycles))
        args.stations = sorted(set(args.stations))
        args.directory = args.directory.resolve()
        download(args)
    elif args.command == "import":
        args.directory = args.directory.resolve()
        import_downloads(args)
    else:
        check(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not expose connection exceptions, which can contain credential details.
        if type(exc).__module__.startswith("psycopg"):
            print("Database operation failed. Check .env, connection, schema permissions and schema compatibility.", file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
