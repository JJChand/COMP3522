"""Reconcile every scope/variable/lead aggregate against independent read-only SQL."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.database import connect


def main():
    result_dir = HERE / 'results'
    meta = json.loads((result_dir / 'run_metadata.json').read_text(encoding='utf-8'))
    with (result_dir / 'revision_by_lead.csv').open(encoding='utf-8', newline='') as handle:
        expected = {(r['scope'], r['metric'], int(r['lead_days'])): r for r in csv.DictReader(handle)}
    sql = (HERE / 'validation_query.sql').read_text(encoding='utf-8')
    from psycopg.rows import dict_row
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql, {'start': meta['start_inclusive'], 'end': meta['end_exclusive']})
            actual = cursor.fetchall()
    if len(actual) != len(expected):
        raise ValueError('Independent query group count differs')
    for row in actual:
        reference = expected[(row['scope'], row['metric'], row['lead_days'])]
        for field in ('n_pairs', 'n_target_dates', 'n_changed'):
            if row[field] != int(reference[field]):
                raise ValueError('Independent count differs: ' + field)
        for field in ('mean_absolute_revision', 'revision_frequency_pct'):
            if abs(float(row[field]) - float(reference[field])) > 1e-10:
                raise ValueError('Independent calculation differs: ' + field)
    with (result_dir / 'revision_overall.csv').open(encoding='utf-8', newline='') as handle:
        for overall in csv.DictReader(handle):
            group = [r for r in expected.values() if r['scope'] == overall['scope'] and r['metric'] == overall['metric']]
            if sum(int(r['n_pairs']) for r in group) != int(overall['n_pairs']):
                raise ValueError('Lead counts do not reconcile to overall')
            recomputed = sum(int(r['n_pairs']) * float(r['mean_absolute_revision']) for r in group) / int(overall['n_pairs'])
            if abs(recomputed - float(overall['mean_absolute_revision'])) > 1e-10:
                raise ValueError('Weighted lead mean differs from overall')
    verification = {
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'database_modified': False, 'independent_sql_group_count': len(actual),
        'checks': ['all scope/metric/lead pair counts, distinct target counts and change counts match SQL',
                   'all mean absolute revisions and change frequencies match SQL to 1e-10',
                   'lead counts and weighted absolute revisions reconcile to overall'],
        'validation_query_sha256': hashlib.sha256(sql.encode()).hexdigest(),
    }
    (result_dir / 'verification.json').write_text(json.dumps(verification, indent=2), encoding='utf-8')
    print(f'Independent SQL reconciliation passed for {len(actual)} scope/variable/lead groups.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if type(exc).__module__.startswith('psycopg'):
            print('Database read failed; raw details withheld.', file=sys.stderr)
        else:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
