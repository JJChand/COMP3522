"""Shared source audit and statistical helpers; no source-system writes or raw exports."""
from __future__ import annotations
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
from .database import connect

ANALYSES = Path(__file__).resolve().parents[1]
START, END, HISTORY_START = date(2022, 1, 1), date(2026, 1, 1), date(1991, 1, 1)
SEED, REPLICATES = 3522, 1000
PSR_CATEGORIES = ('Low', 'Medium Low', 'Medium', 'Medium High', 'High')
# Continuous category supports: upper edges are excluded except 1.0.
PSR_BANDS = {'Low': (0., .30), 'Medium Low': (.30, .45), 'Medium': (.45, .55),
             'Medium High': (.55, .70), 'High': (.70, 1.)}
METRICS = {'tmin': 'forecast_tmin_c', 'tmax': 'forecast_tmax_c',
           'rh_min': 'forecast_rh_min_pct', 'rh_max': 'forecast_rh_max_pct'}
TEMP_CODES = {'tmin': 'obs_hko_daily_tmin', 'tmax': 'obs_hko_daily_tmax'}
UNITS = {'tmin': 'degC', 'tmax': 'degC', 'rh_min': 'percentage_points', 'rh_max': 'percentage_points'}
FOLDERS = {2: '03_rq2_revision_direction', 3: '04_rq3_revision_usefulness',
           4: '05_rq4_accuracy_by_lead', 5: '06_rq5_bias',
           6: '07_rq6_psr_calibration', 7: '08_rq7_error_factors'}


def rq1_module():
    name = '_task1_rq1_shared'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ANALYSES / '02_rq1_revisions/run_analysis.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def digest(rows):
    value = hashlib.sha256()
    for row in rows:
        value.update(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False).encode())
        value.update(b'\n')
    return value.hexdigest()


def csv_output(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fields:
        raise ValueError('No rows: ' + path.name)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def season(target):
    return ('DJF', 'MAM', 'JJA', 'SON')[((target.month % 12) // 3)]


def group_rows(rows, keys):
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    return grouped


def interval(values, dates, block_days=1, repetitions=REPLICATES):
    """Bootstrap ratio-of-totals over observed dates or fixed calendar blocks.

    All records belonging to a date/block move together. Empty blocks are omitted;
    report block_days and actual coverage rather than implying independent cases.
    """
    totals = defaultdict(lambda: [0., 0])
    for value, target in zip(values, dates):
        key = (target - START).days // block_days
        totals[key][0] += float(value)
        totals[key][1] += 1
    if len(totals) < 2:
        return None, None
    packed = np.array(list(totals.values()), dtype=float)
    rng = np.random.default_rng(SEED)
    estimates = []
    for offset in range(0, repetitions, 100):
        draw = rng.integers(0, len(packed), size=(min(100, repetitions-offset), len(packed)))
        sampled = packed[draw].sum(axis=1)
        estimates.extend(sampled[:, 0] / sampled[:, 1])
    return tuple(float(v) for v in np.quantile(estimates, [.025, .975]))


def ratio(a, b):
    return float(a / b) if b else None


def metric_summary(errors):
    errors = np.asarray(errors, dtype=float)
    if not len(errors):
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None}
    return {'n': len(errors), 'mae': float(np.mean(np.abs(errors))),
            'rmse': float(np.sqrt(np.mean(errors ** 2))), 'bias': float(np.mean(errors))}


def daily_latest(rows):
    selected = {}
    for row in sorted(rows, key=lambda r: (r['bulletin_time_hkt'], r['forecast_issue_id'])):
        selected[(row['valid_date'], row['bulletin_time_hkt'].date())] = row
    return sorted(selected.values(), key=lambda r: (r['valid_date'], r['bulletin_time_hkt']))


def revision_pairs(rows, scope='consecutive_le24h'):
    """Return endpoints; lead/missing filters never splice the original trajectory."""
    by_target = defaultdict(list)
    ordered = sorted(rows, key=lambda r: (r['valid_date'], r['bulletin_time_hkt']))
    global_index = {t: n for n, t in enumerate(sorted({r['bulletin_time_hkt'] for r in ordered}))}
    for row in (daily_latest(ordered) if scope == 'daily_latest' else ordered):
        by_target[row['valid_date']].append(row)
    pairs = []
    for target, path in sorted(by_target.items()):
        for a, b in zip(path, path[1:]):
            hours = (b['bulletin_time_hkt'] - a['bulletin_time_hkt']).total_seconds() / 3600
            days = (b['bulletin_time_hkt'].date() - a['bulletin_time_hkt'].date()).days
            if not (1 <= a['lead_days'] <= 9 and 1 <= b['lead_days'] <= 9 and hours > 0):
                continue
            if scope == 'consecutive_le24h' and (hours > 24 or global_index[b['bulletin_time_hkt']] - global_index[a['bulletin_time_hkt']] != 1):
                continue
            if scope == 'daily_latest' and days != 1:
                continue
            pairs.append({'earlier': a, 'later': b, 'valid_date': target,
                          'lead_days': b['lead_days'], 'scope': scope, 'elapsed_hours': hours,
                          'cadence': 'within_day' if days == 0 else 'cross_day'})
    return pairs


@dataclass
class Snapshot:
    forecasts: list
    observations: list
    series: list
    stations: list
    meta: dict
    rh_reports: list = field(default_factory=list)

    def observed(self, code):
        series = [r for r in self.series if r['series_code'] == code]
        if len(series) != 1:
            raise ValueError('Observation target must be a unique series: ' + code)
        return {r['observation_date']: float(r['value_numeric']) for r in self.observations
                if r['series_code'] == code and r['value_numeric'] is not None and r['data_completeness'] == 'C'}

    def temperature_cases(self, selection='daily_latest'):
        return self.verification_cases(selection, tuple(TEMP_CODES))

    def rh_observed(self):
        from .rh_observations import validate_reports
        endpoints, _ = validate_reports(self.rh_reports, START, END)
        return endpoints

    def verification_cases(self, selection='daily_latest', metrics=tuple(METRICS)):
        records = daily_latest(self.forecasts) if selection == 'daily_latest' else self.forecasts
        observed = {m: self.observed(c) for m, c in TEMP_CODES.items()}
        if any(m.startswith('rh_') for m in metrics):
            observed.update(self.rh_observed())
        output = []
        for row in records:
            if not 1 <= row['lead_days'] <= 9:
                continue
            for metric in metrics:
                target, value = row['valid_date'], row[METRICS[metric]]
                if value is None or target not in observed[metric]:
                    continue
                actual = observed[metric][target]
                output.append(dict(row, metric=metric, observed=actual, forecast=float(value),
                                   error=float(value)-actual, season=season(target), year=target.year,
                                   selection=selection, unit=UNITS[metric]))
        return output


def load_snapshot():
    from psycopg import IsolationLevel
    from psycopg.rows import dict_row
    here = Path(__file__).resolve().parent
    forecast_sql = (here / 'forecast_query.sql').read_text(encoding='utf-8')
    observation_sql = (here / 'observation_query.sql').read_text(encoding='utf-8')
    rh_sql = (here / 'rh_report_query.sql').read_text(encoding='utf-8')
    study_codes = ['obs_hko_daily_mean_rh', 'obs_hko_daily_rainfall',
                   'obs_spatial_daily_temperature', 'obs_spatial_daily_rainfall',
                   'obs_hko_daily_mean_cloud', 'obs_hko_daily_mean_pressure',
                   'obs_hka_daily_mean_wind_speed', 'obs_kp_daily_sunshine']
    with connect() as connection:
        connection.isolation_level = IsolationLevel.REPEATABLE_READ
        with connection.cursor(row_factory=dict_row) as cur:
            cur.execute('SHOW transaction_read_only')
            if cur.fetchone()['transaction_read_only'] != 'on':
                raise ValueError('Refusing a non-read-only database session')
            cur.execute(forecast_sql, {'start': START, 'end': END})
            raw = cur.fetchall()
            cur.execute(observation_sql, {'start': START, 'end': END,
                                         'history_start': HISTORY_START, 'study_codes': study_codes})
            observations = cur.fetchall()
            cur.execute(rh_sql, {'start': START, 'end': END})
            rh_reports = cur.fetchall()
            cur.execute('SELECT observation_series_id, series_code, station_name, metric_name, unit, title_en, source_file_id FROM project.hko_observation_series ORDER BY observation_series_id')
            series = cur.fetchall()
            cur.execute('SELECT station_code, station_name, latitude, longitude FROM project.hko_station ORDER BY station_code')
            stations = cur.fetchall()
    clean, duplicate_audit = rq1_module().canonicalize(raw)
    quality = rq1_module().quality_profile(raw, clean, duplicate_audit, START, END)
    if not raw or not observations:
        raise ValueError('Missing source data')
    unknown = {r['psr'] for r in clean if r['psr'] is not None} - set(PSR_CATEGORIES)
    if unknown:
        raise ValueError('Unexpected PSR categories')
    if len({(r['observation_series_id'], r['observation_date']) for r in observations}) != len(observations):
        raise ValueError('Observation query duplicated the series/date grain')
    meta = {
        'loaded_at_utc': datetime.now(timezone.utc).isoformat(), 'database_modified': False,
        'read_only': True, 'snapshot_isolation': 'REPEATABLE READ',
        'start_inclusive': str(START), 'end_exclusive': str(END),
        'history_start_inclusive': str(HISTORY_START), 'forecast_quality': quality,
        'forecast_rows_sha256': digest(raw), 'observation_rows_sha256': digest(observations),
        'rh_report_rows_sha256': digest(rh_reports),
        'source_query_sha256': {'forecast_query.sql': hashlib.sha256(forecast_sql.encode()).hexdigest(),
                                'observation_query.sql': hashlib.sha256(observation_sql.encode()).hexdigest(),
                                'rh_report_query.sql': hashlib.sha256(rh_sql.encode()).hexdigest()},
        'observation_rows_loaded': len(observations),
        'bootstrap_repetitions': REPLICATES, 'seed': SEED,
        'python_version': sys.version.split()[0],
        'package_versions': {p: importlib.metadata.version(p) for p in ('numpy', 'matplotlib', 'psycopg', 'python-dotenv')},
        'rh_extrema_series_available': [r['series_code'] for r in series if 'humidity' in r['title_en'].lower() and 'mean' not in r['title_en'].lower()],
    }
    snapshot = Snapshot(clean, observations, series, stations, meta, rh_reports)
    from .rh_observations import validate_reports
    _, meta['rh_report_validation'] = validate_reports(rh_reports, START, END, {
        **{m: snapshot.observed(c) for m, c in TEMP_CODES.items()},
        'rh_mean': snapshot.observed('obs_hko_daily_mean_rh')})
    return snapshot


def result_dir(rq):
    folder = ANALYSES / FOLDERS[rq] / 'results'
    folder.mkdir(exist_ok=True)
    return folder


def save_metadata(rq, snapshot, extra=None):
    folder = result_dir(rq)
    meta = dict(snapshot.meta, rq=rq, completed_at_utc=datetime.now(timezone.utc).isoformat())
    if extra:
        meta.update(extra)
    (folder / 'run_metadata.json').write_text(json.dumps(meta, indent=2, default=str), encoding='utf-8')


def table(rows, fields, limit=None):
    def display(value):
        if value is None:
            return 'unavailable'
        if isinstance(value, (float, np.floating)):
            return f'{value:.4f}'
        return str(value)
    text = ['| ' + ' | '.join(fields) + ' |', '| ' + ' | '.join('---' for _ in fields) + ' |']
    for row in rows[:limit] if limit else rows:
        text.append('| ' + ' | '.join(display(row.get(key)) for key in fields) + ' |')
    return '\n'.join(text)


def report(rq, title, findings, results_text, methods, caveats):
    folder = result_dir(rq)
    body = [f'# RQ{rq}: {title}', '', 'Target dates: 2022-01-01–2025-12-31. Task 1 only.', '',
            '## Findings', '', findings, '', '## Concrete results', '', results_text, '',
            '## Methods and source evidence', '', methods, '', '## Limitations', '', caveats, '',
            '## Reproduce', '',
            f'From the repository root: `.\\.venv\\Scripts\\python.exe analyses/{FOLDERS[rq]}/run_analysis.py`.', '',
            'Database access is read-only. Source SQL is in `../common/` relative to the analysis folder; '
            'source fingerprints, parameters and versions are in `run_metadata.json`. '
            'Only reviewed aggregates and figures are exported, not raw forecast/observation values.', '']
    (folder / 'findings.md').write_text('\n'.join(body), encoding='utf-8')


def cli(rq, analyze):
    try:
        snapshot = load_snapshot()
        analyze(snapshot)
        print(f'RQ{rq} executed. Results: {result_dir(rq)}')
    except Exception as exc:
        if type(exc).__module__.startswith('psycopg'):
            print('Database read failed; raw details withheld. Check root .env and access.', file=sys.stderr)
        else:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
