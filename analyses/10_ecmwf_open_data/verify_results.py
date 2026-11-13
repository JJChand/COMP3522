"""Recompute consequential outputs independently; no network or DB connection.

Checks raw-message hashes and ecCodes nearest-one extraction against the saved
nearest-four result. Reconstructs each daily range with independent hour-cell
coverage, verifies paired-error arithmetic and makes a non-writing DB payload
preview from the inspected live-column contract. This is not full independent
validation of forecast skill or historical publication availability.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import uuid

import eccodes as ec

from run_investigation import HERE, ROOT, write_json


def run():
    results=HERE/"results"
    meta=json.loads((results/"run_metadata.json").read_text(encoding="utf-8"))
    rows=json.loads((results/"pilot_temperature_extracts.json").read_text(encoding="utf-8"))
    cases=json.loads((results/"daily_reconstruction_cases.json").read_text(encoding="utf-8"))
    anchors=json.loads((results/"historical_index_audit.json").read_text(encoding="utf-8"))
    db=json.loads((results/"database_check.json").read_text(encoding="utf-8"))
    checks=[]
    def check(name,condition,detail=None):
        checks.append(dict(check=name,passed=bool(condition),detail=detail))
    check("historical_anchor_keys_unique",len({(r["run_date"],r["forecast_hour"]) for r in anchors})==len(anchors))
    check("all_requested_anchor_indexes_available",all(r["status"]=="ok" for r in anchors),len(anchors))
    check("database_transaction_read_only",db.get("transaction_read_only")=="on" and not db["database_write"])
    check("no_primary_benchmark_claim",all(not c["primary_eligible"] and not c["availability_verified"] for c in cases))
    files_by_sha={}
    for sidecar in (HERE/"cache/grib").rglob("*.grib2.json"):
        receipt=json.loads(sidecar.read_text(encoding="utf-8"))
        raw=Path(str(sidecar).removesuffix(".json"))
        data=raw.read_bytes()
        check("raw_sha256:"+str(raw.relative_to(HERE)),hashlib.sha256(data).hexdigest()==receipt["sha256"])
        files_by_sha[receipt["sha256"]]=(raw,receipt)
    previews=[]
    for row in rows:
        raw,receipt=files_by_sha[row["sha256"]]
        data=raw.read_bytes()
        gid=ec.codes_new_from_message(data)
        try:
            point=ec.codes_grib_find_nearest(gid,row["target_latitude"],row["target_longitude"],npoints=1)[0]
            name=row["run_date"]+"/"+str(row["forecast_hour"])+"/"+row["native_short_name"]
            check("independent_point_extract:"+name,abs(float(point["value"])-273.15-row["temperature_c"])<1e-9)
            check("native_parameter_retained:"+name,ec.codes_get(gid,"shortName")==row["native_short_name"])
            check("actual_global_grid:"+name,ec.codes_get(gid,"numberOfDataPoints")>400_000)
        finally:
            ec.codes_release(gid)
        source_id=str(uuid.uuid5(uuid.NAMESPACE_URL,row["source_url"]+"#sha256="+row["sha256"]))
        source=dict(source_id=source_id,provider="ECMWF",model="IFS",product="oper_fc_public_global_temperature_field",
                    run_time_utc=row["run_date"]+"T00:00:00+00:00",forecast_hour=row["forecast_hour"],
                    source_url=row["source_url"],index_url=row["source_url"].removesuffix(".grib2")+".index",
                    retrieved_at_utc=row["retrieved_at_utc"],subset_relative_path=raw.relative_to(ROOT).as_posix(),
                    subset_sha256=row["sha256"],subset_size_bytes=len(data),
                    manifest=dict(archive_root="repository_root",native_short_name=row["native_short_name"],
                                  byte_range=receipt["byte_range"],grid_increment_degrees=row["grid_increment_degrees"],
                                  historical_available_time_utc=None,source_fingerprint=row["source_id"],
                                  status="preview only; no INSERT executed"))
        temperature={k:row[k] for k in ("station_code","parameter_id","parameter_name","step_type","interval_start_utc","valid_time_utc",
                         "target_latitude","target_longitude","grid_latitude","grid_longitude","grid_distance_km",
                         "extraction_method","source_value","source_unit","temperature_c")}
        temperature.update(source_id=source_id,message_number=1,short_name=row["native_short_name"])
        previews.append(dict(source=source,temperature=temperature))
    columns={table:{c["column_name"] for c in db["columns"] if c["table_name"]==table} for table in ("external_model_source","external_model_temperature")}
    check("source_payload_columns_exist",all(set(p["source"])<=columns["external_model_source"] for p in previews))
    check("temperature_payload_columns_exist",all(set(p["temperature"])<=columns["external_model_temperature"] for p in previews))
    check("payload_uuid_and_unique_source_keys",len({p["source"]["source_id"] for p in previews})==len(previews) and all(uuid.UUID(p["source"]["source_id"]) for p in previews))
    check("native_short_name_column_is_text",any(c["table_name"]=="external_model_temperature" and c["column_name"]=="short_name" and c["data_type"]=="text" for c in db["columns"]))
    check("payload_interval_constraint",all(p["temperature"]["interval_start_utc"]<=p["temperature"]["valid_time_utc"] for p in previews))
    for case in cases:
        day=datetime.fromisoformat(case["valid_date"]).replace(tzinfo=timezone(timedelta(hours=8)))
        start=day.astimezone(timezone.utc)
        end=start+timedelta(days=1)
        check("24h_hkt_window:"+case["valid_date"]+case["variable"],
              start==datetime.fromisoformat(case["window_start_utc"]) and
              end==datetime.fromisoformat(case["window_end_utc"]) and
              (end-start).total_seconds()==86400)
        group=[r for r in rows if r["run_date"]==case["run_date"] and r["short_name"]==case["variable"]]
        outer=[r for r in group if datetime.fromisoformat(r["interval_start_utc"])<end and datetime.fromisoformat(r["valid_time_utc"])>start]
        inner=[r for r in outer if datetime.fromisoformat(r["interval_start_utc"])>=start and datetime.fromisoformat(r["valid_time_utc"])<=end]
        def hours_covered(records):
            return sum(any(datetime.fromisoformat(r["interval_start_utc"])<=start+timedelta(hours=h) and
                           datetime.fromisoformat(r["valid_time_utc"])>=start+timedelta(hours=h+1) for r in records) for h in range(24))
        check("independent_hour_cell_coverage:"+case["run_date"]+case["valid_date"]+case["variable"],
              hours_covered(inner)==case["inner_coverage_hours"] and hours_covered(outer)==case["outer_coverage_hours"])
        if case["interval_lower_c"] is None:
            check("no_invented_interval_extrema:"+case["run_date"]+case["valid_date"],not inner or hours_covered(outer)<24)
            continue
        pad=lambda r:max(.02,r["packing_step_c"])
        if case["variable"]=="tmax":
            low=max(r["temperature_c"]-pad(r) for r in inner)
            high=max(r["temperature_c"]+pad(r) for r in outer)
        else:
            low=min(r["temperature_c"]-pad(r) for r in outer)
            high=min(r["temperature_c"]+pad(r) for r in inner)
        check("independent_endpoint_range:"+case["valid_date"]+case["variable"],
              abs(low-case["interval_lower_c"])<1e-9 and abs(high-case["interval_upper_c"])<1e-9)
        midpoint=(low+high)/2
        check("midpoint_arithmetic:"+case["valid_date"]+case["variable"],abs(midpoint-case["interval_midpoint_c"])<1e-9)
        if case["observed_c"] is not None:
            delta=abs(midpoint-case["observed_c"])-abs(case["hko_forecast_c"]-case["observed_c"])
            check("paired_error_arithmetic:"+case["valid_date"]+case["variable"],abs(delta-case["paired_absolute_error_difference_c"])<1e-9)
            check("error_difference_within_reconstruction_bounds:"+case["valid_date"]+case["variable"],case["paired_difference_lower_c"]-1e-9<=delta<=case["paired_difference_upper_c"]+1e-9)
    import_preview=dict(status="offline payload preview; NOT IMPORTED",database_write=False,
                        source_grain="one downloaded single-field GRIB subset, not necessarily one source per forecast lead",
                        existing_schema_reference="../../DATABASE_AGENT_GUIDE.md",records=previews)
    write_json(results/"import_payload_preview.json",import_preview)
    receipt=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),passed=all(c["passed"] for c in checks),
                 checks=len(checks),failed_checks=[c for c in checks if not c["passed"]],
                 scope="raw field integrity, nearest-point decode, independent temporal reconstruction/error arithmetic and offline column compatibility",
                 not_verified=["forecast skill beyond two fixed runs","per-file historical publication availability","all leads of all 2024–2025 runs","transactional IFS database import"],
                 schema_compatible_without_new_columns=all(c["passed"] for c in checks if c["check"] in ("source_payload_columns_exist","temperature_payload_columns_exist","native_short_name_column_is_text")),
                 source_quality_status="Proxy use only: native cross-field consistency warnings remain",
                 native_inconsistencies_beyond_numerical_allowance=meta["consistency"]["endpoint_violations_after_disclosed_padding"],
                 certified_daily_bounds=False,
                 components=checks)
    write_json(results/"verification.json",receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!="components"},indent=2))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__=="__main__": run()
