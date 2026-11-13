"""Audit committed GFS 2025 HKO extracts independently of importer status.

Read-only SQL checks the complete Cartesian run/lead schedule and field records.
Every source identity and decoded-row digest is checked, and a small monthly
sample is downloaded again from NOAA to compare its bytes and station values.
The output is a compact verification receipt, not another schema document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import uuid
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import manage_gfs as manager

UTC = timezone.utc
START = datetime(2024, 12, 24, tzinfo=UTC)
END = datetime(2026, 1, 1, tzinfo=UTC)


def canonical_row(row):
    return {key: value.astimezone(UTC).isoformat() if isinstance(value, datetime) else value
            for key, value in row.items()}


def verify(online=True):
    checks = {}
    receipt = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "scope": {"run_start_utc": START.isoformat(), "run_end_exclusive_utc": END.isoformat(),
                  "cycles_utc": [0, 6, 12, 18], "forecast_hours": "0:192:3", "station": "HKO"},
        "checks": checks,
    }
    samples = []
    with manager.connect(read_only=True) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        checks["read_only_session"] = conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        station_record = conn.execute("SELECT station_code,station_name,latitude,longitude "
                                      "FROM project.hko_station WHERE station_code='HKO'").fetchone()
        station = dict(zip(('station_code','station_name','latitude','longitude'), station_record))
        # Generate the expected Cartesian schedule in SQL, independently of the
        # importer's Python task generator and its local status file.
        row = conn.execute("""
            WITH expected AS (
                SELECT run_time,lead
                FROM generate_series(%s::timestamptz,%s::timestamptz - INTERVAL '6 hours',
                                     INTERVAL '6 hours') run_time
                CROSS JOIN generate_series(0,192,3) lead
            ), actual AS (
                SELECT run_time_utc,forecast_hour,count(*) AS copies
                FROM project.external_model_source
                WHERE model='GFS' AND product='pgrb2.0p25'
                  AND run_time_utc >= %s AND run_time_utc < %s
                GROUP BY run_time_utc,forecast_hour
            )
            SELECT count(*) FILTER(WHERE e.run_time IS NOT NULL),
                   count(*) FILTER(WHERE e.run_time IS NOT NULL AND a.run_time_utc IS NULL),
                   count(*) FILTER(WHERE e.run_time IS NULL),
                   count(*) FILTER(WHERE a.copies<>1)
            FROM expected e FULL JOIN actual a
              ON a.run_time_utc=e.run_time AND a.forecast_hour=e.lead
        """, (START, END, START, END)).fetchone()
        receipt["schedule"] = dict(zip(("expected_sources", "missing_sources", "unexpected_slots", "duplicate_slots"), row))
        checks["complete_unique_schedule"] = row == (96980, 0, 0, 0)
        cur = conn.execute("""
            SELECT CASE WHEN s.run_time_utc >= TIMESTAMPTZ '2025-01-01 00:00:00+00'
                        THEN '2025' ELSE '2024_buffer' END AS period,
                   count(DISTINCT s.run_time_utc),count(DISTINCT s.source_id),count(t.source_id)
            FROM project.external_model_source s
            LEFT JOIN project.external_model_temperature t
                   ON t.source_id=s.source_id AND t.station_code='HKO'
            WHERE s.model='GFS' AND s.product='pgrb2.0p25'
              AND s.run_time_utc >= %s AND s.run_time_utc < %s
            GROUP BY 1 ORDER BY 1
        """, (START, END))
        receipt["inventory"] = {period: {"runs": runs, "source_subsets": sources, "temperature_rows": values}
                                for period, runs, sources, values in cur.fetchall()}
        checks["year_and_buffer_counts"] = receipt["inventory"] == {
            "2024_buffer": {"runs": 32, "source_subsets": 2080, "temperature_rows": 6176},
            "2025": {"runs": 1460, "source_subsets": 94900, "temperature_rows": 281780},
        }
        columns = conn.execute("""
            SELECT table_name,column_name,data_type,is_nullable
            FROM information_schema.columns WHERE table_schema='project'
              AND table_name IN ('external_model_source','external_model_temperature')
            ORDER BY table_name,ordinal_position
        """).fetchall()
        receipt["live_catalog_columns_checked"] = len(columns)
        checks["required_live_columns"] = set(manager.VALUE_COLUMNS) <= {
            name for table, name, _, _ in columns if table == 'external_model_temperature'}
        # Server-side iteration keeps verification memory bounded. Source
        # manifests are visited once; the much smaller station rows separately.
        source_errors = 0
        source_count = 0
        byte_total = 0
        with conn.cursor(name="gfs_source_audit") as cur:
            cur.itersize = 500
            cur.execute("""
                SELECT source_id,source_url,subset_sha256,subset_size_bytes,run_time_utc,
                       forecast_hour,manifest
                FROM project.external_model_source
                WHERE model='GFS' AND product='pgrb2.0p25'
                  AND run_time_utc >= %s AND run_time_utc < %s
                ORDER BY source_id
            """, (START, END))
            for source_id, url, digest, size, run, hour, manifest in cur:
                source_count += 1
                byte_total += size
                utc_run = run.astimezone(UTC)
                expected_url = (f"{manager.BASE_URL}/gfs.{run.astimezone(UTC):%Y%m%d}/"
                                f"{run.astimezone(UTC).hour:02d}/atmos/"
                                f"gfs.t{run.astimezone(UTC).hour:02d}z.pgrb2.0p25.f{hour:03d}")
                source_ok = (url == expected_url and size > 0 and len(digest) == 64
                             and all(c in '0123456789abcdef' for c in digest)
                             and source_id == uuid.uuid5(uuid.NAMESPACE_URL, url + '#' + digest)
                             and manifest.get('source_id') == str(source_id)
                             and manifest.get('source_url') == url
                             and manifest.get('subset_sha256') == digest
                             and manifest.get('subset_size_bytes') == size
                             and manifest.get('forecast_hour') == hour
                             and manifest.get('station_snapshot') == [station]
                             and manifest.get('requested_fields') == ['TMAX','TMIN','TMP']
                             and datetime.fromisoformat(manifest['run_time_utc']) == run
                             and manifest.get('raw_subset_retained') is False
                             and manifest.get('storage_mode') == 'station_extract_only'
                             and len(manifest.get('grib_message_metadata', [])) == (1 if hour == 0 else 3))
                source_errors += not source_ok
                # One case per month; cycles and leads deliberately vary.
                month = utc_run.month
                if (utc_run.year == 2025 and utc_run.day == 15
                        and utc_run.hour == ((month-1) % 4)*6
                        and hour == [0, 3, 96, 192][(month-1) % 4]):
                    samples.append(manifest)
        receipt["source_audit"] = {"checked": source_count, "invalid": source_errors,
                                   "original_subset_bytes": byte_total}
        checks["source_provenance_consistent"] = source_count == 96980 and source_errors == 0
        row_count = digest_count = invalid_rows = invalid_groups = digest_errors = 0
        sql = """SELECT t.source_id,s.run_time_utc,s.forecast_hour,
                        s.manifest->>'decoded_rows_sha256' AS row_digest,""" + ",".join(
                            "t." + col for col in manager.VALUE_COLUMNS) + """
                 FROM project.external_model_temperature t
                 JOIN project.external_model_source s USING(source_id)
                 WHERE s.model='GFS' AND s.product='pgrb2.0p25' AND t.station_code='HKO'
                   AND s.run_time_utc >= %s AND s.run_time_utc < %s
                 ORDER BY t.source_id,t.message_number"""
        with conn.cursor(name="gfs_row_audit") as cur:
            cur.itersize = 2000
            cur.execute(sql, (START, END))
            for _, group in groupby(cur, key=lambda row: row[0]):
                records = list(group)
                decoded = []
                for record in records:
                    _, run, hour, stored_digest, *values = record
                    row = dict(zip(manager.VALUE_COLUMNS, values))
                    row_count += 1
                    valid = (math.isfinite(row['temperature_c']) and -100 < row['temperature_c'] < 70
                             and row['valid_time_utc'] == run + timedelta(hours=hour)
                             and run <= row['interval_start_utc'] <= row['valid_time_utc']
                             and row['extraction_method'] == 'nearest_grid_point'
                             and row['target_latitude'] == station['latitude']
                             and row['target_longitude'] == station['longitude']
                             and -90 <= row['grid_latitude'] <= 90
                             and -180 <= row['grid_longitude'] <= 180
                             and 0 <= row['grid_distance_km'] < 100
                             and row['source_unit'] == 'K'
                             and abs(row['temperature_c']-(row['source_value']-273.15)) < 1e-12
                             and ((row['step_type']=='instant' and row['parameter_id']==167 and row['short_name']=='2t'
                                   and row['interval_start_utc']==row['valid_time_utc'])
                                  or (row['step_type']=='max' and row['short_name']=='tmax' and row['parameter_id']==3015
                                      and row['interval_start_utc']<row['valid_time_utc'])
                                  or (row['step_type']=='min' and row['short_name']=='tmin' and row['parameter_id']==3016
                                      and row['interval_start_utc']<row['valid_time_utc'])))
                    invalid_rows += not valid
                    decoded.append(canonical_row(row))
                expected_steps = ['instant'] if records[0][2] == 0 else ['instant', 'max', 'min']
                invalid_groups += sorted(r['step_type'] for r in decoded) != expected_steps
                digest = hashlib.sha256(json.dumps(decoded, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                digest_errors += digest != records[0][3]
                digest_count += 1
        receipt["station_audit"] = {"rows_checked": row_count, "invalid_rows": invalid_rows,
                                    "sources_checked": digest_count, "invalid_field_groups": invalid_groups,
                                    "decoded_digest_mismatches": digest_errors}
        checks["all_station_fields_valid"] = (row_count == 287956 and digest_count == 96980
                                              and invalid_rows == invalid_groups == digest_errors == 0)
        receipt["table_storage_bytes"] = dict(conn.execute("""
            SELECT relname,pg_total_relation_size(oid) FROM pg_class
            WHERE relnamespace='project'::regnamespace
              AND relname IN ('external_model_source','external_model_temperature')
        """).fetchall())
        receipt["online_samples"] = []
        if online:
            import requests
            with requests.Session() as http:
                for manifest in sorted(samples, key=lambda m: m['run_time_utc']):
                    content = manager.get_grib_subset(http, manifest['source_url'],
                                                     [(a,b,'') for a,b in manifest['byte_ranges']])
                    digest_ok = hashlib.sha256(content).hexdigest() == manifest['subset_sha256']
                    rows = manager.decode_temperature(content, manifest['station_snapshot'],
                                                      datetime.fromisoformat(manifest['run_time_utc']),
                                                      manifest['forecast_hour'])
                    rows_digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    receipt['online_samples'].append({
                        'run_time_utc': manifest['run_time_utc'], 'forecast_hour': manifest['forecast_hour'],
                        'raw_sha256_matches': digest_ok,
                        'decoded_rows_match': rows_digest == manifest['decoded_rows_sha256'],
                    })
            checks['noaa_monthly_sample_redownloads_match'] = len(samples) == 12 and all(
                r['raw_sha256_matches'] and r['decoded_rows_match'] for r in receipt['online_samples'])
        else:
            receipt['online_samples_skipped'] = True
    receipt['passed'] = all(checks.values())
    receipt['limits'] = ('Full committed schedule, provenance identities, field validity and decoded-row hashes checked. '
                        'External raw-byte verification is a 12-file monthly sample, not a re-download of every source. '
                        'Global raw fields are not retained; this does not validate exact HKT daily extrema, '
                        'other stations, historical publication times or forecast skill.')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Skip NOAA requests; still reads the live database')
    parser.add_argument('--output', type=Path, default=manager.HERE/'results'/'gfs_2025_verification.json')
    args = parser.parse_args()
    try:
        receipt = verify(not args.offline)
    except Exception as exc:
        # Never print arbitrary database/HTTP exceptions or connection values.
        print('GFS audit failed (' + type(exc).__name__ + '). No database changes were made.', file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
