"""RQ2: numeric flip-flop indices, revision sign transitions and PSR changes."""
from collections import Counter, defaultdict
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import (METRICS, PSR_CATEGORIES, cli, csv_output, daily_latest, interval,
                          report, result_dir, revision_pairs, save_metadata, table)
from common.plotting import COLORS, panels, save


def flip_flop_index(values):
    """Griffiths et al.: (total path length - observed range)/(N-2), N>=3."""
    if len(values) < 3:
        return None
    values = np.asarray(values, dtype=float)
    return max(0., float((np.abs(np.diff(values)).sum() - np.ptp(values)) / (len(values) - 2)))


def sign(value):
    return int(value > 0) - int(value < 0)


def segments(rows, scope, column):
    allowed = {(p['earlier']['forecast_issue_id'], p['later']['forecast_issue_id'], p['valid_date'])
               for p in revision_pairs(rows, scope)}
    trajectories = defaultdict(list)
    for row in (daily_latest(rows) if scope == 'daily_latest' else rows):
        trajectories[row['valid_date']].append(row)
    output = []
    for target, trajectory in sorted(trajectories.items()):
        current = []
        for row in sorted(trajectory, key=lambda r: r['bulletin_time_hkt']):
            valid = 1 <= row['lead_days'] <= 9 and row[column] is not None
            linked = current and (current[-1]['forecast_issue_id'], row['forecast_issue_id'], target) in allowed
            if not valid or (current and not linked):
                if current:
                    output.append((target, current))
                current = []
            if valid:
                current.append(row)
        if current:
            output.append((target, current))
    return output


def analyze(snapshot):
    folder = result_dir(2)
    direction_records, transition_records, ffi_rows = [], [], []
    index_summary = []
    for scope in ('consecutive_le24h', 'daily_latest'):
        pairs = revision_pairs(snapshot.forecasts, scope)
        for pair in pairs:
            a, b = pair['earlier'], pair['later']
            for metric, column in dict(METRICS, psr='psr').items():
                if a[column] is None or b[column] is None:
                    continue
                delta = (PSR_CATEGORIES.index(b[column]) - PSR_CATEGORIES.index(a[column])) if metric == 'psr' else b[column]-a[column]
                direction_records.append(dict(scope=scope, metric=metric, lead_days=b['lead_days'],
                                              valid_date=b['valid_date'], direction=sign(delta)))
            transition_records.append(dict(scope=scope, lead_days=b['lead_days'], before=a['psr'], after=b['psr']))
        for metric, column in METRICS.items():
            date_indices = defaultdict(list)
            adjacent, compressed = [], []
            for target, path in segments(snapshot.forecasts, scope, column):
                values = [float(r[column]) for r in path]
                ffi = flip_flop_index(values)
                if ffi is not None:
                    date_indices[target].append(ffi)
                    ffi_rows.append(dict(scope=scope, metric=metric, valid_date=target,
                                         n_vintages=len(values), first_lead=path[0]['lead_days'],
                                         last_lead=path[-1]['lead_days'], flip_flop_index=ffi))
                signs = [sign(b[column]-a[column]) for a, b in zip(path, path[1:])]
                adjacent.extend((target, int(a != b)) for a, b in zip(signs, signs[1:]) if a and b)
                nonzero = [s for s in signs if s]
                compressed.extend((target, int(a != b)) for a, b in zip(nonzero, nonzero[1:]))
            by_date = [(d, float(np.mean(v))) for d, v in date_indices.items()]
            lo, hi = interval([r[1] for r in by_date], [r[0] for r in by_date])
            index_summary.append(dict(scope=scope, metric=metric, unit='degC' if metric.startswith('t') else 'percentage_points',
                                      n_target_dates=len(by_date), n_segments=sum(len(v) for v in date_indices.values()),
                                      mean_target_ffi=float(np.mean([r[1] for r in by_date])) if by_date else None,
                                      ci95_low=lo, ci95_high=hi,
                                      n_adjacent_nonzero_sign_pairs=len(adjacent),
                                      adjacent_reversal_rate_pct=100*np.mean([r[1] for r in adjacent]) if adjacent else None,
                                      n_consecutive_nonzero_sign_pairs=len(compressed),
                                      compressed_reversal_rate_pct=100*np.mean([r[1] for r in compressed]) if compressed else None))
    grouped = defaultdict(Counter)
    for row in direction_records:
        grouped[(row['scope'], row['metric'], row['lead_days'])][row['direction']] += 1
    directions = [dict(scope=k[0], metric=k[1], lead_days=k[2], n_pairs=sum(c.values()),
                       n_decrease=c[-1], n_unchanged=c[0], n_increase=c[1],
                       decrease_pct=100*c[-1]/sum(c.values()), increase_pct=100*c[1]/sum(c.values()))
                  for k, c in sorted(grouped.items())]
    transitions = Counter((r['scope'], r['before'], r['after']) for r in transition_records)
    psr_rows = [dict(scope=scope, before=a, after=b, n_pairs=transitions[(scope, a, b)])
                for scope in ('consecutive_le24h', 'daily_latest') for a in PSR_CATEGORIES for b in PSR_CATEGORIES]
    csv_output(folder / 'direction_by_lead.csv', directions)
    csv_output(folder / 'flip_flop_summary.csv', index_summary)
    csv_output(folder / 'flip_flop_by_target_segment.csv', ffi_rows)
    csv_output(folder / 'psr_transition_counts.csv', psr_rows)
    fig, axes = panels('RQ2 · Numeric revision direction', ['Tmin', 'Tmax'])
    for ax, metric in zip(axes, ('tmin', 'tmax')):
        selected = [r for r in directions if r['scope'] == 'consecutive_le24h' and r['metric'] == metric]
        x = [r['lead_days'] for r in selected]
        ax.plot(x, [r['increase_pct'] for r in selected], color=COLORS[0], marker='o', label='Increase')
        ax.plot(x, [r['decrease_pct'] for r in selected], color=COLORS[1], marker='s', linestyle='--', label='Decrease')
        ax.set(xlabel='Later lead (days)', ylabel='Percentage of all revision pairs', ylim=(0, 12), xticks=range(1, 10))
        ax.legend(frameon=False)
    save(fig, folder, 'revision_direction.png', 'Zeros are included in the denominator; FFI and reversal rates have separate definitions in the CSVs.')
    selected = [r for r in index_summary if r['scope'] == 'consecutive_le24h']
    findings = '\n\n'.join(f"{r['metric']}: mean date-weighted FFI {r['mean_target_ffi']:.4f} {r['unit']}; "
                            f"adjacent nonzero reversal rate {r['adjacent_reversal_rate_pct']:.1f}% "
                            f"({r['n_adjacent_nonzero_sign_pairs']:,} comparable sign pairs)." for r in selected)
    psr_summary = []
    for scope in ('consecutive_le24h','daily_latest'):
        all_psr = [r for r in psr_rows if r['scope']==scope]
        count = sum(r['n_pairs'] for r in all_psr)
        changed = sum(r['n_pairs'] for r in all_psr if r['before']!=r['after'])
        psr_summary.append(dict(scope=scope,n_pairs=count,n_changed=changed,change_rate_pct=100*changed/count))
    csv_output(folder/'psr_transition_summary.csv',psr_summary)
    report(2, 'Revision direction and flip-flops', findings + '\n\nA nonzero FFI documents back-and-forth movement, not whether an update is useful.',
           table(index_summary, ['scope', 'metric', 'n_target_dates', 'mean_target_ffi', 'adjacent_reversal_rate_pct', 'compressed_reversal_rate_pct'])+
           '\n\n### PSR category changes\n\n'+table(psr_summary,['scope','n_pairs','n_changed','change_rate_pct']),
           'FFI = (sum of successive absolute changes − forecast range)/(N−2), for N≥3, in the variable’s original unit. '
           '[Official scores documentation](https://scores.readthedocs.io/en/latest/api.html#scores.continuous.flip_flop_index). '
           'Continuous trajectories are broken at missing values or disallowed gaps. FFI is averaged within target date then across dates. '
           'The adjacent rate requires both immediately neighboring revision signs to be nonzero; the compressed rate skips zero changes '
           'but never missing values/gaps. PSR uses ordinal direction only, never an equal-distance numeric FFI. '
           'Lead and full category transition counts are in the CSVs; 95% FFI intervals resample target dates.',
           'Archived bulletins may omit actual releases. Daily-latest selection is a cadence sensitivity, not the same population. '
           'Short trajectories cannot have an FFI; zero-change sequences have zero FFI, not missing FFI. '
           'Intervals do not adjust for inter-date serial dependence. PSR categories are probability bands, not probabilities.')
    save_metadata(2, snapshot, {'n_direction_records': len(direction_records), 'n_ffi_segments': len(ffi_rows)})


if __name__ == '__main__':
    cli(2, analyze)
