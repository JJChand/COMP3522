"""Scoped RH availability audit: live DB plus optional importer metadata only.

No downloads, raw observation exports, database writes or scope substitutions.
"""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.database import connect
from common.task1 import START,END,load_snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staging-series',type=Path,
                        help='Optional importer observation_series.csv metadata, not raw observations')
    parser.add_argument('--inspect-sample',action='store_true',help='Print three public report RH/date values for field inspection')
    args=parser.parse_args()
    here=Path(__file__).resolve().parent
    sql=(here/'rh_feasibility_query.sql').read_text(encoding='utf-8')
    with connect() as db,db.cursor() as cur:
        cur.execute('SHOW transaction_read_only')
        if cur.fetchone()[0]!='on':
            raise ValueError('Refusing non-read-only session')
        cur.execute(sql,{'start':START,'end':END})
        evidence=cur.fetchone()[0]
        from psycopg.rows import dict_row
        cur.row_factory=dict_row
        notes_sql=(here/'rh_notes_query.sql').read_text(encoding='utf-8')
        cur.execute(notes_sql,{'start':START,'end':END})
        evidence['measurement_notes']=cur.fetchall()
        evidence['notes_query_sha256']=hashlib.sha256(notes_sql.encode()).hexdigest()
        if args.inspect_sample:
            from psycopg.rows import dict_row
            cur.row_factory=dict_row
            report_sql=(here.parent/'common/rh_report_query.sql').read_text(encoding='utf-8')
            cur.execute(report_sql,{'start':START,'end':END})
            rows=cur.fetchall()
            for r in rows[:3]:
                print({k:r[k] for k in ('report_date','bulletin_date','bulletin_time','source_observation_date',
                                       'observed_rh_min_text','observed_rh_max_text','observed_tmin_text','observed_tmax_text','source_note')})
    evidence.update(checked_at_utc=datetime.now(timezone.utc).isoformat(),database_modified=False,
                    start_inclusive=str(START),end_exclusive=str(END),
                    query_sha256=hashlib.sha256(sql.encode()).hexdigest())
    if args.staging_series:
        with args.staging_series.open(encoding='utf-8-sig',newline='') as f:
            metadata=list(csv.DictReader(f))
        candidates=[r for r in metadata if 'humidity' in r.get('title_en','').lower()]
        evidence['staging_catalog']=dict(path=str(args.staging_series.resolve()),series_count=len(metadata),
            humidity_series=candidates,sha256=hashlib.sha256(args.staging_series.read_bytes()).hexdigest())
    comparable=[r for r in evidence['humidity_series'] if any(word in r['metric_name'].lower() for word in ('minimum','maximum'))]
    evidence['extrema_series_candidates']=comparable
    snapshot=load_snapshot()
    evidence['validated_json_extrema']=snapshot.meta['rh_report_validation']
    evidence['rh_report_rows_sha256']=snapshot.meta['rh_report_rows_sha256']
    evidence['scoring_status']='validated_daily_report_extrema_available' if evidence['validated_json_extrema']['n_valid_dates'] else 'no_valid_daily_report_extrema'
    out=here/'results/rh_source_audit.json'
    out.write_text(json.dumps(evidence,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    print('RH availability audit:',out)
    print('Catalog series:',evidence['observation_catalog_series_count'])
    print('Humidity series:',len(evidence['humidity_series']))
    print('Report dates:',evidence['distinct_report_dates'])
    print('RH candidate report fields:',len(evidence['humidity_candidate_report_fields']))
    print('Status:',evidence['scoring_status'])


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        if type(exc).__module__.startswith('psycopg'):
            print('Database read failed; check root .env and access. Raw details withheld.',file=sys.stderr)
        else:
            print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        raise SystemExit(1)
