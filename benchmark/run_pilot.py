"""Small, reproducible GFS/HKO fairness trial; no network downloads.

Default: read-only audit. --persist writes only the derived pilot table and
refreshes DATABASE_AGENT_GUIDE.md after commit. This is not a model leaderboard.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data_management" / "model_forecasts"))
from manage_gfs import connect, decode_temperature  # noqa: E402
from schema_document import refresh_schema_document  # noqa: E402

UTC = timezone.utc
HKT = ZoneInfo("Asia/Hong_Kong")
RUN = datetime(2024, 1, 1, tzinfo=UTC)
BENCHMARK_ID = "gfs_hko_fairness_pilot_v1"
# Minimum sensitivity allowance; each field uses the larger of this value
# and one inspected GRIB quantization step. Not a certified error bound.
PADDING_C = 0.02
CUTOFF_HOUR_HKT = 20
DOWNLOADS = ROOT / "data_management" / "model_forecasts" / "downloads"


def json_ready(value):
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def digest(value):
    return hashlib.sha256(json.dumps(json_ready(value), sort_keys=True).encode()).hexdigest()


def day_window(day):
    start = datetime.combine(day, time(), HKT).astimezone(UTC)
    return start, start + timedelta(days=1)


def coverage_hours(rows, start, end):
    """Union of clipped intervals; overlapping GRIB periods count only once."""
    spans = sorted((max(r["interval_start_utc"], start), min(r["valid_time_utc"], end))
                   for r in rows if r["interval_start_utc"] < end and r["valid_time_utc"] > start)
    total = 0.0
    cursor = start
    for a, b in spans:
        if b > max(cursor, a):
            total += (b - max(cursor, a)).total_seconds() / 3600
        cursor = max(cursor, b)
    return total


def daily_diagnostic(rows, day, variable):
    """Temporal envelopes, conditional on interval extrema representing one path.

    Tmax lower = largest wholly-contained interval maximum; upper = largest
    overlapping interval maximum. Tmin reverses these sets. Outer intervals
    must cover all 24 h. Packing padding is explicit. These are reconstruction
    envelopes, never sampling confidence intervals or probabilistic forecasts.
    """
    start, end = day_window(day)
    extrema = [r for r in rows if r["short_name"] == variable]
    outer = [r for r in extrema if r["interval_start_utc"] < end and r["valid_time_utc"] > start]
    inner = [r for r in outer if r["interval_start_utc"] >= start and r["valid_time_utc"] <= end]
    instants = [r for r in rows if r["short_name"] == "2t" and start <= r["valid_time_utc"] < end]
    inner_h = coverage_hours(inner, start, end)
    outer_h = coverage_hours(outer, start, end)
    # Exact time tiling is a structural property, independent of whether the
    # particular day's envelope happens to be numerically very narrow.
    lower = upper = raw_lower = raw_upper = None
    if outer_h == 24 and inner:
        pad = lambda r: max(PADDING_C, r.get("packing_step_c", 0.0))
        if variable == "tmax":
            raw_lower = max(r["temperature_c"] for r in inner)
            raw_upper = max(r["temperature_c"] for r in outer)
            lower = max(r["temperature_c"]-pad(r) for r in inner)
            upper = max(r["temperature_c"]+pad(r) for r in outer)
        else:
            raw_lower = min(r["temperature_c"] for r in outer)
            raw_upper = min(r["temperature_c"] for r in inner)
            lower = min(r["temperature_c"]-pad(r) for r in outer)
            upper = min(r["temperature_c"]+pad(r) for r in inner)
    reducer = max if variable == "tmax" else min
    sample = reducer(r["temperature_c"] for r in instants) if instants else None
    used = outer + instants
    return {
        "window_start_utc": start, "window_end_utc": end,
        "inner_coverage_hours": inner_h, "outer_coverage_hours": outer_h,
        "exact_window_tiling": inner_h == 24,
        "raw_lower_c": raw_lower, "raw_upper_c": raw_upper,
        "gfs_lower_c": lower, "gfs_upper_c": upper,
        "gfs_sampled_c": sample, "sample_count": len(instants),
        "sample_times_hkt": [r["valid_time_utc"].astimezone(HKT).strftime("%H:%M") for r in instants],
        "source_ids": sorted({str(r["source_id"]) for r in used}),
    }


def absolute_error_bounds(lower, upper, observed):
    if lower > upper:
        raise ValueError("Inverted reconstruction envelope")
    return max(lower - observed, observed - upper, 0.0), max(abs(lower - observed), abs(upper - observed))


def select_issue(issues, cutoff):
    """Latest same-date bulletin known by both recorded issue/publish proxies."""
    eligible = [i for i in issues if i["bulletin_time_hkt"].date() == cutoff.astimezone(HKT).date()
                and i["bulletin_time_hkt"].replace(tzinfo=HKT).astimezone(UTC) <= cutoff
                and i["published_time_utc"] is not None and i["published_time_utc"] <= cutoff]
    if not eligible:
        raise ValueError("No HKO issue satisfies the predetermined cutoff")
    return max(eligible, key=lambda i: (i["bulletin_time_hkt"], i["forecast_issue_id"]))


def load_inputs():
    from psycopg.rows import dict_row
    with connect() as c:
        c.row_factory = dict_row
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        sources = c.execute("""
            SELECT source_id, model, product, run_time_utc, forecast_hour,
                   source_url, subset_relative_path, subset_sha256, subset_size_bytes,
                   manifest->'station_snapshot' AS station_snapshot,
                   manifest->>'availability_time_utc' AS availability_time_utc,
                   manifest->>'availability_note' AS availability_note
            FROM project.external_model_source WHERE model=%s AND run_time_utc=%s
            ORDER BY forecast_hour, source_id
        """, ("GFS", RUN)).fetchall()
        rows = c.execute("""
            SELECT t.*, s.forecast_hour FROM project.external_model_temperature t
            JOIN project.external_model_source s USING (source_id)
            WHERE s.model=%s AND s.run_time_utc=%s AND t.station_code=%s
            ORDER BY t.valid_time_utc, t.short_name, t.source_id
        """, ("GFS", RUN, "HKO")).fetchall()
        station = c.execute("""
            SELECT station_code, station_name, latitude, longitude, elevation_m
            FROM project.hko_station WHERE station_code=%s
        """, ("HKO",)).fetchone()
        issues = c.execute("""
            SELECT forecast_issue_id, bulletin_time_hkt, published_time_utc
            FROM project.hko_forecast_issue
            WHERE bulletin_time_hkt >= %s AND bulletin_time_hkt < %s
            ORDER BY bulletin_time_hkt, forecast_issue_id
        """, (date(2024, 1, 1), date(2024, 1, 2))).fetchall()
        forecasts = c.execute("""
            SELECT f.forecast_issue_id, f.valid_date, f.lead_days,
                   f.forecast_tmax_c::float8, f.forecast_tmin_c::float8
            FROM project.hko_forecast_daily f JOIN project.hko_forecast_issue i USING (forecast_issue_id)
            WHERE i.bulletin_time_hkt >= %s AND i.bulletin_time_hkt < %s
              AND f.valid_date >= %s AND f.valid_date < %s
            ORDER BY f.forecast_issue_id, f.valid_date
        """, (date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 9))).fetchall()
        observations = c.execute("""
            SELECT s.observation_series_id, s.series_code, s.source_file_id,
                   o.observation_date, o.value_numeric::float8, o.data_completeness
            FROM project.hko_daily_observation o
            JOIN project.hko_observation_series s USING (observation_series_id)
            WHERE s.series_code=ANY(%s) AND o.observation_date >= %s AND o.observation_date < %s
            ORDER BY s.series_code, o.observation_date
        """, (["obs_hko_daily_tmax", "obs_hko_daily_tmin"], date(2024, 1, 2), date(2024, 1, 9))).fetchall()
    if len(sources) != 65 or [s["forecast_hour"] for s in sources] != list(range(0, 193, 3)):
        raise ValueError("Pilot requires exactly one source at each three-hour step 0..192")
    if len(rows) != 193 or len({(r["source_id"], r["message_number"]) for r in rows}) != 193:
        raise ValueError("Unexpected extract count or duplicated source/message key")
    if len({(r["valid_time_utc"], r["short_name"]) for r in rows}) != len(rows):
        raise ValueError("Duplicated semantic forecast field")
    if Counter(r["short_name"] for r in rows) != {"2t": 65, "tmax": 64, "tmin": 64}:
        raise ValueError("Unexpected temperature field mix")
    if len({(r["grid_latitude"], r["grid_longitude"], r["extraction_method"]) for r in rows}) != 1:
        raise ValueError("Mixed spatial extraction")
    for r in rows:
        if (r["target_latitude"], r["target_longitude"]) != (station["latitude"], station["longitude"]):
            raise ValueError("Station snapshot differs from live station")
        if not math.isfinite(r["temperature_c"]) or not -90 < r["temperature_c"] < 65:
            raise ValueError("Invalid Celsius temperature")
        expected_step = {"2t": "instant", "tmax": "max", "tmin": "min"}[r["short_name"]]
        if r["step_type"] != expected_step or r["valid_time_utc"] != RUN + timedelta(hours=r["forecast_hour"]):
            raise ValueError("Invalid step metadata")
    return dict(sources=sources, rows=rows, station=station, issues=issues,
                forecasts=forecasts, observations=observations)


def audit_local_grib(inputs):
    """Verify hashes, re-decode all 193 station values, inspect packing metadata."""
    import eccodes as ec
    checks = 0
    packing_steps = []
    row_map = {(str(r["source_id"]), r["message_number"]): r for r in inputs["rows"]}
    max_difference = 0.0
    for source in inputs["sources"]:
        path = (DOWNLOADS / source["subset_relative_path"]).resolve()
        if not path.is_relative_to(DOWNLOADS.resolve()):
            raise ValueError("Unsafe source path")
        content = path.read_bytes()
        if len(content) != source["subset_size_bytes"] or hashlib.sha256(content).hexdigest() != source["subset_sha256"]:
            raise ValueError("Local GRIB differs from committed provenance")
        decoded = decode_temperature(content, source["station_snapshot"], RUN, source["forecast_hour"])
        for fresh in decoded:
            stored = row_map[(str(source["source_id"]), fresh["message_number"])]
            if fresh["short_name"] != stored["short_name"]:
                raise ValueError("Decoded variable differs from stored variable")
            for key in ("interval_start_utc", "valid_time_utc"):
                if datetime.fromisoformat(fresh[key]) != stored[key]:
                    raise ValueError("Decoded interval differs from stored interval")
            diff = abs(fresh["temperature_c"] - stored["temperature_c"])
            max_difference = max(max_difference, diff)
            if diff > 1e-9:
                raise ValueError("Re-decoded temperature differs from database")
            checks += 1
        with path.open("rb") as f:
            message_number = 0
            while (gid := ec.codes_grib_new_from_file(f)) is not None:
                try:
                    message_number += 1
                    step = 2.0 ** ec.codes_get(gid, "binaryScaleFactor") * 10.0 ** (-ec.codes_get(gid, "decimalScaleFactor"))
                    packing_steps.append(step)
                    row_map[(str(source["source_id"]), message_number)]["packing_step_c"] = step
                finally:
                    ec.codes_release(gid)
    if checks != 193 or max(packing_steps) > 0.1:
        raise ValueError("Unexpected decode count or packing coarser than pilot supports")
    worst_nesting = 0.0
    padded_violations = 0
    for a in inputs["rows"]:
        if a["short_name"] == "2t":
            continue
        for b in inputs["rows"]:
            if a is b or a["short_name"] != b["short_name"]:
                continue
            if b["interval_start_utc"] <= a["interval_start_utc"] and a["valid_time_utc"] <= b["valid_time_utc"]:
                violation = a["temperature_c"]-b["temperature_c"] if a["short_name"] == "tmax" else b["temperature_c"]-a["temperature_c"]
                worst_nesting = max(worst_nesting, violation)
                padded_violations += violation > max(PADDING_C, a["packing_step_c"])+max(PADDING_C, b["packing_step_c"])
    if padded_violations:
        raise ValueError("Nested extrema inconsistent beyond diagnostic packing allowance")
    return {"verified_files": len(inputs["sources"]), "verified_extracts": checks,
            "max_decode_difference_c": max_difference,
            "quantization_steps_c": sorted(set(packing_steps)),
            "quantization_step_counts": dict(Counter(map(str, packing_steps))),
            "padding_rule": "per message max(0.02 C, one GRIB quantization step)",
            "max_raw_nested_extremum_violation_c": worst_nesting,
            "nested_violations_after_padding": padded_violations,
            "padding_is_certified_error_bound": False}


def build_result(inputs, raw_audit):
    cutoff = datetime.combine(RUN.astimezone(HKT).date(), time(CUTOFF_HOUR_HKT), HKT).astimezone(UTC)
    issue = select_issue(inputs["issues"], cutoff)
    f_map = {(r["forecast_issue_id"], r["valid_date"]): r for r in inputs["forecasts"]}
    o_map = {(r["series_code"], r["observation_date"]): r for r in inputs["observations"]}
    if len(o_map) != len(inputs["observations"]):
        raise ValueError("Observation series join is not unique")
    cases = []
    for lead in range(1, 8):
        day = RUN.astimezone(HKT).date() + timedelta(days=lead)
        for var in ("tmax", "tmin"):
            d = daily_diagnostic(inputs["rows"], day, var)
            f = f_map.get((issue["forecast_issue_id"], day))
            o = o_map.get(("obs_hko_daily_" + var, day))
            if f is None or o is None or o["data_completeness"] != "C" or o["value_numeric"] is None:
                raise ValueError("Missing forecast/complete numeric observation; no silent case dropping")
            if f["lead_days"] != lead or f["forecast_" + var + "_c"] is None:
                raise ValueError("Unexpected lead or missing HKO endpoint")
            if d["outer_coverage_hours"] != 24 or d["sample_count"] != 8 or d["gfs_lower_c"] is None:
                raise ValueError("Incomplete daily pilot support")
            hko = f["forecast_" + var + "_c"]
            observed = o["value_numeric"]
            ae_low, ae_high = absolute_error_bounds(d["gfs_lower_c"], d["gfs_upper_c"], observed)
            cases.append(dict(
                benchmark_id=BENCHMARK_ID, valid_date=day, variable=var, station_code="HKO",
                gfs_run_time_utc=RUN, cutoff_utc=cutoff, lead_days=lead,
                forecast_issue_id=issue["forecast_issue_id"],
                hko_bulletin_time_hkt=issue["bulletin_time_hkt"],
                gfs_lead_hours_to_day_start=(d["window_start_utc"]-RUN).total_seconds()/3600,
                hko_lead_hours_to_day_start=(d["window_start_utc"]-issue["bulletin_time_hkt"].replace(tzinfo=HKT)).total_seconds()/3600,
                decision_lead_hours_to_day_start=(d["window_start_utc"]-cutoff).total_seconds()/3600,
                observation_series_id=o["observation_series_id"],
                observation_source_file_id=o["source_file_id"],
                observed_c=observed, hko_forecast_c=hko,
                hko_absolute_error_c=abs(hko-observed),
                gfs_ae_lower_c=ae_low, gfs_ae_upper_c=ae_high,
                delta_ae_lower_c=ae_low-abs(hko-observed),
                delta_ae_upper_c=ae_high-abs(hko-observed),
                gfs_availability_verified=False, primary_eligible=False,
                **d,
            ))
    summary = {}
    for var in ("tmax", "tmin"):
        group = [c for c in cases if c["variable"] == var]
        errors = [c["gfs_sampled_c"]-c["observed_c"] for c in group]
        h_errors = [c["hko_forecast_c"]-c["observed_c"] for c in group]
        summary[var] = dict(
            n=7, hko_mae_c=statistics.mean(map(abs, h_errors)),
            sampled_gfs_mae_c=statistics.mean(map(abs, errors)),
            sampled_gfs_rmse_c=math.sqrt(statistics.mean(e*e for e in errors)),
            sampled_gfs_bias_c=statistics.mean(errors),
            hko_rmse_c=math.sqrt(statistics.mean(e*e for e in h_errors)),
            hko_bias_c=statistics.mean(h_errors),
            gfs_mae_lower_c=statistics.mean(c["gfs_ae_lower_c"] for c in group),
            gfs_mae_upper_c=statistics.mean(c["gfs_ae_upper_c"] for c in group),
            delta_mae_lower_c=statistics.mean(c["delta_ae_lower_c"] for c in group),
            delta_mae_upper_c=statistics.mean(c["delta_ae_upper_c"] for c in group),
            max_temporal_envelope_width_c=max(c["gfs_upper_c"]-c["gfs_lower_c"] for c in group),
            sampled_value_outside_envelope=sum(not c["gfs_lower_c"] <= c["gfs_sampled_c"] <= c["gfs_upper_c"] for c in group),
        )
    cutoff_sensitivity = []
    for hour in (12, 16, 20):
        candidate_cutoff = cutoff.replace(hour=hour-8)
        selected = select_issue(inputs["issues"], candidate_cutoff)
        entry = {"cutoff_hkt": f"{hour:02}:00", "forecast_issue_id": selected["forecast_issue_id"],
                 "bulletin_time_hkt": selected["bulletin_time_hkt"],
                 "gfs_assumed_available_lag_hours": {str(lag): RUN+timedelta(hours=lag) <= candidate_cutoff for lag in (4, 6, 8, 12)},
                 "historical_availability_verified": False}
        for var in ("tmax", "tmin"):
            paired = [(f_map.get((selected["forecast_issue_id"], c["valid_date"])), c) for c in cases if c["variable"] == var]
            if any(f is None or f["forecast_"+var+"_c"] is None for f, _ in paired):
                entry[var+"_hko_mae_c"] = None
            else:
                entry[var+"_hko_mae_c"] = statistics.mean(abs(f["forecast_"+var+"_c"]-c["observed_c"]) for f, c in paired)
        cutoff_sensitivity.append(entry)
    durations = Counter(f'{r["short_name"]}:{(r["valid_time_utc"]-r["interval_start_utc"]).total_seconds()/3600:g}h' for r in inputs["rows"])
    return dict(
        benchmark_id=BENCHMARK_ID, input_sha256=digest(inputs),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        computed_at_utc=datetime.now(UTC), status="diagnostic_only_not_a_ranking",
        source_count=len(inputs["sources"]), extract_count=len(inputs["rows"]), independent_run_count=1,
        original_grib_bytes=sum(s["subset_size_bytes"] for s in inputs["sources"]),
        new_weather_download_bytes=0, station=inputs["station"],
        grid={k: inputs["rows"][0][k] for k in ("grid_latitude", "grid_longitude", "grid_distance_km", "extraction_method")},
        interval_counts=dict(durations), raw_audit=raw_audit,
        config={"cutoff_hkt": "20:00", "gfs_cycle_utc": "00:00", "run_selection": "fixed existing pilot; not latest of all available cycles",
                "padding_rule": raw_audit["padding_rule"], "observation_completeness": "C", "delta_sign": "GFS absolute error minus HKO absolute error; negative favors GFS",
                "hko_availability_basis": "bulletin and RSS publication timestamps; proxies, not captured delivery logs",
                "gfs_availability_basis": "unknown; lag scenarios are assumptions only"},
        primary_eligible_cases=0, exact_time_tiled_cases=sum(c["exact_window_tiling"] for c in cases),
        summary=summary, cutoff_sensitivity=cutoff_sensitivity, cases=cases,
        source_provenance=[{k: s[k] for k in ("source_id", "source_url", "subset_sha256", "forecast_hour")} for s in inputs["sources"]],
        blockers=["HKT midnight is UTC16, outside three/six-hour boundaries; inner intervals cover only part of each day",
                  "GFS historical per-file availability unknown; fixed cycle also does not prove latest-available operational selection",
                  "One January run cannot estimate seasonal skill or sampling confidence intervals",
                  "Nearest grid point is not the HKO station; land/sea mask and model orography not yet checked"],
    )


DDL = """
CREATE TABLE IF NOT EXISTS project.benchmark_gfs_pilot_case (
    benchmark_id text NOT NULL,
    valid_date date NOT NULL,
    variable text NOT NULL CHECK (variable IN ('tmax','tmin')),
    station_code text NOT NULL REFERENCES project.hko_station(station_code),
    gfs_run_time_utc timestamptz NOT NULL,
    cutoff_utc timestamptz NOT NULL,
    lead_days integer NOT NULL CHECK (lead_days BETWEEN 1 AND 7),
    forecast_issue_id bigint NOT NULL,
    observation_series_id bigint NOT NULL,
    window_start_utc timestamptz NOT NULL,
    window_end_utc timestamptz NOT NULL,
    inner_coverage_hours double precision NOT NULL CHECK (inner_coverage_hours BETWEEN 0 AND 24),
    outer_coverage_hours double precision NOT NULL CHECK (outer_coverage_hours = 24),
    gfs_lower_c double precision NOT NULL,
    gfs_upper_c double precision NOT NULL,
    gfs_sampled_c double precision NOT NULL,
    hko_forecast_c double precision NOT NULL,
    observed_c double precision NOT NULL,
    source_ids uuid[] NOT NULL CHECK (cardinality(source_ids) > 0),
    gfs_availability_verified boolean NOT NULL CHECK (NOT gfs_availability_verified),
    primary_eligible boolean NOT NULL CHECK (NOT primary_eligible),
    input_sha256 text NOT NULL CHECK (length(input_sha256) = 64),
    diagnostics jsonb NOT NULL,
    computed_at_utc timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (benchmark_id, valid_date, variable, station_code),
    FOREIGN KEY (forecast_issue_id, valid_date)
        REFERENCES project.hko_forecast_daily(forecast_issue_id, valid_date),
    FOREIGN KEY (observation_series_id, valid_date)
        REFERENCES project.hko_daily_observation(observation_series_id, observation_date),
    CHECK (gfs_lower_c <= gfs_upper_c),
    CHECK (window_end_utc - window_start_utc = interval '24 hours'),
    CHECK (gfs_run_time_utc <= cutoff_utc AND cutoff_utc < window_start_utc)
);
"""


def persist(result):
    """One atomic, idempotent derived-data commit; never alters source tables."""
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from uuid import UUID
    columns = ("benchmark_id", "valid_date", "variable", "station_code", "gfs_run_time_utc",
               "cutoff_utc", "lead_days", "forecast_issue_id", "observation_series_id",
               "window_start_utc", "window_end_utc", "inner_coverage_hours", "outer_coverage_hours",
               "gfs_lower_c", "gfs_upper_c", "gfs_sampled_c", "hko_forecast_c", "observed_c",
               "source_ids", "gfs_availability_verified", "primary_eligible", "input_sha256", "diagnostics")
    query = sql.SQL("INSERT INTO project.benchmark_gfs_pilot_case ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
        sql.SQL(",").join(map(sql.Identifier, columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in columns))
    with connect(read_only=False) as c:
        c.execute(DDL)
        old = c.execute("SELECT DISTINCT input_sha256 FROM project.benchmark_gfs_pilot_case WHERE benchmark_id=%s", (BENCHMARK_ID,)).fetchall()
        if old and old != [(result["input_sha256"],)]:
            raise ValueError("Inputs changed: use a new benchmark version, do not overwrite pilot history")
        for case in result["cases"]:
            row = dict(case, input_sha256=result["input_sha256"])
            row["source_ids"] = [UUID(s) for s in case["source_ids"]]
            diagnostic = json_ready({"case": case, "config": result["config"], "raw_audit": result["raw_audit"],
                                     "implementation_sha256": result["implementation_sha256"]})
            row["diagnostics"] = Jsonb(diagnostic)
            c.execute(query, [row[key] for key in columns])
            stored = c.execute("""
                SELECT diagnostics FROM project.benchmark_gfs_pilot_case
                WHERE benchmark_id=%s AND valid_date=%s AND variable=%s AND station_code=%s
            """, (BENCHMARK_ID, case["valid_date"], case["variable"], "HKO")).fetchone()[0]
            if stored != diagnostic:
                raise ValueError("Stored method/results differ; use a new benchmark version")
        count = c.execute("SELECT count(*) FROM project.benchmark_gfs_pilot_case WHERE benchmark_id=%s", (BENCHMARK_ID,)).fetchone()[0]
        if count != 14:
            raise ValueError("Expected 14 committed pilot cases; transaction rolled back")
    # Deliberately outside the writing transaction: inspect committed state.
    try:
        refresh_schema_document()
    except Exception as exc:
        raise RuntimeError("COMMITTED: 14 derived pilot cases. Documentation refresh FAILED; the guide is stale and must be refreshed before completion.") from exc
    with connect() as c:
        verified = c.execute("""
            SELECT count(*), count(*) FILTER (WHERE primary_eligible),
                   count(DISTINCT input_sha256)
            FROM project.benchmark_gfs_pilot_case WHERE benchmark_id=%s
        """, (BENCHMARK_ID,)).fetchone()
        if verified != (14, 0, 1):
            raise RuntimeError("Committed pilot verification failed")
    return {"committed_cases": 14, "primary_eligible_cases": 0, "schema_guide_refreshed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    inputs = load_inputs()
    print("Read-only snapshot: 65 GFS sources, 193 extracts; checking existing local GRIB files.", flush=True)
    result = build_result(inputs, audit_local_grib(inputs))
    result["database_write"] = persist(result) if args.persist else {"performed": False}
    output = Path(__file__).with_name("pilot_results.json")
    output.write_text(json.dumps(json_ready(result), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(json_ready({k: result[k] for k in ("status", "source_count", "extract_count", "raw_audit", "primary_eligible_cases", "exact_time_tiled_cases", "summary", "cutoff_sensitivity", "database_write")}), indent=2))
    print("Saved benchmark/pilot_results.json. No weather data downloaded.")


if __name__ == "__main__":
    main()
