"""RQ4: like-for-like temperature and validated daily-report RH scoring."""
from datetime import date, timedelta
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import (TEMP_CODES, cli, csv_output, daily_latest, group_rows, interval,
                          metric_summary, report, result_dir, save_metadata, table)
from common.plotting import COLORS, panels, save


def calendar_index(target):
    # A leap reference year preserves month/day alignment after February.
    return (date(2000, target.month, target.day) - date(2000, 1, 1)).days


def fit_climatology(observed):
    training = [(d, value) for d, value in observed.items() if date(1991,1,1) <= d < date(2021,1,1)]
    bins = {}
    for day in range(366):
        samples = [v for d, v in training if min(abs(calendar_index(d)-day), 366-abs(calendar_index(d)-day)) <= 2]
        if len(samples) < 50:
            raise ValueError('Insufficient frozen climatology history')
        bins[day] = {'mean': float(np.mean(samples)), 'median': float(np.median(samples)), 'n_training': len(samples)}
    return bins, len(training)


def rh_distance(mean, lower, upper):
    """Distance of an observed mean outside a forecast extrema range, not endpoint error."""
    return max(lower-mean, mean-upper, 0.)


def rh_cases(snapshot):
    mean_rh = snapshot.observed('obs_hko_daily_mean_rh')
    cases = []
    for r in daily_latest(snapshot.forecasts):
        if not 1 <= r['lead_days'] <= 9 or r['valid_date'] not in mean_rh:
            continue
        lower, upper = r['forecast_rh_min_pct'], r['forecast_rh_max_pct']
        if lower is None or upper is None:
            continue
        actual = mean_rh[r['valid_date']]
        cases.append(dict(valid_date=r['valid_date'], lead_days=r['lead_days'],
                          below=actual < lower, above=actual > upper,
                          outside_distance_pp=rh_distance(actual, float(lower), float(upper))))
    return cases


def fit_rh_climatology(observed):
    """Freeze 2022 ±15-calendar-day RH means/medians; verify only 2023–2025."""
    training = [(d,v) for d,v in observed.items() if date(2022,1,1) <= d < date(2023,1,1)]
    bins = {}
    for day in range(366):
        samples = [v for d,v in training if min(abs(calendar_index(d)-day),366-abs(calendar_index(d)-day)) <= 15]
        if len(samples) < 25:
            raise ValueError('Insufficient frozen 2022 RH reference history')
        bins[day] = dict(mean=float(np.mean(samples)),median=float(np.median(samples)),n_training=len(samples))
    return bins,len(training)


def score_rh(snapshot,folder):
    observed = snapshot.rh_observed()
    climate = {m:fit_rh_climatology(v) for m,v in observed.items()}
    csv_output(folder/'rh_climatology_calendar_day.csv',[
        dict(metric=m,reference_day_index=k,**v) for m,(bins,_) in climate.items() for k,v in bins.items()])
    output, skills = [],[]
    for selection in ('daily_latest','all_vintages'):
        cases = [r for r in snapshot.verification_cases(selection) if r['metric'].startswith('rh_')]
        for (metric,lead), members in sorted(group_rows(cases,('metric','lead_days')).items()):
            stats = metric_summary([r['error'] for r in members])
            lo,hi = interval([abs(r['error']) for r in members],[r['valid_date'] for r in members])
            output.append(dict(selection=selection,metric=metric,lead_days=lead,unit='percentage_points',**stats,
                               n_target_dates=len({r['valid_date'] for r in members}),mae_ci95_low=lo,mae_ci95_high=hi))
            for baseline in ('climatology_mean_2022','climatology_median_2022','persistence_lag2','persistence_lag1'):
                paired=[]
                for row in members:
                    target=row['valid_date']
                    if baseline.startswith('climatology'):
                        if target < date(2023,1,1):
                            continue  # Never score the frozen reference on its training year.
                        reference=climate[metric][0][calendar_index(target)]['mean' if 'mean' in baseline else 'median']
                    else:
                        lag=2 if baseline.endswith('2') else 1
                        past=row['bulletin_time_hkt'].date()-timedelta(days=lag)
                        if past >= row['bulletin_time_hkt'].date() or past >= target:
                            raise ValueError('RH persistence date leakage')
                        reference=observed[metric].get(past)
                        if reference is None:
                            continue
                    paired.append((row['error'],reference-row['observed']))
                forecast=metric_summary([f for f,b in paired])
                reference=metric_summary([b for f,b in paired])
                skills.append(dict(selection=selection,metric=metric,lead_days=lead,baseline=baseline,
                                   unit='percentage_points',n_matched=len(paired),n_excluded=len(members)-len(paired),
                                   forecast_mae=forecast['mae'],baseline_mae=reference['mae'],forecast_rmse=forecast['rmse'],baseline_rmse=reference['rmse'],
                                   mae_skill=1-forecast['mae']/reference['mae'] if reference['mae'] else None,
                                   mse_skill=1-forecast['rmse']**2/reference['rmse']**2 if reference['rmse'] else None,
                                   verification_period='2023–2025' if baseline.startswith('climatology') else '2022–2025, available lagged dates only',
                                   availability='frozen_2022_reference_not_30_year_climatology' if baseline.startswith('climatology') else 'retrospective_past_day_proxy_not_certified_operational'))
    csv_output(folder/'rh_accuracy_by_lead.csv',output)
    csv_output(folder/'rh_baseline_skill_by_lead.csv',skills)
    fig,axes=panels('RQ4 · HKO relative-humidity forecast errors',['RH minimum','RH maximum'])
    for ax,metric in zip(axes,('rh_min','rh_max')):
        rows=[r for r in output if r['selection']=='daily_latest' and r['metric']==metric]
        x=[r['lead_days'] for r in rows]
        for field,color,marker in zip(('mae','rmse'),COLORS,('o','s')):
            ax.plot(x,[r[field] for r in rows],color=color,marker=marker,label=field.upper())
        ax.fill_between(x,[r['mae_ci95_low'] for r in rows],[r['mae_ci95_high'] for r in rows],color=COLORS[0],alpha=.15)
        ax.set(xlabel='Lead (calendar days)',ylabel='RH error (percentage points)',xticks=range(1,10))
        ax.legend(frameon=False)
    axes[0].set_ylim(0,1.1*max(r['rmse'] for r in output if r['selection']=='daily_latest'))
    save(fig,folder,'rh_accuracy.png','HKO daily-report extrema; latest archived per target/issue day. Shading: 95% target-date cluster MAE interval.')
    return output,skills


def analyze(snapshot):
    folder = result_dir(4)
    rh_accuracy,rh_skills=score_rh(snapshot,folder)
    observed = {m: snapshot.observed(c) for m, c in TEMP_CODES.items()}
    climate = {m: fit_climatology(values) for m, values in observed.items()}
    csv_output(folder / 'climatology_calendar_day.csv', [
        dict(metric=m, reference_day_index=k, **v) for m, (bins, _) in climate.items() for k,v in bins.items()])
    output, scoring_records = [], []
    for selection in ('daily_latest', 'all_vintages'):
        cases = snapshot.temperature_cases(selection)
        for row in cases:
            m, target = row['metric'], row['valid_date']
            # Compare strictly past observations, never a target-day value.
            issue_day = row['bulletin_time_hkt'].date()
            lag2, lag1 = issue_day-timedelta(days=2), issue_day-timedelta(days=1)
            norm = climate[m][0][calendar_index(target)]
            row['climatology_mean_error'] = norm['mean'] - row['observed']
            row['climatology_median_error'] = norm['median'] - row['observed']
            row['persistence_lag2_error'] = observed[m].get(lag2, np.nan) - row['observed']
            row['persistence_lag1_error'] = observed[m].get(lag1, np.nan) - row['observed']
            row['baseline_day_lag2'] = lag2
            if lag2 >= issue_day or lag1 >= issue_day or lag2 >= target:
                raise ValueError('Baseline date leakage')
        scoring_records.extend(cases)
        for (metric, lead), members in sorted(group_rows(cases, ('metric','lead_days')).items()):
            errors = [r['error'] for r in members]
            stats = metric_summary(errors)
            lo, hi = interval(np.abs(errors), [r['valid_date'] for r in members])
            output.append(dict(selection=selection, metric=metric, lead_days=lead, **stats,
                               n_target_dates=len({r['valid_date'] for r in members}), mae_ci95_low=lo, mae_ci95_high=hi))
    skills = []
    for (selection, metric, lead), members in sorted(group_rows(scoring_records, ('selection','metric','lead_days')).items()):
        for baseline in ('climatology_mean','climatology_median','persistence_lag2','persistence_lag1'):
            eligible = [r for r in members if np.isfinite(r[baseline+'_error'])]
            forecast_stats = metric_summary([r['error'] for r in eligible])
            baseline_stats = metric_summary([r[baseline+'_error'] for r in eligible])
            mae_ref, mse_ref = baseline_stats['mae'], baseline_stats['rmse'] ** 2 if eligible else None
            skills.append(dict(selection=selection, metric=metric, lead_days=lead, baseline=baseline,
                               n_matched=len(eligible), n_missing_baseline=len(members)-len(eligible),
                               forecast_mae=forecast_stats['mae'], baseline_mae=mae_ref,
                               forecast_rmse=forecast_stats['rmse'], baseline_rmse=baseline_stats['rmse'],
                               mae_skill=1-forecast_stats['mae']/mae_ref if mae_ref else None,
                               mse_skill=1-forecast_stats['rmse']**2/mse_ref if mse_ref else None,
                               availability='frozen_pre_study_climatology' if baseline.startswith('climatology') else 'retrospective_past_day_proxy_publication_unverified'))
    rh = []
    for (lead,), members in sorted(group_rows(rh_cases(snapshot), ('lead_days',)).items()):
        violations = [int(r['below'] or r['above']) for r in members]
        rh.append(dict(lead_days=lead, n_cases=len(members), n_outside=sum(violations),
                       outside_rate_pct=100*np.mean(violations), n_below_forecast_min=sum(r['below'] for r in members),
                       n_above_forecast_max=sum(r['above'] for r in members),
                       mean_outside_distance_pp=float(np.mean([r['outside_distance_pp'] for r in members])),
                       interpretation='mean-RH consistency only; not extrema MAE/RMSE'))
    csv_output(folder / 'temperature_accuracy_by_lead.csv', output)
    csv_output(folder / 'baseline_skill_by_lead.csv', skills)
    csv_output(folder / 'rh_range_consistency_by_lead.csv', rh)
    csv_output(folder / 'variable_feasibility.csv', [
        dict(variable='Tmin/Tmax', comparable_observations=True, observation='HKO daily extrema', status='MAE/RMSE scored'),
        dict(variable='RH min/max', comparable_observations=True, observation='HKOReadingsMinRH/MaxRH daily JSON report', status='MAE/RMSE scored; no CSV completeness flag')])
    fig, axes = panels('RQ4 · HKO temperature forecast errors', ['Tmin', 'Tmax'])
    for ax, metric in zip(axes, ('tmin','tmax')):
        selected = [r for r in output if r['selection']=='daily_latest' and r['metric']==metric]
        x = [r['lead_days'] for r in selected]
        for field, color, marker in zip(('mae','rmse'), COLORS, ('o','s')):
            ax.plot(x, [r[field] for r in selected], color=color, marker=marker, label=field.upper())
        ax.fill_between(x, [r['mae_ci95_low'] for r in selected], [r['mae_ci95_high'] for r in selected], color=COLORS[0], alpha=.15)
        ax.set(xlabel='Lead (calendar days)', ylabel='Temperature error (°C)', ylim=(0,None), xticks=range(1,10))
        ax.legend(frameon=False)
    axes[0].set_ylim(0,1.1*max(r['rmse'] for r in output if r['selection']=='daily_latest'))
    save(fig, folder, 'temperature_accuracy.png', 'Latest archived per target/issue day; shading is the 95% target-date cluster interval for MAE only.')
    primary = [r for r in output if r['selection']=='daily_latest' and r['lead_days'] in (1,3,6,9)]
    findings = '\n\n'.join(f"{metric}: daily-latest MAE rises from "
                            f"{next(r['mae'] for r in primary if r['metric']==metric and r['lead_days']==1):.3f} °C at lead 1 to "
                            f"{next(r['mae'] for r in primary if r['metric']==metric and r['lead_days']==9):.3f} °C at lead 9."
                            for metric in TEMP_CODES)
    rh_primary=[r for r in rh_accuracy if r['selection']=='daily_latest' and r['lead_days'] in (1,3,6,9)]
    findings+='\n\n'+'\n\n'.join(f"{metric}: daily-latest MAE rises from "
                 f"{next(r['mae'] for r in rh_primary if r['metric']==metric and r['lead_days']==1):.3f} percentage points at lead 1 to "
                 f"{next(r['mae'] for r in rh_primary if r['metric']==metric and r['lead_days']==9):.3f} at lead 9." for metric in ('rh_min','rh_max'))
    report(4, 'Accuracy across lead days and reference forecasts', findings + '\n\nRH extrema are scored against validated daily JSON reports. '
           'The separate mean-RH diagnostic measures whether the observed daily mean falls outside the forecast minimum/maximum range; '
           'an inside-range mean does not establish correct extrema.',
           table(primary, ['metric','lead_days','n','mae','rmse','mae_ci95_low','mae_ci95_high']) +
           '\n\n### RH endpoint accuracy (percentage points)\n\n'+table(rh_primary,['metric','lead_days','n','mae','rmse','mae_ci95_low','mae_ci95_high'])+
           '\n\n### RH matched baseline skill\n\n'+table([r for r in rh_skills if r['selection']=='daily_latest' and r['lead_days'] in (1,9) and r['baseline'] in ('climatology_mean_2022','persistence_lag2')],
                    ['metric','lead_days','baseline','verification_period','n_matched','mae_skill','mse_skill'])+
           '\n\n### RH mean consistency, not endpoint accuracy\n\n' +
           table(rh, ['lead_days','n_cases','outside_rate_pct','mean_outside_distance_pp'])+
           '\n\n### Matched baseline skill (positive means lower error than reference)\n\n'+
           table([r for r in skills if r['selection']=='daily_latest' and r['lead_days'] in (1,9)
                  and r['baseline'] in ('climatology_mean','persistence_lag2')],
                 ['metric','lead_days','baseline','n_matched','forecast_mae','baseline_mae','mae_skill','mse_skill']),
           'Temperature uses complete (`C`) HKO Headquarters daily CSV observations; RH uses validated HKOReadingsMinRH/MaxRH JSON report values, joined on report_date. '
           '[HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. Positive leads 1–9. Main selection is latest archived per target/issue date; '
           'all-vintage scoring is a sensitivity. Frozen climatology pools 1991–2020 observations within ±2 calendar days using leap-reference '
           'month/day alignment; mean and median references are both exported. Training ends before the study. '
           'Persistence uses issue-day-minus-2 (primary retrospective proxy) and minus-1 (sensitivity). Skill is '
           '1−MAE_forecast/MAE_reference and 1−MSE_forecast/MSE_reference, calculated on identical eligible cases, not unmatched averages. '
           'RH has no 1991–2020 extrema history in the local dataset. Its separate frozen 2022 ±15-calendar-day mean/median seasonal reference is scored only on 2023–2025, never on its training year. '
           'It is a one-year reference, not a 30-year climatological normal and is not directly comparable to the temperature baseline. '
           'Climatology calendar aggregates and all baseline scores are saved.',
           'Historical observation publication times are absent, so persistence skill is not proven operationally available even with a two-day lag. '
           'Lead 9 may use an earlier issue-day bulletin than other targets because the product window changes within a day. '
           'Mean RH is not minimum/maximum RH. A positive outside-distance is a lower bound on at least one extrema error, but zero is not an accuracy score. '
           'RH reports explicitly mark displayed data as provisional with limited validation and have no CSV completeness flag. '
           'Range/date validation does not certify finalized values. The RH verification target is HKO Headquarters, not a territory-wide humidity range. '
           'Sampling intervals do not correct inter-date serial dependence.')
    save_metadata(4, snapshot, {'climatology_training': '1991-01-01 <= date < 2021-01-01',
                               'training_complete_days': {m: n for m, (_,n) in climate.items()},
                               'rh_extrema_scoring_status': 'scored against validated daily JSON report extrema',
                               'rh_reference_training': '2022 only; ±15 calendar days; reference verification 2023–2025 only',
                               'persistence_publication_status': 'unverified; retrospective comparator only'})


if __name__ == '__main__':
    cli(4, analyze)
