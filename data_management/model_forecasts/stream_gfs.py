"""Resumable, bounded-memory GFS temperature import without a raw-file archive.

Writes only the existing external-model tables. Global GRIB subsets are decoded
in memory; committed station extracts and source checksums are the durable copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import manage_gfs as manager

UTC = timezone.utc
FIELDS = ["TMAX", "TMIN", "TMP"]
SOURCE_COLUMNS = (
    "source_id", "provider", "model", "product", "run_time_utc",
    "forecast_hour", "source_url", "index_url", "retrieved_at_utc",
    "subset_relative_path", "subset_sha256", "subset_size_bytes",
)
_local = threading.local()
_stop = threading.Event()


def tasks(start, end, cycles):
    day = start
    while day < end:
        for cycle in sorted(set(cycles)):
            run = datetime(day.year, day.month, day.day, cycle, tzinfo=UTC)
            for hour in range(0, 193, 3):
                yield run, hour
        day += timedelta(days=1)


def validate_rows(rows, stations, run, hour):
    expected = {"instant"} if hour == 0 else {"instant", "max", "min"}
    if len(rows) != len(stations) * len(expected):
        raise ValueError("Temperature field/station count differs from required coverage")
    for station in stations:
        selected = [r for r in rows if r["station_code"] == station["station_code"]]
        if {r["step_type"] for r in selected} != expected:
            raise ValueError("Missing or duplicate instantaneous/minimum/maximum field")
        for row in selected:
            if not math.isfinite(row["temperature_c"]) or not -100 < row["temperature_c"] < 70:
                raise ValueError("Implausible or missing decoded temperature")
            end = datetime.fromisoformat(row["valid_time_utc"])
            start = datetime.fromisoformat(row["interval_start_utc"])
            if end != run + timedelta(hours=hour) or not run <= start <= end:
                raise ValueError("Invalid forecast validity interval")
            if row["step_type"] == "instant" and start != end:
                raise ValueError("Instantaneous temperature has a nonzero interval")
            if row["step_type"] != "instant" and start >= end:
                raise ValueError("Extreme temperature has an empty interval")


def session():
    if not hasattr(_local, "session"):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        result = requests.Session()
        result.headers["User-Agent"] = "COMP3522-weather-research/2.0"
        retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
        result.mount("https://", HTTPAdapter(max_retries=retry))
        _local.session = result
    return _local.session


def message_metadata(content):
    """Retain packing/grid diagnostics needed after raw messages are released."""
    import eccodes as ec
    result = []
    position = 0
    keys = ("paramId", "shortName", "stepType", "startStep", "endStep",
            "packingType", "binaryScaleFactor", "decimalScaleFactor", "bitsPerValue",
            "Ni", "Nj", "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees")
    while position < len(content):
        size = int.from_bytes(content[position + 8:position + 16], "big")
        gid = ec.codes_new_from_message(content[position:position + size])
        try:
            ec.codes_set(gid, "stepUnits", 1)
            values = {key: ec.codes_get(gid, key) for key in keys if ec.codes_is_defined(gid, key)}
            if "binaryScaleFactor" in values and "decimalScaleFactor" in values:
                values["quantization_step_k"] = 2.0 ** values["binaryScaleFactor"] / 10.0 ** values["decimalScaleFactor"]
            result.append(values)
        finally:
            ec.codes_release(gid)
        position += size
    return result


def fetch(task, stations):
    run, hour = task
    name = f"gfs.t{run.hour:02d}z.pgrb2.0p25.f{hour:03d}"
    url = f"{manager.BASE_URL}/gfs.{run:%Y%m%d}/{run.hour:02d}/atmos/{name}"
    http = session()
    response = http.get(url + ".idx", timeout=(15, 60))
    response.raise_for_status()
    ranges = manager.selected_ranges(response.text, FIELDS)
    content = manager.get_grib_subset(http, url, ranges)
    rows = manager.decode_temperature(content, stations, run, hour)
    validate_rows(rows, stations, run, hour)
    digest = hashlib.sha256(content).hexdigest()
    manifest = {
        "manifest_version": manager.MANIFEST_VERSION,
        "source_id": str(uuid.uuid5(uuid.NAMESPACE_URL, url + "#" + digest)),
        "provider": "NOAA", "model": "GFS", "product": "pgrb2.0p25",
        "run_time_utc": run.isoformat(), "forecast_hour": hour,
        "source_url": url, "index_url": url + ".idx",
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "subset_relative_path": f"not-retained/{run:%Y%m%d}/{run.hour:02d}/{name}.TMAX-TMIN-TMP.grib2",
        "subset_sha256": digest, "subset_size_bytes": len(content),
        "requested_fields": FIELDS,
        "selected_index_lines": [r[2] for r in ranges],
        "byte_ranges": [[r[0], r[1]] for r in ranges],
        "station_snapshot": stations,
        "availability_time_utc": None,
        "availability_note": "Historical publication time not established; retrieval time is provenance only.",
        "storage_mode": "station_extract_only",
        "raw_subset_retained": False,
        "grib_message_metadata": message_metadata(content),
        "decoded_rows_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    # Only small station rows and provenance escape this function. No raw file
    # is created, so memory and disk do not grow with the number of forecasts.
    return manifest, rows


def insert_statements():
    from psycopg import sql
    def build(table, columns, conflict):
        return sql.SQL("INSERT INTO project.{} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING").format(
            sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
            sql.SQL(",").join(map(sql.Identifier, conflict)),
        )
    return (
        build("external_model_source", (*SOURCE_COLUMNS, "manifest"), ("source_id",)),
        build("external_model_temperature", ("source_id", *manager.VALUE_COLUMNS),
              ("source_id", "station_code", "message_number")),
    )


def commit_source(conn, statements, manifest, rows):
    from psycopg.types.json import Jsonb
    source_sql, value_sql = statements
    with conn.transaction():
        conn.execute(source_sql, [manifest[k] for k in SOURCE_COLUMNS] + [Jsonb(manifest)])
        with conn.cursor() as cur:
            cur.executemany(value_sql, [
                [manifest["source_id"]] + [row[k] for k in manager.VALUE_COLUMNS]
                for row in rows
            ])
        # Verify every persisted field before releasing the in-memory source.
        cur = conn.execute(
            "SELECT " + ",".join(manager.VALUE_COLUMNS) +
            " FROM project.external_model_temperature WHERE source_id=%s "
            "AND station_code=ANY(%s) ORDER BY station_code,message_number",
            (manifest["source_id"], sorted({r["station_code"] for r in rows})),
        )
        actual = cur.fetchall()
        expected = sorted(rows, key=lambda r: (r["station_code"], r["message_number"]))
        if len(actual) != len(expected):
            raise ValueError("Post-insert station row count mismatch")
        for db_row, expected_row in zip(actual, expected):
            for field, value in zip(manager.VALUE_COLUMNS, db_row):
                other = expected_row[field]
                if isinstance(value, datetime):
                    other = datetime.fromisoformat(other)
                if value != other:
                    raise ValueError("Post-insert station value mismatch: " + field)
        source = conn.execute(
            "SELECT subset_sha256,subset_size_bytes FROM project.external_model_source WHERE source_id=%s",
            (manifest["source_id"],),
        ).fetchone()
        if source != (manifest["subset_sha256"], manifest["subset_size_bytes"]):
            raise ValueError("Post-insert source identity mismatch")


def completed_tasks(conn, start, end, cycles, stations):
    # Resume from committed rows, never from an optimistic local progress file.
    rows = conn.execute("""
        SELECT s.run_time_utc,s.forecast_hour,s.manifest->'station_snapshot',
               s.manifest->'requested_fields',t.station_code,
               array_agg(t.step_type ORDER BY t.step_type)
        FROM project.external_model_source s
        JOIN project.external_model_temperature t USING(source_id)
        WHERE s.model='GFS' AND s.product='pgrb2.0p25'
          AND s.run_time_utc >= %s AND s.run_time_utc < %s
          AND EXTRACT(HOUR FROM s.run_time_utc AT TIME ZONE 'UTC')=ANY(%s)
          AND t.station_code=ANY(%s)
        GROUP BY s.source_id,s.run_time_utc,s.forecast_hour,t.station_code
    """, (datetime.combine(start, datetime.min.time(), UTC),
          datetime.combine(end, datetime.min.time(), UTC), cycles,
          [s["station_code"] for s in stations])).fetchall()
    found = {}
    for run, hour, snapshot, fields, station, steps in rows:
        if snapshot != stations or sorted(fields or []) != FIELDS:
            continue
        expected = ["instant"] if hour == 0 else ["instant", "max", "min"]
        if steps == expected:
            found.setdefault((run, hour), set()).add(station)
    codes = {s["station_code"] for s in stations}
    return {task for task, matched in found.items() if matched == codes}


def write_status(path, state, attempts=6, retry_delay=0.05):
    """Publish progress atomically without letting a Windows reader stop import.

    Editors and indexers may briefly open the destination without delete sharing,
    which prevents os.replace on Windows. A blocked progress snapshot is safe to
    skip: committed database rows, not this file, are the resume authority.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    for attempt in range(attempts):
        try:
            temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
            return True
        except PermissionError:
            if attempt + 1 < attempts:
                time.sleep(retry_delay * 2 ** attempt)
    state["status_write_failures"] = state.get("status_write_failures", 0) + 1
    if state["status_write_failures"] == 1 or state["status_write_failures"] % 100 == 0:
        print("Progress file temporarily locked; import continues and resume uses committed database rows.", flush=True)
    return False


def failure_details(exc):
    """Record a useful failure location without connection strings or messages."""
    frames = traceback.extract_tb(exc.__traceback__)
    result = {"failure_type": type(exc).__name__}
    if frames:
        frame = frames[-1]
        result["failure_location"] = {
            "file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno,
        }
    if isinstance(exc, OSError):
        result["failure_errno"] = exc.errno
        result["failure_winerror"] = getattr(exc, "winerror", None)
    return result


def run(args):
    from schema_document import refresh_schema_document
    stations = manager.station_records(["HKO"])
    wanted = list(tasks(args.start, args.end, args.cycles))
    status_path = args.status.resolve()
    lock_path = status_path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Windows file locking is released by the OS after a crash, allowing resume.
    import msvcrt
    lock = lock_path.open("a+b")
    lock.seek(0)
    if lock.read(1) == b"":
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    state = {
        "state": "starting", "pid": os.getpid(), "start": str(args.start),
        "end_exclusive": str(args.end), "cycles_utc": args.cycles,
        "workers": args.workers,
        "station": "HKO", "forecast_hours": "0:192:3", "expected_sources": len(wanted),
        "raw_storage": "in_memory_only", "started_at_utc": datetime.now(UTC).isoformat(),
        "sources_done": 0, "new_sources_this_session": 0, "downloaded_bytes_this_session": 0,
        "errors": [], "documentation_current": False,
    }
    start_clock = time.monotonic()
    since_refresh = 0
    try:
        with manager.connect(read_only=False) as conn:
            conn.autocommit = True
            done = completed_tasks(conn, args.start, args.end, args.cycles, stations)
            pending = [task for task in wanted if task not in done]
            state["sources_done"] = len(wanted) - len(pending)
            state["state"] = "running"
            refresh_schema_document()
            state["documentation_current"] = True
            write_status(status_path, state)
            last_status_clock = time.monotonic()
            print(f"Starting: {len(pending):,} pending / {len(wanted):,} sources; workers={args.workers}", flush=True)
            statements = insert_statements()
            iterator = iter(pending)
            # The bundled ecCodes native decoder is not safe for concurrent
            # calls from threads. Separate worker processes isolate its state.
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                active = {}
                for _ in range(args.workers):
                    task = next(iterator, None)
                    if task is not None:
                        active[executor.submit(fetch, task, stations)] = (task, 0)
                while active:
                    ready, _ = wait(active, timeout=1, return_when=FIRST_COMPLETED)
                    for future in ready:
                        task, attempts = active.pop(future)
                        try:
                            manifest, rows = future.result()
                        except Exception as exc:
                            # Log only a fixed class and forecast identity, never
                            # arbitrary exception strings or connection settings.
                            if attempts < 2 and not _stop.is_set():
                                active[executor.submit(fetch, task, stations)] = (task, attempts + 1)
                                continue
                            state["errors"].append({"run": task[0].isoformat(), "hour": task[1],
                                                    "error_type": type(exc).__name__})
                            print(f"Failed source: {task[0].isoformat()} f{task[1]:03d} ({type(exc).__name__})", flush=True)
                            if len(state["errors"]) >= args.max_errors:
                                _stop.set()
                        else:
                            commit_source(conn, statements, manifest, rows)
                            state["sources_done"] += 1
                            state["new_sources_this_session"] += 1
                            state["downloaded_bytes_this_session"] += manifest["subset_size_bytes"]
                            state["last_committed_run"] = manifest["run_time_utc"]
                            state["last_committed_hour"] = manifest["forecast_hour"]
                            state["documentation_current"] = False
                            since_refresh += 1
                        if since_refresh >= 260:
                            refresh_schema_document()
                            state["documentation_current"] = True
                            since_refresh = 0
                            print(f"Committed: {state['sources_done']:,}/{len(wanted):,}; "
                                  f"downloaded={state['downloaded_bytes_this_session']/1e9:.2f} GB; "
                                  f"elapsed={(time.monotonic()-start_clock)/60:.1f} min", flush=True)
                        state["updated_at_utc"] = datetime.now(UTC).isoformat()
                        state["elapsed_seconds"] = round(time.monotonic() - start_clock, 1)
                        # Avoid forcing editors/indexers to reopen this file
                        # several times a second. The final state is always
                        # attempted regardless of this progress throttle.
                        if time.monotonic() - last_status_clock >= 5:
                            write_status(status_path, state)
                            last_status_clock = time.monotonic()
                        # At most one task per worker is outstanding. Completed
                        # futures cannot accumulate global arrays in memory.
                        if not _stop.is_set():
                            following = next(iterator, None)
                            if following is not None:
                                active[executor.submit(fetch, following, stations)] = (following, 0)
            final_done = completed_tasks(conn, args.start, args.end, args.cycles, stations)
            state["sources_done"] = len(set(wanted) & final_done)
            missing = [task for task in wanted if task not in final_done]
            state["missing_sources"] = len(missing)
            state["first_missing_sources"] = [{"run": run.isoformat(), "hour": hour} for run, hour in missing[:20]]
            state["state"] = "complete" if not missing else "incomplete"
            invalid_rows = conn.execute("""
                SELECT count(*) FROM project.external_model_temperature t
                JOIN project.external_model_source s USING(source_id)
                WHERE s.model='GFS' AND s.run_time_utc >= %s AND s.run_time_utc < %s
                  AND t.station_code='HKO'
                  AND (t.valid_time_utc <> s.run_time_utc + s.forecast_hour * INTERVAL '1 hour'
                       OR t.interval_start_utc < s.run_time_utc
                       OR t.temperature_c NOT BETWEEN -100 AND 70
                       OR t.step_type NOT IN ('instant','min','max'))
            """, (datetime.combine(args.start, datetime.min.time(), UTC),
                  datetime.combine(args.end, datetime.min.time(), UTC))).fetchone()[0]
            state["invalid_committed_rows"] = invalid_rows
            if invalid_rows:
                state["state"] = "verification_failed"
    except BaseException as exc:
        state["state"] = "failed"
        state.update(failure_details(exc))
        print("Import failure diagnostics: " + json.dumps(failure_details(exc)), flush=True)
        raise
    finally:
        try:
            refresh_schema_document()
            state["documentation_current"] = True
        except Exception:
            state["documentation_current"] = False
            state["state"] = "documentation_refresh_failed"
        state["updated_at_utc"] = datetime.now(UTC).isoformat()
        state["elapsed_seconds"] = round(time.monotonic() - start_clock, 1)
        try:
            if not write_status(status_path, state):
                print("Final status (progress file locked): " + json.dumps(state), flush=True)
        finally:
            lock.close()
    print(json.dumps(state, indent=2), flush=True)
    return 0 if state["state"] == "complete" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 12, 24))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--cycles", type=int, nargs="+", choices=(0, 6, 12, 18), default=[0, 6, 12, 18])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-errors", type=int, default=12)
    parser.add_argument("--status", type=Path, default=manager.HERE / "downloads" / "gfs_2025_stream_status.json")
    args = parser.parse_args()
    args.cycles = sorted(set(args.cycles))
    if args.end <= args.start or not 1 <= args.workers <= 24 or args.max_errors < 1:
        parser.error("Require end after start, 1–24 workers, and positive max-errors")
    signal.signal(signal.SIGINT, lambda *_: _stop.set())
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    try:
        return run(args)
    except Exception as exc:
        print("Stream import failed (" + type(exc).__name__ + "). Check the credential-free status file; committed rows are resumable.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
