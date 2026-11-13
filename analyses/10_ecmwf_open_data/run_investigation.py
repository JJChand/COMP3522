"""Read-only ECMWF Open Data feasibility audit; never imports into PostgreSQL.

Public index/GRIB requests are bounded, cached, checksum-checked and resumable.
The historical audit checks TWO anchor leads, not every lead of every run.
Two complete 00 UTC engineering pilots additionally check all published leads
through +192 h. This is not a full-period model leaderboard.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import threading
import time as clock
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "data_management" / "model_forecasts"))
from manage_gfs import connect  # noqa: E402

spec = importlib.util.spec_from_file_location("existing_gfs_pilot", ROOT / "benchmark/run_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

UTC = timezone.utc
HKT = ZoneInfo("Asia/Hong_Kong")
BASES = {
    "aws": "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/",
    "google": "https://storage.googleapis.com/ecmwf-open-data/",
}
PARAMETERS = {"2t", "mx2t3", "mn2t3", "mx2t6", "mn2t6"}
ALIASES = {"2t": "2t", "mx2t3": "tmax", "mx2t6": "tmax", "mn2t3": "tmin", "mn2t6": "tmin"}
STEPS = tuple(range(0, 145, 3)) + tuple(range(150, 193, 6))
PILOT_DATES = (date(2024, 1, 1), date(2025, 1, 1))
LOCAL = threading.local()


def now():
    return datetime.now(UTC).isoformat()


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(jsonable(v), ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else jsonable(v) for k, v in row.items()})


def session():
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers["User-Agent"] = "COMP3522-ECMWF-feasibility/1.0 (public-data research)"
    return LOCAL.session


def public_get(url, byte_range=None, limit=1_000_000):
    """Never accept a full-file 200 response to a byte-range request."""
    headers = {"Accept-Encoding": "identity"}
    if byte_range:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
    attempts = []
    for attempt in range(3):
        try:
            with session().get(url, headers=headers, timeout=(10, 35), stream=True) as response:
                attempts.append({"status": response.status_code, "checked_at_utc": now()})
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < 2:
                        clock.sleep(attempt + 1)
                        continue
                expected = 206 if byte_range else 200
                if response.status_code != expected:
                    return None, {"url": url, "status": response.status_code, "attempts": attempts}
                if byte_range:
                    prefix = f"bytes {byte_range[0]}-{byte_range[1]}/"
                    if not response.headers.get("Content-Range", "").startswith(prefix):
                        raise ValueError("HTTP Content-Range differs from the requested GRIB message")
                chunks, size = [], 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Public response exceeds the bounded download limit")
                    chunks.append(chunk)
                content = b"".join(chunks)
                if byte_range and len(content) != byte_range[1] - byte_range[0] + 1:
                    raise ValueError("Truncated HTTP byte range")
                return content, {"url": url, "status": expected, "attempts": attempts,
                                 "retrieved_at_utc": now(), "bytes": len(content), "sha256": digest(content),
                                 "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
        except requests.RequestException as exc:
            attempts.append({"error_type": type(exc).__name__, "checked_at_utc": now()})
            if attempt < 2:
                clock.sleep(attempt + 1)
    return None, {"url": url, "status": "network_error", "attempts": attempts}


def cached_get(cache, key, url, byte_range=None):
    data_path = cache / key
    meta_path = Path(str(data_path) + ".json")
    if data_path.exists() and meta_path.exists():
        content = data_path.read_bytes()
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if digest(content) != metadata.get("sha256") or metadata.get("url") != url:
            raise ValueError("Cached public-data checksum or URL mismatch")
        if metadata.get("byte_range") != (list(byte_range) if byte_range else None):
            raise ValueError("Cached byte-range request differs")
        return content, metadata
    content, metadata = public_get(url, byte_range, limit=2_000_000 if byte_range else 1_000_000)
    if content is not None:
        metadata["byte_range"] = list(byte_range) if byte_range else None
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_bytes(content)
        write_json(meta_path, metadata)
    return content, metadata


def index_key(day, step, resolution):
    path = "0p4-beta" if resolution == "0p4-beta" else "ifs/0p25"
    return f"{day:%Y%m%d}/00z/{path}/oper/{day:%Y%m%d}000000-{step}h-oper-fc.index"


def inspect_index(day, step, cache):
    resolutions = ("0p4-beta", "0p25") if day < date(2024, 2, 28) else ("0p25", "0p4-beta")
    failures = []
    for resolution in resolutions:
        key = index_key(day, step, resolution)
        for mirror in ("aws", "google"):
            content, metadata = cached_get(cache, "indexes/" + mirror + "/" + key, BASES[mirror] + key)
            if content is None:
                failures.append(metadata)
                continue
            rows = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
            candidates = [r for r in rows if r.get("param") in PARAMETERS and r.get("levtype") == "sfc"]
            excluded = [r for r in candidates if int(r.get("step", -1)) != step]
            # Some historical +0 files contain tiny +3 extrema placeholders.
            # Never let those overwrite the genuine +3 forecast. This narrowly
            # scoped exclusion is recorded; other identity mismatches still fail.
            if excluded and not (step == 0 and all(r["param"] in ("mx2t3", "mn2t3") and int(r["step"]) == 3 for r in excluded)):
                raise ValueError("Index contains an unexpected out-of-lead temperature field")
            selected = [r for r in candidates if int(r.get("step", -1)) == step]
            counts = Counter(r["param"] for r in selected)
            if any(n != 1 for n in counts.values()):
                raise ValueError("Duplicate temperature parameter at a single deterministic lead")
            identity_ok = all(str(r.get("date")) == day.strftime("%Y%m%d") and
                              int(r.get("time", -1)) == 0 and int(r.get("step", -1)) == step and
                              r.get("class") == "od" and r.get("stream") == "oper" and r.get("type") == "fc"
                              for r in selected)
            if not selected or not identity_ok:
                raise ValueError("Index forecast identity does not match the requested deterministic run")
            result = dict(run_date=day.isoformat(), cycle_utc=0, forecast_hour=step, status="ok",
                          resolution=resolution, mirror=mirror, index_url=metadata["url"],
                          index_sha256=metadata["sha256"], index_bytes=len(content), index_record_count=len(rows),
                          retrieved_at_utc=metadata["retrieved_at_utc"], parameters=";".join(sorted(counts)),
                          has_2t="2t" in counts, has_max=any(p.startswith("mx2t") for p in counts),
                          has_min=any(p.startswith("mn2t") for p in counts),
                          selected_message_bytes=sum(int(r["_length"]) for r in selected),
                          identity_ok=identity_ok, failed_attempts=len(failures),
                          excluded_mismatched_fields=[{k:r[k] for k in ("param","step","_offset","_length")} for r in excluded])
            return result, selected, rows, metadata
        # A missing newer path may have a historical legacy equivalent. Errors
        # stay visible in the final receipt; they are never fabricated as data.
    return dict(run_date=day.isoformat(), cycle_utc=0, forecast_hour=step, status="unavailable",
                failures=failures), [], [], None


def get_field(day, step, index_result, field, cache):
    url = index_result["index_url"].removesuffix(".index") + ".grib2"
    offset, length = int(field["_offset"]), int(field["_length"])
    suffix_key = f"{day:%Y%m%d}/f{step:03d}_{field['param']}_{index_result['resolution']}.grib2"
    key = "grib/" + index_result["mirror"] + "/" + suffix_key
    content, metadata = cached_get(cache, key, url, (offset, offset + length - 1))
    if content is None:
        # Same object and offsets on the other official mirror; verify the GRIB
        # message identity below and record the actual successful URL.
        other = "google" if index_result["mirror"] == "aws" else "aws"
        suffix = url.removeprefix(BASES[index_result["mirror"]])
        content, metadata = cached_get(cache, "grib/" + other + "/" + suffix_key, BASES[other] + suffix, (offset, offset + length - 1))
    if content is None:
        raise RuntimeError(f"Public GRIB range unavailable: {day} +{step} {field['param']}")
    if len(content) < 20 or content[:4] != b"GRIB" or content[7] != 2 or int.from_bytes(content[8:16], "big") != len(content) or content[-4:] != b"7777":
        raise ValueError("Downloaded field is not one complete GRIB2 message")
    return content, metadata


def decode_field(content, station, expected_day, expected_step, field, metadata):
    import eccodes as ec
    gid = ec.codes_new_from_message(content)
    try:
        ec.codes_set(gid, "stepUnits", 1)
        names = ("edition", "paramId", "shortName", "name", "stepType", "units", "dataDate", "dataTime",
                 "startStep", "endStep", "typeOfLevel", "level", "gridType", "Ni", "Nj",
                 "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees", "packingType",
                 "binaryScaleFactor", "decimalScaleFactor", "bitsPerValue")
        info = {name: ec.codes_get(gid, name) for name in names}
        if info["dataDate"] != int(expected_day.strftime("%Y%m%d")) or info["dataTime"] != 0 or info["endStep"] != expected_step:
            raise ValueError("GRIB run/lead differs from its requested index")
        if info["shortName"] != field["param"]:
            raise ValueError("Index parameter differs from decoded GRIB")
        if info["units"] != "K" or info["typeOfLevel"] != "heightAboveGround" or info["level"] != 2:
            raise ValueError("Expected 2 metre temperature in kelvin")
        alias = ALIASES[info["shortName"]]
        if info["stepType"] != {"2t": "instant", "tmax": "max", "tmin": "min"}[alias]:
            raise ValueError("Unexpected native statistical-processing type")
        points = ec.codes_grib_find_nearest(gid, station["latitude"], station["longitude"], npoints=4)
        nearest = min(points, key=lambda p: p["distance"])
        value = float(nearest["value"])
        if value == ec.codes_get(gid, "missingValue") or not math.isfinite(value) or not 180 < value < 340:
            raise ValueError("Missing or implausible pilot temperature")
        run = datetime.combine(expected_day, time(), UTC)
        quantization = 2.0 ** int(info["binaryScaleFactor"]) * 10.0 ** (-int(info["decimalScaleFactor"]))
        source_id = digest((metadata["url"] + metadata["sha256"]).encode())
        row = dict(run_date=expected_day.isoformat(), source_id=source_id, station_code=station["station_code"],
                   forecast_hour=expected_step, native_short_name=info["shortName"], short_name=alias,
                   parameter_id=info["paramId"], parameter_name=info["name"], step_type=info["stepType"],
                   interval_start_utc=run + timedelta(hours=float(info["startStep"])),
                   valid_time_utc=run + timedelta(hours=float(info["endStep"])),
                   target_latitude=station["latitude"], target_longitude=station["longitude"],
                   grid_latitude=float(nearest["lat"]), grid_longitude=(float(nearest["lon"]) + 180) % 360 - 180,
                   grid_distance_km=float(nearest["distance"]), extraction_method="nearest_grid_point",
                   source_value=value, source_unit="K", temperature_c=value - 273.15,
                   packing_step_c=quantization, grid_increment_degrees=info["iDirectionIncrementInDegrees"],
                   packing_type=info["packingType"], source_url=metadata["url"], sha256=metadata["sha256"],
                   field_bytes=metadata["bytes"], retrieved_at_utc=metadata["retrieved_at_utc"],
                   historical_available_time_utc=None)
        neighbors = [dict(run_date=expected_day.isoformat(), forecast_hour=expected_step, native_short_name=info["shortName"],
                          latitude=float(p["lat"]), longitude=(float(p["lon"])+180) % 360-180,
                          distance_km=float(p["distance"]), temperature_c=float(p["value"])-273.15,
                          nearest=math.isclose(float(p["distance"]), float(nearest["distance"]), abs_tol=1e-8)) for p in points]
        return row, info, neighbors
    finally:
        ec.codes_release(gid)


def database_snapshot():
    """Bounded source reads; no DDL, DML, imports or guide refresh."""
    from psycopg.rows import dict_row
    with connect(read_only=True) as connection:
        connection.row_factory = dict_row
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        readonly = connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"]
        if readonly != "on":
            raise ValueError("Database connection is not read-only")
        station = connection.execute("SELECT station_code, station_name, latitude, longitude, elevation_m FROM project.hko_station WHERE station_code=%s", ("HKO",)).fetchone()
        tables = ["external_model_source", "external_model_temperature", "hko_forecast_daily", "hko_forecast_issue", "hko_station"]
        columns = connection.execute("""SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
            WHERE table_schema=%s AND table_name=ANY(%s) ORDER BY table_name, ordinal_position""", ("project", tables)).fetchall()
        constraints = connection.execute("""SELECT c.relname AS table_name, con.conname AS name, pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname=ANY(%s) ORDER BY c.relname, con.conname""", ("project", tables)).fetchall()
        index_rows = connection.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname=%s AND tablename=ANY(%s)", ("project", tables)).fetchall()
        model_counts = connection.execute("""SELECT model, count(*) AS sources, min(run_time_utc) AS first_run, max(run_time_utc) AS last_run
            FROM project.external_model_source GROUP BY model ORDER BY model""").fetchall()
        observation_profile = connection.execute("""SELECT s.series_code, s.unit, count(*) AS rows, min(o.observation_date) AS first_date,
            max(o.observation_date) AS last_date, count(*) FILTER (WHERE o.value_numeric IS NULL) AS null_values,
            count(*) FILTER (WHERE o.data_completeness IS DISTINCT FROM 'C') AS not_complete
            FROM project.hko_observation_series s JOIN project.hko_daily_observation o USING(observation_series_id)
            WHERE s.series_code=ANY(%s) AND o.observation_date >= %s AND o.observation_date < %s
            GROUP BY s.series_code,s.unit ORDER BY s.series_code""", (["obs_hko_daily_tmax", "obs_hko_daily_tmin"], date(2024,1,1), date(2026,1,1))).fetchall()
        days = list(PILOT_DATES)
        issues = connection.execute("""SELECT forecast_issue_id, bulletin_time_hkt, published_time_utc FROM project.hko_forecast_issue
            WHERE bulletin_time_hkt::date=ANY(%s) ORDER BY bulletin_time_hkt,forecast_issue_id""", (days,)).fetchall()
        forecasts = connection.execute("""SELECT f.forecast_issue_id,f.valid_date,f.lead_days,
            f.forecast_tmax_c::float8,f.forecast_tmin_c::float8 FROM project.hko_forecast_daily f
            JOIN project.hko_forecast_issue i USING(forecast_issue_id)
            WHERE i.bulletin_time_hkt::date=ANY(%s) AND f.lead_days BETWEEN 1 AND 7
            ORDER BY f.forecast_issue_id,f.valid_date""", (days,)).fetchall()
        target_days = [d+timedelta(days=lead) for d in days for lead in range(1,8)]
        observations = connection.execute("""SELECT s.observation_series_id,s.series_code,o.observation_date,
            o.value_numeric::float8 AS value,o.data_completeness FROM project.hko_daily_observation o
            JOIN project.hko_observation_series s USING(observation_series_id)
            WHERE s.series_code=ANY(%s) AND o.observation_date=ANY(%s) ORDER BY s.series_code,o.observation_date""",
            (["obs_hko_daily_tmax", "obs_hko_daily_tmin"], target_days)).fetchall()
        gfs_rows = connection.execute("""SELECT t.*,s.forecast_hour FROM project.external_model_temperature t
            JOIN project.external_model_source s USING(source_id)
            WHERE s.model=%s AND s.run_time_utc=%s AND t.station_code=%s
            ORDER BY t.valid_time_utc,t.short_name""", ("GFS",datetime(2024,1,1,tzinfo=UTC),"HKO")).fetchall()
    return dict(status="ok", transaction_read_only=readonly, database_write=False, inspected_at_utc=now(),
                station=station, columns=columns, constraints=constraints, indexes=index_rows,
                existing_models=model_counts, observation_profile=observation_profile,
                issues=issues, forecasts=forecasts, observations=observations, gfs_rows=gfs_rows)


def audit_consistency(rows):
    identities = [(r["run_date"],r["forecast_hour"],r["native_short_name"],r["station_code"]) for r in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate decoded pilot field")
    raw_violations = padded_violations = comparisons = 0
    max_violation = 0.0
    violations=[]
    for row in rows:
        if row["short_name"] not in ("tmax","tmin"):
            continue
        for point in rows:
            if point["run_date"] != row["run_date"] or point["short_name"] != "2t":
                continue
            if row["interval_start_utc"] <= point["valid_time_utc"] <= row["valid_time_utc"]:
                comparisons += 1
                violation = point["temperature_c"]-row["temperature_c"] if row["short_name"]=="tmax" else row["temperature_c"]-point["temperature_c"]
                max_violation = max(max_violation,violation)
                raw_violations += violation > 1e-8
                pad = max(.02,row["packing_step_c"]) + max(.02,point["packing_step_c"])
                padded_violations += violation > pad
                if violation > 1e-8:
                    violations.append(dict(run_date=row["run_date"],native_parameter=row["native_short_name"],
                                           interval_start_utc=row["interval_start_utc"],valid_time_utc=row["valid_time_utc"],
                                           forecast_hour=row["forecast_hour"],instant_forecast_hour=point["forecast_hour"],
                                           interval_extreme_c=row["temperature_c"],instantaneous_c=point["temperature_c"],
                                           violation_c=violation,numerical_allowance_c=pad,beyond_allowance=violation>pad))
    return dict(decoded_rows=len(rows),duplicate_semantic_keys=0,endpoint_raw_violations=raw_violations,
                endpoint_violations_after_disclosed_padding=padded_violations,max_raw_violation_c=max_violation,
                endpoint_comparisons=comparisons,violations=violations,
                conditional_bound_assumption_verified=padded_violations==0,
                packing_allowance_rule="max(0.02 C, one decoded packing step) per field; numerical sensitivity, not certified bound")


def daily_cases(rows, db):
    cases = []
    for run_day in PILOT_DATES:
        selected = [r for r in rows if r["run_date"]==run_day.isoformat()]
        if not selected:
            continue
        # Preserve the existing GFS pilot's fixed 20:00 HKT scenario. This is
        # explicitly NOT proof of latest-available historical model selection.
        cutoff = datetime.combine(run_day,time(20),HKT).astimezone(UTC)
        issue = pilot.select_issue(db["issues"],cutoff) if db.get("status")=="ok" else None
        for lead in range(1,8):
            target = run_day+timedelta(days=lead)
            forecasts = [f for f in db.get("forecasts",[]) if issue and f["forecast_issue_id"]==issue["forecast_issue_id"] and f["valid_date"]==target]
            for variable in ("tmax","tmin"):
                diagnostic = pilot.daily_diagnostic(selected,target,variable)
                lower,upper = diagnostic["gfs_lower_c"],diagnostic["gfs_upper_c"]
                observed_rows = [o for o in db.get("observations",[]) if o["series_code"]=="obs_hko_daily_"+variable and o["observation_date"]==target and o["data_completeness"]=="C" and o["value"] is not None]
                if len(observed_rows)>1 or len(forecasts)>1:
                    raise ValueError("Pilot join multiplies target-date cases")
                observed = observed_rows[0]["value"] if observed_rows else None
                forecast = forecasts[0]["forecast_"+variable+"_c"] if forecasts else None
                midpoint = (lower+upper)/2 if lower is not None else None
                c = dict(run_date=run_day.isoformat(),valid_date=target.isoformat(),lead_days=lead,variable=variable,
                         approximation_method="interval_envelope_midpoint" if midpoint is not None else "instantaneous_samples_only",
                         sampled_extreme_c=diagnostic["gfs_sampled_c"],sample_count=diagnostic["sample_count"],
                         interval_lower_c=lower,interval_upper_c=upper,interval_midpoint_c=midpoint,
                         reconstruction_width_c=upper-lower if lower is not None else None,
                         inner_coverage_hours=diagnostic["inner_coverage_hours"],outer_coverage_hours=diagnostic["outer_coverage_hours"],
                         exact_window_tiling=diagnostic["exact_window_tiling"],
                         window_start_utc=diagnostic["window_start_utc"],window_end_utc=diagnostic["window_end_utc"],
                         reconstruction_interpretation="conditional sensitivity envelope, not a certified daily-extreme bound",
                         forecast_issue_id=issue["forecast_issue_id"] if issue else None,
                         hko_bulletin_time_hkt=issue["bulletin_time_hkt"] if issue else None,
                         cutoff_utc=cutoff,hko_forecast_c=forecast,observed_c=observed,
                         primary_eligible=False,availability_verified=False,
                         model_run_selection="fixed 00 UTC; 20:00 HKT cutoff scenario, not verified latest-available",
                         source_ids=diagnostic["source_ids"])
                if observed is not None and forecast is not None:
                    c["hko_absolute_error_c"] = abs(forecast-observed)
                    if midpoint is not None:
                        ae_lower,ae_upper=pilot.absolute_error_bounds(lower,upper,observed)
                        c.update(interval_midpoint_absolute_error_c=abs(midpoint-observed),
                                 paired_absolute_error_difference_c=abs(midpoint-observed)-abs(forecast-observed),
                                 paired_difference_lower_c=ae_lower-abs(forecast-observed),
                                 paired_difference_upper_c=ae_upper-abs(forecast-observed))
                cases.append(c)
    return cases


def metric_example():
    inputs = [("Day A",25,27,26),("Day B",28,27,29),("Day C",30,32,29)]
    return [dict(case=label,observed_tmax_c=obs,hko_forecast_c=hko,ifs_forecast_c=ifs,
                 hko_absolute_error_c=abs(hko-obs),ifs_absolute_error_c=abs(ifs-obs),
                 paired_difference_c=abs(ifs-obs)-abs(hko-obs),synthetic=True) for label,obs,hko,ifs in inputs]


def run(args):
    cache,results=HERE/"cache",HERE/"results"
    results.mkdir(parents=True,exist_ok=True)
    started=now()
    try:
        db=database_snapshot()
        print("Read-only database snapshot succeeded; credentials omitted.",flush=True)
    except Exception as exc:
        db=dict(status="unavailable",error_type=type(exc).__name__,database_write=False)
        print("Read-only database unavailable: "+type(exc).__name__,flush=True)
    write_json(results/"database_check.json",{k:v for k,v in db.items() if k not in ("issues","forecasts","observations","gfs_rows")})
    if not db.get("station"):
        # Existing documented HKO coordinates; an explicit fallback, never
        # represented as a fresh .env/live-database lookup.
        station=dict(station_code="HKO",station_name="Hong Kong Observatory Headquarters",
                     latitude=22.30194,longitude=114.17417,coordinate_source="documented prior station snapshot; live DB unavailable")
    else:
        station=db["station"]
    dates=[]
    cursor=date.fromisoformat(args.start)
    end=date.fromisoformat(args.end)
    while cursor<end:
        dates.append(cursor)
        cursor+=timedelta(days=1)
    jobs=[(day,step) for day in dates for step in (24,168)]
    index_results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(inspect_index,day,step,cache):(day,step) for day,step in jobs}
        for n,future in enumerate(as_completed(futures),1):
            result,*_=future.result()
            index_results.append(result)
            if n%50==0 or n==len(jobs):
                print(f"Historical anchor indexes: {n}/{len(jobs)} checked",flush=True)
    index_results.sort(key=lambda r:(r["run_date"],r["forecast_hour"]))
    write_csv(results/"historical_index_audit.csv",index_results)
    write_json(results/"historical_index_audit.json",index_results)
    extracted,metadata_rows,neighbors=[],[],[]
    for day in PILOT_DATES:
        print("Decoding complete engineering pilot: "+str(day),flush=True)
        for step in STEPS:
            result,fields,index_rows,_=inspect_index(day,step,cache)
            if result["status"]!="ok":
                raise RuntimeError(f"Complete pilot missing lead {day} +{step}")
            for field in fields:
                content,receipt=get_field(day,step,result,field,cache)
                row,info,points=decode_field(content,station,day,step,field,receipt)
                extracted.append(row)
                metadata_rows.append(dict(run_date=day.isoformat(),forecast_hour=step,**info))
                if step in (0,24,168):
                    neighbors.extend(points)
            if step%24==0:
                print(f"Pilot {day}: +{step} h decoded",flush=True)
    consistency=audit_consistency(extracted)
    write_csv(results/"pilot_temperature_extracts.csv",extracted)
    write_json(results/"pilot_temperature_extracts.json",extracted)
    write_csv(results/"grib_metadata.csv",metadata_rows)
    write_csv(results/"four_neighbor_sensitivity.csv",neighbors)
    cases=daily_cases(extracted,db)
    write_csv(results/"daily_reconstruction_cases.csv",cases)
    write_json(results/"daily_reconstruction_cases.json",cases)
    write_csv(results/"metric_worked_example.csv",metric_example())
    grouped=[]
    for year in (2024,2025):
        for step in (24,168):
            group=[r for r in index_results if r["run_date"].startswith(str(year)) and r["forecast_hour"]==step]
            ok=[r for r in group if r["status"]=="ok"]
            grouped.append(dict(year=year,forecast_hour=step,expected=len(group),available=len(ok),
                                has_2t=sum(r["has_2t"] for r in ok),has_extrema=sum(r["has_max"] and r["has_min"] for r in ok),
                                unresolved=len(group)-len(ok)))
    write_csv(results/"coverage_by_year.csv",grouped)
    by_run=[]
    for day in PILOT_DATES:
        group=[r for r in extracted if r["run_date"]==day.isoformat()]
        by_run.append(dict(run_date=day.isoformat(),lead_count=len(set(r["forecast_hour"] for r in group)),
                           field_count=len(group),field_bytes=sum(r["field_bytes"] for r in group),
                           parameter_counts=dict(Counter(r["native_short_name"] for r in group)),
                           grid_points=sorted(set((r["grid_latitude"],r["grid_longitude"],r["grid_distance_km"]) for r in group)),
                           packing_steps_c=sorted(set(r["packing_step_c"] for r in group))))
    summary=dict(started_at_utc=started,finished_at_utc=now(),study_start=args.start,study_end_exclusive=args.end,
                 audit_grain="one deterministic 00 UTC run and one anchor lead; only +24/+168 checked across history",
                 database_write=False,database_status=db["status"],station=station,coverage=grouped,pilots=by_run,
                 consistency=consistency,case_count=len(cases),complete_interval_cases=sum(c["interval_midpoint_c"] is not None for c in cases),
                 observed_paired_cases=sum(c["observed_c"] is not None and c["hko_forecast_c"] is not None for c in cases),
                 primary_eligible_cases=0,method_script_sha256=digest(Path(__file__).read_bytes()),
                 cache_bytes=sum(p.stat().st_size for p in cache.rglob('*') if p.is_file()))
    write_json(results/"run_metadata.json",summary)
    print(json.dumps(jsonable(summary),indent=2),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start",default="2024-01-01")
    parser.add_argument("--end",default="2026-01-01",help="Exclusive run-date end")
    parser.add_argument("--workers",type=int,choices=range(1,5),default=4)
    run(parser.parse_args())
