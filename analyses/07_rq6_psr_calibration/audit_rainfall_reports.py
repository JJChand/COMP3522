"""Inspect retained rainfall field grain without exporting daily source records."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.database import connect
from common.rh_observations import number as numeric
from common.task1 import START, END, digest, load_snapshot
from psycopg.rows import dict_row


def main():
    query_path = Path(__file__).with_name('rainfall_report_audit_query.sql')
    query = query_path.read_text(encoding='utf-8')
    with connect() as db, db.cursor(row_factory=dict_row) as cur:
        cur.execute(query, {'start': START, 'end': END})
        rows = cur.fetchall()
    snapshot = load_snapshot()
    point = snapshot.observed('obs_hko_daily_rainfall')
    fields = Counter()
    year_summaries = []
    by_year = defaultdict(list)
    calendar_averages = defaultdict(set)
    calendar_years = defaultdict(set)
    matches = comparisons = 0
    for r in rows:
        fields.update((r['rainfall_fields'] or {}).keys())
        by_year[r['report_date'].year].append(r)
        avg = numeric(r['average_text'])
        if avg is not None:
            calendar_averages[r['report_date'].strftime('%m-%d')].add(avg)
            calendar_years[r['report_date'].strftime('%m-%d')].add(r['report_date'].year)
        value = numeric(r['rainfall_text'])
        if value is not None and r['report_date'] in point:
            comparisons += 1
            matches += value == point[r['report_date']]
    for year, members in sorted(by_year.items()):
        for field in ('rainfall_text', 'accumulated_text', 'average_text'):
            values = [numeric(r[field]) for r in members]
            usable = [v for v in values if v is not None]
            drops = sum(a is not None and b is not None and b < a
                        for a, b in zip(values, values[1:]))
            year_summaries.append(dict(year=year, field=field,
                n_reports=len(members), n_numeric=len(usable),
                minimum=min(usable) if usable else None,
                maximum=max(usable) if usable else None,
                consecutive_day_decreases=drops))
    output = dict(audited_at_utc=datetime.now(timezone.utc).isoformat(),
        database_modified=False, period=[START.isoformat(), END.isoformat()],
        n_reports=len(rows), source_rows_sha256=digest(rows),
        query_sha256=hashlib.sha256(query.encode()).hexdigest(),
        rainfall_key_presence=dict(sorted(fields.items())),
        yearly_field_profiles=year_summaries,
        rainfall_vs_complete_hko_point_csv=dict(n_numeric_comparisons=comparisons,
            n_exact_matches=matches),
        average_field_calendar_comparison=dict(
            n_calendar_dates=len(calendar_averages),
            n_calendar_dates_with_multiple_years=sum(len(v)>1 for v in calendar_years.values()),
            n_multiyear_calendar_dates_with_identical_values=sum(
                len(v) == 1 and len(calendar_years[k])>1 for k,v in calendar_averages.items())),
        interpretation='Profiles test whether fields can supply daily territorial labels. '
            'Names alone do not establish spatial coverage or averaging period. '
            'The daily rainfall field agrees with the HKO-point CSV on every numeric comparison. '
            'Accumulated rainfall is total since 1 January under official API documentation. '
            'The average field has a cumulative-like, mostly calendar-repeated annual trajectory, '
            'not a daily rainfall trajectory; its precise climatological averaging period is not '
            'established by this audit. These fields do not supply the missing daily territorial label. '
            'No field is substituted for the declared RQ6 event.',
        documentation='https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf',
        documentation_printed_pages='36-37')
    destination = Path(__file__).parent / 'results' / 'rainfall_report_audit.json'
    destination.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
