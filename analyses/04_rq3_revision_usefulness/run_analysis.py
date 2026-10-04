"""RQ3: score paired revision endpoints against identical HKO outcomes."""
from collections import defaultdict
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import (METRICS, TEMP_CODES, UNITS, cli, csv_output, group_rows, interval,
                          report, result_dir, revision_pairs, save_metadata, table)
from common.plotting import COLORS, panels, save


def classify_improvement(earlier, later, actual):
    benefit = abs(float(earlier)-actual) - abs(float(later)-actual)
    return ('improved' if benefit > 1e-10 else 'worsened' if benefit < -1e-10 else 'tied'), benefit


def summarize(records, keys):
    output = []
    for key, members in sorted(group_rows(records, keys).items()):
        for denominator in ('changed_only', 'all_pairs'):
            eligible = [r for r in members if denominator == 'all_pairs' or r['changed']]
            if not eligible:
                continue
            statuses = {s: sum(r['status'] == s for r in eligible) for s in ('improved', 'worsened', 'tied')}
            lo, hi = interval([int(r['status'] == 'improved') for r in eligible], [r['valid_date'] for r in eligible])
            output.append(dict(zip(keys, key)) | dict(
                denominator=denominator, n_pairs=len(eligible), n_target_dates=len({r['valid_date'] for r in eligible}),
                **{'n_' + k: v for k, v in statuses.items()},
                usefulness_rate_pct=100*statuses['improved']/len(eligible),
                ci95_low_pct=None if lo is None else 100*lo, ci95_high_pct=None if hi is None else 100*hi,
                mean_absolute_error_reduction=float(np.mean([r['benefit'] for r in eligible]))))
    return output


def analyze(snapshot):
    folder = result_dir(3)
    observed = {metric: snapshot.observed(code) for metric, code in TEMP_CODES.items()} | snapshot.rh_observed()
    records, coverage = [], []
    for scope in ('consecutive_le24h', 'daily_latest'):
        pairs = revision_pairs(snapshot.forecasts, scope)
        for metric in METRICS:
            code = TEMP_CODES.get(metric, 'HKOReadingsMinRH' if metric=='rh_min' else 'HKOReadingsMaxRH')
            missing = 0
            for pair in pairs:
                a, b = pair['earlier'][METRICS[metric]], pair['later'][METRICS[metric]]
                if a is None or b is None or pair['valid_date'] not in observed[metric]:
                    missing += 1
                    continue
                status, benefit = classify_improvement(a, b, observed[metric][pair['valid_date']])
                records.append(dict(scope=scope, metric=metric, lead_days=pair['lead_days'], valid_date=pair['valid_date'],
                                    changed=a != b, status=status, benefit=benefit))
            coverage.append(dict(scope=scope, metric=metric, source_series=code,
                                 n_candidate_pairs=len(pairs), n_unmatched_or_null=missing,
                                 n_matched_pairs=len(pairs)-missing))
    overall = summarize(records, ('scope', 'metric'))
    by_lead = summarize(records, ('scope', 'metric', 'lead_days'))
    for r in overall+by_lead:
        r['error_reduction_unit'] = UNITS[r['metric']]
    csv_output(folder / 'usefulness_overall.csv', overall)
    csv_output(folder / 'usefulness_by_lead.csv', by_lead)
    csv_output(folder / 'join_coverage.csv', coverage)
    for metrics, titles, filename in [(('tmin','tmax'), ['Tmin','Tmax'], 'revision_usefulness.png'),
                                      (('rh_min','rh_max'), ['RH minimum','RH maximum'], 'rh_revision_usefulness.png')]:
        plot_usefulness(folder, by_lead, metrics, titles, filename)
    primary = [r for r in overall if r['scope'] == 'consecutive_le24h' and r['denominator'] == 'changed_only']
    findings = '\n\n'.join(f"{r['metric']}: {r['usefulness_rate_pct']:.1f}% of {r['n_pairs']:,} changed forecasts moved closer to "
                            f"the realized observation; {100*r['n_worsened']/r['n_pairs']:.1f}% worsened and "
                            f"{100*r['n_tied']/r['n_pairs']:.1f}% tied. Mean absolute-error reduction "
                            f"{r['mean_absolute_error_reduction']:.3f} {'percentage points' if r['metric'].startswith('rh_') else '°C'}." for r in primary)
    report(3, 'Are forecast revisions useful?', findings,
           table(overall, ['scope','metric','denominator','n_pairs','usefulness_rate_pct','ci95_low_pct','ci95_high_pct','mean_absolute_error_reduction','error_reduction_unit']),
           'Each pair uses the same valid date, variable and HKO Headquarters observation. Temperature uses complete (`C`) numeric CSV values; '
           'RH uses validated daily-report HKOReadingsMinRH/MaxRH, not daily mean RH. Dates join to report_date, not bulletin_date. '
           '[HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. '
           'Primary pairs are adjacent archived vintages with gap≤24h and both leads 1–9. Benefit is earlier absolute error '
           'minus later absolute error; tolerance 1e−10 is used only for floating-point ties. '
           'Changed-only and all-pair rates are separately reported. Confidence intervals cluster by target date; '
           'lead breakdown and join exclusions are saved.',
           'Retrospective usefulness is not something the forecaster knew at issuance. Equal absolute errors can occur even '
           'when the forecast changes across the observed value. RH daily reports explicitly mark data as provisional with limited validation and have no CSV completeness flag. '
           'Numeric/date/range checks do not certify finalized climatological values; the RH verification target is HKO Headquarters, not a territory-wide humidity range. '
           'Lead 9 temperature has only seven changed pairs per variable in the primary scope and compares same-day boundary updates; '
           'consult by-lead RH counts separately. Serial dependence and archive capture are not corrected.')
    save_metadata(3, snapshot, {'n_pair_records': len(records), 'rh_extrema_usefulness': 'scored against validated daily JSON report extrema'})


def plot_usefulness(folder, by_lead, metrics, titles, filename):
    fig, axes = panels('RQ3 · Outcomes of changed forecasts', titles)
    for ax, metric in zip(axes, metrics):
        selected = [r for r in by_lead if r['scope'] == 'consecutive_le24h' and r['metric'] == metric and r['denominator'] == 'changed_only']
        x, bottom = [r['lead_days'] for r in selected], np.zeros(len(selected))
        for status, color, hatch in zip(('improved', 'worsened', 'tied'), (*COLORS[:2], '#999999'), ('', '//', '..')):
            values = np.array([100*r['n_'+status]/r['n_pairs'] for r in selected])
            ax.bar(x, values, bottom=bottom, color=color, hatch=hatch, label=status)
            bottom += values
        ax.set(xlabel='Later lead (days)', ylabel='Changed forecast pairs (%)', ylim=(0,100), xticks=range(1,10))
        for r in selected:
            ax.text(r['lead_days'],102,f"n={r['n_pairs']}",ha='center',fontsize=8)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.07),ncol=3,frameon=False)
    for ax in axes:
        ax.set_ylim(0,110)
        ax.set_yticks(range(0,101,20))
    save(fig, folder, filename, 'Only changed pairs; sample sizes above bars. Lead 9 is same-day boundary updating, not daily lead shortening.',bottom=.14)


if __name__ == '__main__':
    cli(3, analyze)
