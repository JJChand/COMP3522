"""RQ6: fresh PSR verification against explicitly defined rainfall proxies."""
from collections import defaultdict
import csv
import hashlib
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import (ANALYSES, PSR_BANDS, PSR_CATEGORIES, cli, csv_output, daily_latest,
                          group_rows, interval, ratio, report, result_dir, save_metadata, table)
from common.plotting import COLORS, panels, save

WEIGHTS_FILE = ANALYSES / '01_rainfall/results/psr_area_weights.csv'


def rainfall_interval(row):
    if row['data_completeness'] != 'C':
        return None
    if row['value_numeric'] is not None:
        value = float(row['value_numeric'])
        if value < 0:
            raise ValueError('Negative rainfall')
        return value, value
    if row['value_text'] == 'Trace':
        return 0., .05  # upper limit used conservatively, not a replacement measurement
    return None


def rainfall_targets(snapshot):
    with WEIGHTS_FILE.open(encoding='utf-8', newline='') as handle:
        weights = list(csv.DictReader(handle))
    if len(weights) != 22 or len({r['observation_series_id'] for r in weights}) != 22:
        raise ValueError('Expected a unique 22-station rainfall weight panel')
    total = sum(float(r['weight']) for r in weights)
    if abs(total-1) > 1e-6:
        raise ValueError('Saved spatial weights do not sum to one')
    by_id = {r['observation_series_id']: r for r in snapshot.series}
    stations = {r['station_code']: r for r in snapshot.stations}
    weight_map = {}
    for r in weights:
        series_id = int(r['observation_series_id'])
        if series_id not in by_id or by_id[series_id]['station_name'] != r['station_name']:
            raise ValueError('Saved rainfall weights do not match this database series')
        if stations[r['station_code']]['station_name'] != r['station_name']:
            raise ValueError('Saved station code/name mismatch')
        if by_id[series_id]['series_code'] not in ('obs_hko_daily_rainfall','obs_spatial_daily_rainfall'):
            raise ValueError('Weight is attached to a non-rainfall series')
        weight_map[series_id] = float(r['weight']) / total
    daily = defaultdict(dict)
    for row in snapshot.observations:
        if row['observation_series_id'] in weight_map:
            daily[row['observation_date']][row['observation_series_id']] = rainfall_interval(row)
    targets = {k: {} for k in ('area_weighted_22','station_mean_22','hko_point')}
    counts = dict(n_panel_stations=len(weights), n_days_with_panel_records=len(daily),
                  n_complete_panel_days=0, n_area_trace_ambiguous=0, n_mean_trace_ambiguous=0,
                  saved_weight_sum=total, weights_sha256=hashlib.sha256(WEIGHTS_FILE.read_bytes()).hexdigest())
    for target, readings in sorted(daily.items()):
        if len(readings) != len(weights) or any(v is None for v in readings.values()):
            continue
        counts['n_complete_panel_days'] += 1
        for kind, wmap in (('area_weighted_22',weight_map), ('station_mean_22',dict.fromkeys(weight_map,1/len(weights)))):
            lower = sum(wmap[k]*v[0] for k,v in readings.items())
            upper = sum(wmap[k]*v[1] for k,v in readings.items())
            if lower < 10 <= upper:
                counts['n_area_trace_ambiguous' if kind=='area_weighted_22' else 'n_mean_trace_ambiguous'] += 1
                continue
            targets[kind][target] = int(lower >= 10)
    for row in snapshot.observations:
        if row['series_code'] == 'obs_hko_daily_rainfall':
            bounds = rainfall_interval(row)
            if bounds and not bounds[0] < 10 <= bounds[1]:
                targets['hko_point'][row['observation_date']] = int(bounds[0] >= 10)
    return targets, counts, weights


def brier_bounds(category, event):
    lo, hi = PSR_BANDS[category]
    return min((lo-event)**2, (hi-event)**2), max((lo-event)**2, (hi-event)**2)


def confusion(events, alarms):
    tp = sum(bool(y) and bool(a) for y,a in zip(events,alarms))
    fp = sum(not y and bool(a) for y,a in zip(events,alarms))
    fn = sum(bool(y) and not a for y,a in zip(events,alarms))
    tn = len(events)-tp-fp-fn
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, hit_rate=ratio(tp,tp+fn),
                false_alarm_ratio=ratio(fp,tp+fp), false_positive_rate=ratio(fp,fp+tn))


def analyze(snapshot):
    folder = result_dir(6)
    targets, quality, weights = rainfall_targets(snapshot)
    cases = []
    eligible = [r for r in daily_latest(snapshot.forecasts) if 1 <= r['lead_days'] <= 9 and r['psr'] in PSR_BANDS]
    for proxy, labels in targets.items():
        for row in eligible:
            target = row['valid_date']
            if target not in labels:
                continue
            lo, hi = PSR_BANDS[row['psr']]
            probability = (lo+hi)/2
            event = labels[target]
            minimum, maximum = brier_bounds(row['psr'], event)
            cases.append(dict(proxy=proxy, valid_date=target, category=row['psr'], event=event,
                              lead_days=row['lead_days'], lead_group='1-3' if row['lead_days']<=3 else '4-6' if row['lead_days']<=6 else '7-9',
                              midpoint_p=probability, midpoint_bs=(probability-event)**2,
                              lower_endpoint_bs=(lo-event)**2, upper_endpoint_bs=(hi-event)**2,
                              bs_lower_bound=minimum, bs_upper_bound=maximum))
    reliability = []
    for keys in (('proxy','category'), ('proxy','lead_group','category')):
        for key, members in sorted(group_rows(cases, keys).items()):
            category = members[0]['category']
            lo, hi = PSR_BANDS[category]
            ci_lo, ci_hi = interval([r['event'] for r in members], [r['valid_date'] for r in members])
            rate = float(np.mean([r['event'] for r in members]))
            reliability.append(dict(proxy=members[0]['proxy'], lead_group=members[0]['lead_group'] if 'lead_group' in keys else 'all',
                                    category=category, forecast_band_low=lo, forecast_band_high=hi, midpoint_p=(lo+hi)/2,
                                    n_forecasts=len(members), n_target_dates=len({r['valid_date'] for r in members}),
                                    n_events=sum(r['event'] for r in members), event_rate=rate, ci95_low=ci_lo, ci95_high=ci_hi,
                                    rate_within_band=lo <= rate <= hi if hi==1 else lo <= rate < hi))
    scores, contingencies = [], []
    for keys in (('proxy',), ('proxy','lead_group')):
        for key, members in sorted(group_rows(cases, keys).items()):
            scores.append(dict(proxy=members[0]['proxy'], lead_group=members[0]['lead_group'] if 'lead_group' in keys else 'all',
                               n_forecasts=len(members), event_rate=float(np.mean([r['event'] for r in members])),
                               **{field: float(np.mean([r[field] for r in members])) for field in
                                  ('midpoint_bs','lower_endpoint_bs','upper_endpoint_bs','bs_lower_bound','bs_upper_bound')}))
            for alarm_category in ('Medium','Medium High','High'):
                alarms = [PSR_CATEGORIES.index(r['category']) >= PSR_CATEGORIES.index(alarm_category) for r in members]
                contingencies.append(dict(proxy=members[0]['proxy'], lead_group=members[0]['lead_group'] if 'lead_group' in keys else 'all',
                                          alarm_rule=alarm_category+'_or_higher', n_forecasts=len(members),
                                          **confusion([r['event'] for r in members],alarms)))
    coverage = [dict(proxy=k,n_target_dates=len(v), n_events=sum(v.values()),
                     n_matched_forecasts=sum(r['proxy']==k for r in cases), n_candidate_forecasts=len(eligible),
                     n_unmatched_forecasts=len(eligible)-sum(r['proxy']==k for r in cases)) for k,v in targets.items()]
    csv_output(folder/'reliability.csv', reliability)
    csv_output(folder/'brier_scores.csv', scores)
    csv_output(folder/'contingency_tables.csv', contingencies)
    csv_output(folder/'target_coverage.csv', coverage)
    csv_output(folder/'validated_area_weights.csv',weights)
    fig, axes = panels('RQ6 · PSR rainfall-proxy reliability', ['Area-weighted 22 stations', 'Unweighted 22 stations'])
    for ax, proxy in zip(axes, ('area_weighted_22','station_mean_22')):
        selected = sorted((r for r in reliability if r['proxy']==proxy and r['lead_group']=='all'), key=lambda r:r['midpoint_p'])
        x, y = np.array([r['midpoint_p'] for r in selected])*100, np.array([r['event_rate'] for r in selected])*100
        ax.errorbar(x,y, yerr=np.array([[100*(r['event_rate']-r['ci95_low']) for r in selected],
                                     [100*(r['ci95_high']-r['event_rate']) for r in selected]]),
                    xerr=np.array([[100*(r['midpoint_p']-r['forecast_band_low']) for r in selected],
                                   [100*(r['forecast_band_high']-r['midpoint_p']) for r in selected]]),
                    color=COLORS[0], fmt='o', capsize=3)
        ax.plot([0,100],[0,100], color='#555555',linestyle='--',linewidth=1)
        ax.set(xlabel='Published PSR band / midpoint (%)',ylabel='Observed proxy event rate (%)',xlim=(0,100),ylim=(0,100))
    save(fig,folder,'psr_reliability.png', 'Horizontal bars: published category ranges. Vertical bars: 95% target-date cluster intervals. Neither proxy is an exact territory event.')
    primary = [r for r in reliability if r['proxy']=='area_weighted_22' and r['lead_group']=='all']
    bs = next(r for r in scores if r['proxy']=='area_weighted_22' and r['lead_group']=='all')
    out_of_band = [r['category'] for r in primary if not r['rate_within_band']]
    findings = f"The area-weighted proxy has {len(targets['area_weighted_22']):,} usable target days. "
    findings += f"Observed frequencies fall outside the published bands for: {', '.join(out_of_band) if out_of_band else 'none of the five categories'}. "
    findings += f"Midpoint-coded Brier score is {bs['midpoint_bs']:.4f}; the compatible per-case probability-band bounds are "
    findings += f"[{bs['bs_lower_bound']:.4f}, {bs['bs_upper_bound']:.4f}], which are not confidence intervals. "
    findings += 'These results concern the defined rainfall proxy, so they do not alone establish calibration or miscalibration of the exact HKO event.'
    report(6,'PSR calibration and event verification',findings,
           table(primary,['category','n_forecasts','event_rate','forecast_band_low','forecast_band_high','ci95_low','ci95_high']) +
           '\n\n### Categorical alarm verification (area proxy)\n\n'+table(
               [r for r in contingencies if r['proxy']=='area_weighted_22' and r['lead_group']=='all'],
               ['alarm_rule','tp','fp','fn','tn','hit_rate','false_alarm_ratio']),
           'HKO defines significant rain using daily rainfall reaching 10 mm broadly across Hong Kong and publishes five probability bands. '
           '[HKO product definitions](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm?tablenote=true). '
           'Primary proxy: weighted daily station mean ≥10 mm, using the existing 22-station land-clipped Voronoi weights. '
           'Their IDs/names/codes and weight sum are verified against the live catalog; the weight file checksum is saved. '
           'Only days with all 22 complete numeric/Trace records qualify. Trace is [0,0.05) mm; ambiguous threshold outcomes are excluded, '
           'not filled with invented measurements. Station-mean and HKO-point sensitivities are separate. '
           'Brier score = mean((p−event)²); category midpoints are an explicit coding assumption. Lower/upper endpoint codings and '
           'infimum/supremum bounds over unpublished per-case probabilities are exported. Alarms are categorical thresholds, '
           'not claims that every Medium forecast has p≥0.5. Hit rate=TP/(TP+FN); false alarm ratio=FP/(TP+FP), '
           'distinct from false-positive rate=FP/(FP+TN).',
           'A station-area weighted average is an approximation to the territorial rainfall event, not its official verification label. '
           'Station availability and exclusion can select different weather conditions. The saved weights use a prior land geometry and rounded '
           'weights are normalized after a tight sum check, not recomputed from fresh geometry. Reliability depends on lead and target definition. '
           'Brier bounds are partial identification of the missing numeric probabilities, not recommended outcome-aware forecasts. '
           'A headline midpoint score must retain its coding assumption. Date clusters do not address inter-date serial dependence. '
           'The separate retained-report [rainfall source audit](rainfall_report_audit.json) does not resolve territorial labels: '
           'daily JSON rainfall matches the HKO-point CSV on all 1,223 numeric comparisons. Accumulated rainfall is year-to-date, '
           'and the average field has a cumulative-like annual trajectory, not daily rainfall. Neither is a valid daily territorial substitute.')
    save_metadata(6,snapshot,{'rainfall_quality':quality,'probability_coding':'continuous band midpoint',
                             'rainfall_targets':'area weighted, station mean, HKO point separately'})


if __name__ == '__main__':
    cli(6,analyze)
