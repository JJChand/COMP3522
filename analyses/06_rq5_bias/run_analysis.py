"""RQ5: signed bias by target season/year with dependence-aware intervals."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import cli, csv_output, group_rows, interval, report, result_dir, save_metadata, table
from common.plotting import COLORS, panels, save


def bias_summary(cases, keys, error_field='mean_error_c'):
    output = []
    for key, members in sorted(group_rows(cases, keys).items()):
        errors, dates = [r['error'] for r in members], [r['valid_date'] for r in members]
        low, high = interval(errors, dates)
        block_low, block_high = interval(errors, dates, block_days=7)
        output.append(dict(zip(keys, key)) | dict(
            n_forecasts=len(errors), n_target_dates=len(set(dates)), **{error_field:float(np.mean(errors))},
            date_cluster_ci95_low=low, date_cluster_ci95_high=high,
            calendar7day_block_ci95_low=block_low, calendar7day_block_ci95_high=block_high))
    return output


def analyze(snapshot):
    folder = result_dir(5)
    cases = snapshot.temperature_cases('daily_latest')
    overall = bias_summary(cases, ('metric',))
    leads = bias_summary(cases, ('metric','lead_days'))
    seasons = bias_summary(cases, ('metric','season'))
    years = bias_summary(cases, ('metric','year'))
    cross = bias_summary(cases, ('metric','season','year','lead_days'))
    for name, rows in [('bias_overall',overall), ('bias_by_lead',leads), ('bias_by_season',seasons),
                       ('bias_by_year',years), ('bias_by_season_year_lead',cross)]:
        csv_output(folder / (name+'.csv'), rows)
    csv_output(folder / 'all_vintage_bias_sensitivity.csv', bias_summary(snapshot.temperature_cases('all_vintages'), ('metric','lead_days')))
    humidity = [r for r in snapshot.verification_cases('daily_latest') if r['metric'].startswith('rh_')]
    humidity_outputs = {}
    for name, keys in [('bias_overall',('metric',)), ('bias_by_lead',('metric','lead_days')),
                       ('bias_by_season',('metric','season')), ('bias_by_year',('metric','year')),
                       ('bias_by_season_year_lead',('metric','season','year','lead_days'))]:
        humidity_outputs[name] = bias_summary(humidity,keys,'mean_error_pp')
        csv_output(folder / ('rh_'+name+'.csv'), humidity_outputs[name])
    csv_output(folder / 'rh_all_vintage_bias_sensitivity.csv', bias_summary(
        [r for r in snapshot.verification_cases('all_vintages') if r['metric'].startswith('rh_')],
        ('metric','lead_days'),'mean_error_pp'))
    plot_seasons(folder,humidity_outputs['bias_by_season'],('rh_min','rh_max'),['RH minimum','RH maximum'],
                 'mean_error_pp','percentage points','rh_seasonal_bias.png')
    fig, axes = panels('RQ5 · Signed bias by target season', ['Tmin', 'Tmax'])
    for ax, metric in zip(axes, ('tmin','tmax')):
        selected = [next(r for r in seasons if r['metric']==metric and r['season']==s) for s in ('DJF','MAM','JJA','SON')]
        y = [r['mean_error_c'] for r in selected]
        ax.errorbar(range(4), y, yerr=np.array([[r['mean_error_c']-r['calendar7day_block_ci95_low'] for r in selected],
                                             [r['calendar7day_block_ci95_high']-r['mean_error_c'] for r in selected]]),
                    color=COLORS[0], marker='o', linestyle='none', capsize=4)
        ax.axhline(0, color='#555555', linewidth=1)
        ax.set(xticks=range(4), xticklabels=('DJF','MAM','JJA','SON'), ylabel='Forecast − observation (°C)', xlabel='Target-date season')
    save(fig, folder, 'seasonal_bias.png', 'Bars: 95% bootstrap intervals over fixed 7-calendar-day blocks; positive means over-forecasting.')
    findings = '\n\n'.join(f"{r['metric']}: overall mean error {r['mean_error_c']:+.3f} °C; 7-day-block 95% interval "
                            f"[{r['calendar7day_block_ci95_low']:+.3f}, {r['calendar7day_block_ci95_high']:+.3f}]."
                            for r in overall)
    findings += '\n\n' + '\n\n'.join(f"{r['metric']}: overall mean error {r['mean_error_pp']:+.3f} percentage points; 7-day-block 95% interval "
                                     f"[{r['calendar7day_block_ci95_low']:+.3f}, {r['calendar7day_block_ci95_high']:+.3f}]."
                                     for r in humidity_outputs['bias_overall'])
    report(5, 'Systematic bias, season and year', findings + '\n\nPositive values mean over-forecasting; '
           'negative values mean under-forecasting. Seasonal and annual differences are descriptive, not causal changes in forecast quality.',
           '### Season\n\n' + table(seasons, ['metric','season','n_forecasts','mean_error_c','calendar7day_block_ci95_low','calendar7day_block_ci95_high']) +
           '\n\n### Year\n\n' + table(years, ['metric','year','n_forecasts','mean_error_c','calendar7day_block_ci95_low','calendar7day_block_ci95_high']) +
           '\n\n### RH season (percentage points)\n\n' + table(humidity_outputs['bias_by_season'], ['metric','season','n_forecasts','mean_error_pp','calendar7day_block_ci95_low','calendar7day_block_ci95_high']) +
           '\n\n### RH year (percentage points)\n\n' + table(humidity_outputs['bias_by_year'], ['metric','year','n_forecasts','mean_error_pp','calendar7day_block_ci95_low','calendar7day_block_ci95_high']),
           'Same HKO Headquarters target observations and daily-latest vintage rule as RQ4. Temperature uses complete (`C`) CSV observations; '
           'RH uses validated report-date HKOReadingsMinRH/MaxRH. [HKO definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37. '
           'Seasons use target months: DJF=December–February, MAM=March–May, JJA=June–August, SON=September–November. '
           'Year is target calendar year; DJF within a calendar year is not a continuous winter episode. '
           'Both target-date cluster and fixed 7-day calendar-block percentile intervals (1,000 draws, seed 3522) are exported. '
           'The cross-table controls descriptive comparisons for lead, season and year; all-vintage sensitivity is separate.',
           'Intervals are exploratory and not multiple-testing-adjusted. Fixed 7-day blocks approximate serial dependence; '
           'weather episodes can persist longer. Pooled seasonal/year bias can change with lead mix, so consult the cross-table. '
           'RH reports explicitly mark data as provisional with limited validation and lack CSV-style completeness flags; validation does not certify finalized values. '
           'The RH verification target is HKO Headquarters, not a territory-wide humidity range. Mean RH is never substituted for endpoints.')
    save_metadata(5, snapshot, {'main_selection': 'daily_latest', 'season_rule': 'target month DJF/MAM/JJA/SON',
                               'interval_blocks_days': [1,7], 'rh_extrema_bias_status': 'scored against validated daily JSON report extrema'})


def plot_seasons(folder, rows, metrics, titles, field, unit, filename):
    fig, axes = panels('RQ5 · Signed bias by target season', titles)
    for ax, metric in zip(axes, metrics):
        selected = [next(r for r in rows if r['metric']==metric and r['season']==s) for s in ('DJF','MAM','JJA','SON')]
        y = [r[field] for r in selected]
        ax.errorbar(range(4),y,yerr=np.array([[r[field]-r['calendar7day_block_ci95_low'] for r in selected],
                                            [r['calendar7day_block_ci95_high']-r[field] for r in selected]]),
                    color=COLORS[0],marker='o',linestyle='none',capsize=4)
        ax.axhline(0,color='#555555',linewidth=1)
        ax.set(xticks=range(4),xticklabels=('DJF','MAM','JJA','SON'),ylabel='Forecast − observation ('+unit+')',xlabel='Target-date season')
    save(fig,folder,filename,'Bars: 95% bootstrap intervals over fixed 7-calendar-day blocks; positive means over-forecasting.')


if __name__ == '__main__':
    cli(5, analyze)
