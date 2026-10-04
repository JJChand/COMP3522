"""RQ1: changes between successive archived HKO forecasts, read-only.

No raw forecast/observation export and no database writes. CSVs are aggregates.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.database import connect

METRICS = {
    'tmin': ('forecast_tmin_c', 'degC'),
    'tmax': ('forecast_tmax_c', 'degC'),
    'rh_min': ('forecast_rh_min_pct', 'percentage_points'),
    'rh_max': ('forecast_rh_max_pct', 'percentage_points'),
}
PAYLOAD = ('lead_days', *(v[0] for v in METRICS.values()), 'psr', 'wind', 'weather')
SCOPES = ('all_archived_pairs', 'consecutive_le24h', 'daily_latest')


def write_csv(path, rows, fieldnames=None):
    if not rows and not fieldnames:
        raise ValueError('No output rows for ' + path.name)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def canonicalize(rows):
    """Only identical target/time payloads can be collapsed; conflicts stop the run."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row['valid_date'], row['bulletin_time_hkt'])].append(row)
    clean, duplicates = [], []
    for (target, stamp), group in sorted(groups.items()):
        variants = {tuple(row[key] for key in PAYLOAD) for row in group}
        if len(variants) != 1:
            raise ValueError(f'Conflicting forecast payloads at {target}, {stamp}; resolve before analysis.')
        clean.append(min(group, key=lambda r: r['forecast_issue_id']))
        if len(group) > 1:
            duplicates.append({
                'valid_date': target, 'bulletin_time_hkt': stamp,
                'issue_ids': '|'.join(str(r['forecast_issue_id']) for r in sorted(group, key=lambda r: r['forecast_issue_id'])),
                'source_file_ids': '|'.join(str(r['source_file_id']) for r in sorted(group, key=lambda r: r['source_file_id'])),
                'removed_rows': len(group) - 1, 'rule': 'identical_complete_forecast_payload',
            })
    return clean, duplicates


def build_pairs(rows):
    """Pair before filtering null metrics or lead zero; never bridge them silently."""
    release_index = {stamp: index for index, stamp in enumerate(sorted({r['bulletin_time_hkt'] for r in rows}))}
    targets = defaultdict(list)
    for row in rows:
        targets[row['valid_date']].append(row)
    pairs = []
    for target, trajectory in sorted(targets.items()):
        trajectory.sort(key=lambda r: r['bulletin_time_hkt'])
        daily = {}
        for row in trajectory:
            daily[row['bulletin_time_hkt'].date()] = row
        for scope, selected in (('all_archived_pairs', trajectory), ('daily_latest', list(daily.values()))):
            for earlier, later in zip(selected, selected[1:]):
                if not (1 <= earlier['lead_days'] <= 9 and 1 <= later['lead_days'] <= 9):
                    continue
                hours = (later['bulletin_time_hkt'] - earlier['bulletin_time_hkt']).total_seconds() / 3600
                days = (later['bulletin_time_hkt'].date() - earlier['bulletin_time_hkt'].date()).days
                skipped = release_index[later['bulletin_time_hkt']] - release_index[earlier['bulletin_time_hkt']] - 1
                if hours <= 0:
                    raise ValueError('Nonpositive pair interval')
                if scope == 'daily_latest' and days != 1:
                    continue
                pair = {
                    'scope': scope, 'valid_date': target, 'lead_days': later['lead_days'],
                    'earlier_lead_days': earlier['lead_days'], 'elapsed_hours': hours,
                    'issue_day_gap': days, 'skipped_archived_bulletins': skipped,
                    'cadence': 'within_issue_day' if days == 0 else 'cross_issue_day',
                    'psr_changed': None if earlier['psr'] is None or later['psr'] is None else earlier['psr'] != later['psr'],
                }
                for metric, (column, _) in METRICS.items():
                    a, b = earlier[column], later[column]
                    pair[metric] = None if a is None or b is None else b - a
                pairs.append(pair)
                if scope == 'all_archived_pairs' and hours <= 24 and skipped == 0:
                    pairs.append(dict(pair, scope='consecutive_le24h'))
    return pairs


def cluster_interval(values, dates, repetitions, seed):
    """Target-date cluster bootstrap; retains all repeated vintages for that date."""
    totals = defaultdict(lambda: [0.0, 0])
    for value, target in zip(values, dates):
        totals[target][0] += value
        totals[target][1] += 1
    packed = np.array(list(totals.values()), dtype=float)
    if len(packed) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    estimates = []
    for offset in range(0, repetitions, 100):
        draws = rng.integers(0, len(packed), size=(min(100, repetitions - offset), len(packed)))
        selected = packed[draws].sum(axis=1)
        estimates.extend(selected[:, 0] / selected[:, 1])
    return tuple(float(v) for v in np.quantile(estimates, (0.025, 0.975)))


def summarize(pairs, dimensions=(), repetitions=1000, seed=3522, intervals=True):
    groups = defaultdict(list)
    for pair in pairs:
        groups[(pair['scope'], *(pair[key] for key in dimensions))].append(pair)
    result = []
    for group, members in sorted(groups.items()):
        for metric, (_, unit) in METRICS.items():
            valid = [p for p in members if p[metric] is not None]
            if not valid:
                continue
            # Decimal differences preserve exact equality at the source's precision.
            absolute = [float(abs(p[metric])) for p in valid]
            changed = [float(p[metric] != 0) for p in valid]
            dates = [p['valid_date'] for p in valid]
            row = dict(zip(('scope', *dimensions), group))
            row.update({
                'metric': metric, 'unit': unit, 'n_candidate_pairs': len(members),
                'n_pairs': len(valid), 'n_missing_pairs': len(members) - len(valid),
                'n_target_dates': len(set(dates)),
                'mean_absolute_revision': float(np.mean(absolute)),
                'median_absolute_revision': float(np.median(absolute)),
                'p90_absolute_revision': float(np.quantile(absolute, 0.9)),
                'n_changed': int(sum(changed)), 'revision_frequency_pct': 100 * float(np.mean(changed)),
                'mean_signed_revision': float(np.mean([float(p[metric]) for p in valid])),
                'mean_elapsed_hours': float(np.mean([p['elapsed_hours'] for p in valid])),
            })
            if intervals:
                low, high = cluster_interval(absolute, dates, repetitions, seed)
                flow, fhigh = cluster_interval(changed, dates, repetitions, seed)
                row.update({
                    'mar_ci95_low': low, 'mar_ci95_high': high,
                    'frequency_ci95_low_pct': None if flow is None else 100 * flow,
                    'frequency_ci95_high_pct': None if fhigh is None else 100 * fhigh,
                })
            result.append(row)
    return result


def near_far_comparison(pairs, repetitions, seed):
    """Matched dates avoid interpreting two differently covered cohorts as a trend."""
    output = []
    for scope in SCOPES:
        for metric, (_, unit) in METRICS.items():
            targets = defaultdict(lambda: defaultdict(list))
            for pair in pairs:
                if pair['scope'] != scope or pair[metric] is None:
                    continue
                lead = pair['lead_days']
                group = 'near' if 1 <= lead <= 3 else ('far' if 7 <= lead <= 8 else None)
                if group:
                    targets[pair['valid_date']][group].append(float(abs(pair[metric])))
            matched = [(d, float(np.mean(g['near'])), float(np.mean(g['far'])))
                       for d, g in sorted(targets.items()) if g['near'] and g['far']]
            if not matched:
                continue
            differences = [near - far for _, near, far in matched]
            low, high = cluster_interval(differences, [r[0] for r in matched], repetitions, seed)
            output.append({
                'scope': scope, 'metric': metric, 'unit': unit, 'n_matched_target_dates': len(matched),
                'near_leads': '1-3', 'far_leads': '7-8',
                'mean_near_target_mar': float(np.mean([r[1] for r in matched])),
                'mean_far_target_mar': float(np.mean([r[2] for r in matched])),
                'near_minus_far': float(np.mean(differences)), 'ci95_low': low, 'ci95_high': high,
            })
    return output


def quality_profile(rows, clean, duplicates, start, end):
    issues = {r['forecast_issue_id']: r for r in rows}
    leads = Counter(r['lead_days'] for r in rows)
    quality = {
        'start_inclusive': start.isoformat(), 'end_exclusive': end.isoformat(),
        'raw_forecast_rows': len(rows), 'distinct_source_issues': len(issues),
        'canonical_target_time_rows': len(clean), 'identical_duplicate_rows_removed': len(rows) - len(clean),
        'duplicate_target_time_groups': len(duplicates),
        'target_dates_available': len({r['valid_date'] for r in rows}),
        'calendar_target_dates_expected': (end - start).days,
        'lead_zero_rows_excluded_from_pairs': leads[0],
        'lead_mismatch_rows': sum(r['lead_days'] != (r['valid_date'] - r['bulletin_time_hkt'].date()).days for r in rows),
        'invalid_numeric_ranges': sum(
            (r['forecast_tmin_c'] is not None and r['forecast_tmax_c'] is not None and r['forecast_tmin_c'] > r['forecast_tmax_c'])
            or (r['forecast_rh_min_pct'] is not None and r['forecast_rh_max_pct'] is not None
                and not 0 <= r['forecast_rh_min_pct'] <= r['forecast_rh_max_pct'] <= 100) for r in rows),
        'midnight_source_issues': sum(r['bulletin_time_hkt'].time().isoformat() == '00:00:00' for r in issues.values()),
        'titles_without_explicit_hkt_update_time': sum(not re.search(r'updated\s+at\s+\d{1,2}:\d{2}\s+HKT\s+\d{1,2}/[A-Za-z]{3}/\d{4}', r['title'], re.I) for r in issues.values()),
    }
    for metric, (column, _) in METRICS.items():
        quality['null_' + metric + '_rows'] = sum(r[column] is None for r in rows)
    if quality['lead_mismatch_rows'] or quality['invalid_numeric_ranges']:
        raise ValueError('Invalid lead/range values; resolve before reporting RQ1.')
    return quality


def write_findings(result_dir, quality, by_lead, comparison):
    lines = [
        '# RQ1 — successive forecast revisions', '',
        'Exploratory Task 1 results. This analysis does not evaluate forecast accuracy or compare agencies.', '',
        f"Target-date range: {quality['start_inclusive']} inclusive to {quality['end_exclusive']} exclusive.", '',
        '## Coverage', '',
        f"Read {quality['raw_forecast_rows']:,} forecast-day rows from {quality['distinct_source_issues']:,} archived issues; "
        f"{quality['target_dates_available']:,} of {quality['calendar_target_dates_expected']:,} target dates are represented.",
        f"Removed {quality['identical_duplicate_rows_removed']} identical duplicate target/time rows only in memory. "
        'No database changes. Lead zero is excluded; no numeric forecast nulls are filled.', '',
        '## How large are the changes?', '',
        'Primary scope: successive archived target-date vintages, adjacent in the observed bulletin timeline and at most 24 hours apart. '
        'Values below are mean absolute revision / percentage of pairs that changed. RH units are percentage points.', '',
        '| Variable | Later lead 1 | Later lead 3 | Later lead 7 | Later lead 9 |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for metric, (_, unit) in METRICS.items():
        cells = []
        for lead in (1, 3, 7, 9):
            found = next((r for r in by_lead if r['scope'] == 'consecutive_le24h' and r['metric'] == metric and r['lead_days'] == lead), None)
            cells.append('not available' if found is None else f"{found['mean_absolute_revision']:.3f} / {found['revision_frequency_pct']:.1f}%")
        lines.append('| ' + f'{metric} ({unit})' + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## Does the change shrink near the target day?', '',
              'This is a paired comparison: each included target date supplies an average absolute revision at leads 1–3 and 7–8. '
              'Target dates have equal weight. A negative near-minus-far difference means smaller near-day revisions; '
              'it does not imply every individual lead follows a monotonic trend. Lead 9 is excluded from this contrast '
              'because its predecessor coverage differs structurally and it is unavailable in the daily-latest scope.', '',
              '| Scope | Variable | Matched dates | Near − far | 95% interval |',
              '| --- | --- | ---: | ---: | --- |']
    for row in comparison:
        bounds = 'unavailable' if row['ci95_low'] is None else f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]"
        lines.append(f"| {row['scope']} | {row['metric']} | {row['n_matched_target_dates']} | {row['near_minus_far']:.3f} | {bounds} |")
    lines += ['', 'Reading the table: negative intervals entirely below zero support smaller average near-day revisions '
              'for that scope and variable under this exploratory bootstrap. An interval spanning zero does not establish a difference. '
              'Use the full lead-day plots before describing a smooth or monotonic decline; the result can depend on release cadence.']
    lines += ['', '## Interpretation limits', '',
              '- Bulletin timings and archive capture vary. `all_archived_pairs` includes long gaps; the primary scope excludes them. '
              '`daily_latest` uses the latest archived forecast for each target/issue day, compared only over consecutive issue days.',
              '- These are archived vintages, not proof that every real HKO release was captured. Do not describe revision frequency as changes per day.',
              '- Lead 9 may have only within-day comparisons: a lead-10 forecast is outside the product. Daily-latest comparisons generally stop at later lead 8.',
              '- Early January 2022 trajectories are left-truncated by the source archive; lead coverage and pair denominators are saved.',
              '- Confidence intervals resample target-date clusters, preserving repeated vintages within dates. They do not address serial dependence between adjacent weather days.',
              '- PSR is categorical. Its change frequency is saved separately; no numeric probability or equal-distance category score is invented.',
              '- Zero revisions are retained in mean absolute revision and frequency denominators. Source precision limits measurable changes.',
              '- This is RQ1 only. Revision direction and whether updates improve accuracy belong to RQ2 and RQ3.', '',
              '## Reproducibility', '',
              'SQL: `../forecast_query.sql`. Parameters, source fingerprint, coverage checks and software versions: `run_metadata.json`. '
              'Exact denominators and intervals: `revision_by_lead.csv`; gap audit: `pair_coverage.csv`; '
              'paired approach comparison: `near_far_comparison.csv`. No raw forecast values are exported.', '']
    (result_dir / 'findings.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument('--end', type=date.fromisoformat, default=date(2026, 1, 1), help='Exclusive target date')
    parser.add_argument('--bootstrap', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=3522)
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args()
    if args.start >= args.end or args.bootstrap < 100:
        parser.error('Use start < end and at least 100 bootstrap replicates.')
    sql = (HERE / 'forecast_query.sql').read_text(encoding='utf-8')
    from psycopg.rows import dict_row
    with connect() as connection:
        connection.isolation_level = __import__('psycopg').IsolationLevel.REPEATABLE_READ
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()['transaction_read_only'] != 'on':
                raise ValueError('Database session is not read-only')
            cursor.execute(sql, {'start': args.start, 'end': args.end})
            rows = cursor.fetchall()
    if not rows:
        raise ValueError('No forecast rows in the requested target-date period')
    clean, duplicates = canonicalize(rows)
    quality = quality_profile(rows, clean, duplicates, args.start, args.end)
    pairs = build_pairs(clean)
    for pair in pairs:
        pair['target_year'] = pair['valid_date'].year
    if not pairs:
        raise ValueError('No eligible revision pairs in this date range')
    results = HERE / 'results'
    results.mkdir(exist_ok=True)
    by_lead = summarize(pairs, ('lead_days',), args.bootstrap, args.seed)
    comparison = near_far_comparison(pairs, args.bootstrap, args.seed)
    write_csv(results / 'revision_by_lead.csv', by_lead)
    write_csv(results / 'revision_overall.csv', summarize(pairs, (), args.bootstrap, args.seed))
    write_csv(results / 'revision_by_cadence_and_lead.csv', summarize(pairs, ('cadence', 'lead_days'), intervals=False))
    write_csv(results / 'revision_by_year_and_lead.csv', summarize(pairs, ('target_year', 'lead_days'), intervals=False))
    write_csv(results / 'near_far_comparison.csv', comparison, [
        'scope', 'metric', 'unit', 'n_matched_target_dates', 'near_leads', 'far_leads',
        'mean_near_target_mar', 'mean_far_target_mar', 'near_minus_far', 'ci95_low', 'ci95_high',
    ])
    gap_groups = defaultdict(list)
    for pair in pairs:
        hours = pair['elapsed_hours']
        band = '0-6h' if hours <= 6 else ('6-12h' if hours <= 12 else ('12-24h' if hours <= 24 else '>24h'))
        gap_groups[(pair['scope'], pair['cadence'], band, pair['skipped_archived_bulletins'] > 0)].append(pair)
    write_csv(results / 'pair_coverage.csv', [
        dict(scope=k[0], cadence=k[1], elapsed_band=k[2], skipped_bulletins=k[3], n_pairs=len(v),
             n_target_dates=len({p['valid_date'] for p in v}), mean_elapsed_hours=float(np.mean([p['elapsed_hours'] for p in v])))
        for k, v in sorted(gap_groups.items())
    ])
    psr = defaultdict(list)
    for pair in pairs:
        psr[(pair['scope'], pair['lead_days'])].append(pair)
    write_csv(results / 'psr_change_by_lead.csv', [
        dict(scope=k[0], lead_days=k[1], n_candidate_pairs=len(v),
             n_pairs=sum(p['psr_changed'] is not None for p in v),
             n_changed=sum(p['psr_changed'] is True for p in v),
             change_frequency_pct=(100 * sum(p['psr_changed'] is True for p in v) / sum(p['psr_changed'] is not None for p in v))
             if any(p['psr_changed'] is not None for p in v) else None)
        for k, v in sorted(psr.items())
    ])
    write_csv(results / 'identical_duplicate_audit.csv', duplicates, [
        'valid_date', 'bulletin_time_hkt', 'issue_ids', 'source_file_ids', 'removed_rows', 'rule',
    ])
    write_csv(results / 'coverage_by_lead.csv', [
        dict(lead_days=lead, raw_rows=sum(r['lead_days'] == lead for r in rows),
             canonical_rows=sum(r['lead_days'] == lead for r in clean),
             n_target_dates=len({r['valid_date'] for r in clean if r['lead_days'] == lead}))
        for lead in sorted({r['lead_days'] for r in rows})
    ])
    fingerprint = hashlib.sha256()
    for row in rows:
        fingerprint.update(json.dumps(row, default=str, sort_keys=True, ensure_ascii=False).encode('utf-8'))
        fingerprint.update(b'\n')
    metadata = {
        'run_at_utc': datetime.now(timezone.utc).isoformat(), 'task': 'Task 1 / RQ1',
        'start_inclusive': args.start.isoformat(), 'end_exclusive': args.end.isoformat(),
        'read_only': True, 'database_modified': False, 'quality': quality,
        'source_tables': ['project.hko_forecast_daily', 'project.hko_forecast_issue', 'project.hko_source_file'],
        'query_file': 'forecast_query.sql', 'query_sha256': hashlib.sha256(sql.encode()).hexdigest(),
        'source_rows_sha256': fingerprint.hexdigest(), 'unique_source_file_count': len({r['source_file_id'] for r in rows}),
        'bootstrap_repetitions': args.bootstrap, 'bootstrap_seed': args.seed, 'bootstrap_cluster': 'valid_date',
        'bootstrap_interval': '95% percentile; no serial-dependence correction',
        'pair_counts': dict(Counter(p['scope'] for p in pairs)),
        'numeric_change_rule': 'exact nonzero Decimal difference at published precision',
        'primary_gap_limit_hours': 24, 'primary_scope': 'consecutive_le24h',
        'python_version': sys.version.split()[0],
        'package_versions': {p: importlib.metadata.version(p) for p in ('numpy', 'psycopg', 'python-dotenv')},
    }
    (results / 'run_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    write_findings(results, quality, by_lead, comparison)
    if not args.no_plots:
        from plot_results import main as plot
        plot()
    print(f"RQ1 complete: {len(rows):,} source rows; {len(clean):,} canonical rows. Read-only database session.")
    print('Results: ' + str(results))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not expose connection strings, passwords, or arbitrary server errors.
        if type(exc).__module__.startswith('psycopg'):
            print('Database read failed. Check root .env and connection access; raw details withheld.', file=sys.stderr)
        else:
            print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
