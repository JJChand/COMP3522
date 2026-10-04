"""RQ7: post-event factor associations, stratified contrasts and linear SHAP."""
from collections import defaultdict
from datetime import timedelta
import math
from pathlib import Path
import re
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.task1 import (START, END, METRICS, TEMP_CODES, REPLICATES, SEED,
                          cli, csv_output, group_rows, report, result_dir,
                          revision_pairs, save_metadata, season, table)
from common.plotting import COLORS, plt, save

# Fixed geographic panel, selected without reference to forecast error.
PANEL = ('Hong Kong International Airport', "King's Park", 'Sheung Shui',
         'Shau Kei Wan', 'Sha Tin', 'Ta Kwu Ling', 'Tai Mo Shan', 'Waglan Island')


def regime(text):
    """Narrative mention proxy, NOT a target-day synoptic/event classification."""
    if not text or not text.strip():
        return 'missing'
    text = text.lower()
    if re.search(r'\b(tropical cyclone|typhoon|tropical storm|tropical depression)\b', text):
        return 'cyclone_mention'
    if re.search(r'\btrough\b', text):
        return 'trough_mention'
    if re.search(r'\bmonsoon\b', text):
        return 'monsoon_mention'
    return 'other'


def factor_data(snapshot):
    readings = defaultdict(dict)
    for row in snapshot.observations:
        if row['data_completeness'] == 'C' and row['value_numeric'] is not None:
            readings[row['observation_series_id']][row['observation_date']] = float(row['value_numeric'])
    spreads, audit = {}, []
    for metric in TEMP_CODES:
        ids = []
        for name in PANEL:
            variants = [r for r in snapshot.series if r['series_code']=='obs_spatial_daily_temperature'
                        and r['station_name']==name
                        and ('minimum' if metric=='tmin' else 'maximum') in r['metric_name'].lower()]
            if len(variants) != 1:
                raise ValueError(f'Expected one {metric} series for panel station {name}; found {len(variants)}')
            series = variants[0]
            matching = [r for r in snapshot.stations if r['station_name']==name]
            if len(matching) != 1:
                raise ValueError('Unverified exact station mapping: ' + name)
            sid = series['observation_series_id']
            ids.append(sid)
            audit.append(dict(metric=metric, station_name=name, observation_series_id=sid,
                              source_file_id=series['source_file_id'], station_code=matching[0]['station_code'],
                              latitude=matching[0]['latitude'], longitude=matching[0]['longitude'],
                              numeric_complete_days=sum(START<=d<END for d in readings[sid])))
        shared = set.intersection(*(set(readings[sid]) for sid in ids))
        spreads[metric] = {d: max(readings[sid][d] for sid in ids)-min(readings[sid][d] for sid in ids)
                           for d in shared if START<=d<END}
    rain = {}
    for row in snapshot.observations:
        if row['series_code'] != 'obs_hko_daily_rainfall' or row['data_completeness'] != 'C':
            continue
        if row['value_numeric'] is not None:
            rain[row['observation_date']] = int(float(row['value_numeric'])>=10)
        elif row['value_text']=='Trace':
            # Classification only: a trace cannot cross 10 mm; do not invent an amount.
            rain[row['observation_date']] = 0
    observed = {m: snapshot.observed(c) for m,c in TEMP_CODES.items()}
    factors = {}
    for m in TEMP_CODES:
        factors[m] = {d: dict(rain10=rain[d], temp_change=abs(v-observed[m][d-timedelta(days=1)]),
                              spatial_spread=spreads[m][d], season=season(d), year=d.year)
                      for d,v in observed[m].items()
                      if START<=d<END and d in rain and d in spreads[m] and d-timedelta(days=1) in observed[m]}
    return factors, audit


def outcome_cases(snapshot, factors):
    output, coverage = [], []
    candidates = defaultdict(list)
    for r in snapshot.temperature_cases():
        candidates[(r['metric'], 'absolute_error')].append(dict(r, outcome=abs(r['error'])))
    for pair in revision_pairs(snapshot.forecasts, 'daily_latest'):
        r,a = pair['later'],pair['earlier']
        for m in TEMP_CODES:
            if r[METRICS[m]] is not None and a[METRICS[m]] is not None:
                candidates[(m, 'absolute_revision')].append(dict(r, metric=m,
                    outcome=abs(float(r[METRICS[m]])-float(a[METRICS[m]])), elapsed_hours=pair['elapsed_hours']))
    for (m,kind), rows in sorted(candidates.items()):
        kept = []
        for row in rows:
            d = row['valid_date']
            if d not in factors[m] or regime(row['general_situation'])=='missing':
                continue
            kept.append(dict(row, **factors[m][d], regime=regime(row['general_situation']), outcome_kind=kind))
        output.extend(kept)
        coverage.append(dict(metric=m, outcome_kind=kind, eligible_cases=len(rows), matched_cases=len(kept),
                             excluded_cases=len(rows)-len(kept), matched_dates=len({r['valid_date'] for r in kept}),
                             source_dates=len({r['valid_date'] for r in rows})))
    return output, coverage


def stratified_contrast(rows, factor, label, reference, strata):
    """Fixed common-support stratum weights; 7-day cluster percentile intervals."""
    grouped = defaultdict(lambda: [[], []])
    for row in rows:
        if row[factor] not in (label, reference):
            continue
        grouped[tuple(row[k] for k in strata)][int(row[factor]==label)].append(row)
    eligible = {key: groups for key,groups in grouped.items()
                if all(len({r['valid_date'] for r in g})>=10 for g in groups)}
    base = dict(factor=factor, comparison=str(label), reference=str(reference),
                strata='+'.join(strata), n_supported_strata=len(eligible),
                n_cases=sum(len(g) for v in eligible.values() for g in v),
                mean_difference_c=None, ci95_low=None, ci95_high=None,
                ci_excludes_zero=None, valid_bootstrap_replicates=0)
    if not eligible:
        return base
    blocks = sorted({(r['valid_date']-START).days//7 for v in eligible.values() for g in v for r in g})
    positions = {b:i for i,b in enumerate(blocks)}
    packed = np.zeros((len(blocks), len(eligible), 2, 2))
    for j,groups in enumerate(eligible.values()):
        for side, records in enumerate(groups):
            for row in records:
                b = positions[(row['valid_date']-START).days//7]
                packed[b,j,side] += (row['outcome'], 1)
    original = packed.sum(axis=0)
    weights = original[:,:,1].sum(axis=1)
    weights /= weights.sum()
    base['mean_difference_c'] = float(weights @ (original[:,1,0]/original[:,1,1]-original[:,0,0]/original[:,0,1]))
    rng = np.random.default_rng(SEED)
    boot = []
    for offset in range(0, REPLICATES, 20):
        draw = rng.integers(0,len(blocks),size=(min(20,REPLICATES-offset),len(blocks)))
        sampled = packed[draw].sum(axis=1)
        valid = np.all(sampled[:,:,:,1]>0,axis=(1,2))
        selected = sampled[valid]
        boot.extend((selected[:,:,1,0]/selected[:,:,1,1]-selected[:,:,0,0]/selected[:,:,0,1]) @ weights)
    base['valid_bootstrap_replicates'] = len(boot)
    if len(boot)>=900:
        lo,hi = np.quantile(boot,[.025,.975])
        base.update(ci95_low=float(lo),ci95_high=float(hi),ci_excludes_zero=bool(lo>0 or hi<0))
    return base


def design(rows, revision=False):
    names = ['intercept','rain10','temp_change','spatial_spread','calendar_year_trend']
    names += [f'lead_{i}' for i in range(2,10)]
    names += ['season_MAM','season_JJA','season_SON']
    names += ['regime_cyclone_mention','regime_trough_mention','regime_monsoon_mention']
    if revision:
        names.append('elapsed_hours')
    data = []
    for r in rows:
        v = [1, r['rain10'],r['temp_change'],r['spatial_spread'],r['year']-2022]
        v += [int(r['lead_days']==i) for i in range(2,10)]
        v += [int(r['season']==s) for s in ('MAM','JJA','SON')]
        v += [int(r['regime']==s) for s in ('cyclone_mention','trough_mention','monsoon_mention')]
        if revision:
            v.append(r['elapsed_hours'])
        data.append(v)
    return np.asarray(data,float),names


def fit_cluster_ols(x, y, dates):
    beta,_,rank,_ = np.linalg.lstsq(x,y,rcond=None)
    if rank != x.shape[1]:
        raise ValueError('Rank-deficient retained regression design')
    residual = y-x@beta
    scores = defaultdict(lambda: np.zeros(x.shape[1]))
    for a,e,d in zip(x,residual,dates):
        scores[(d-START).days//7] += a*e
    g,n,p = len(scores),len(y),x.shape[1]
    if g<=1 or n<=p:
        raise ValueError('Insufficient independent blocks for covariance')
    bread = np.linalg.inv(x.T@x)
    meat = sum(np.outer(v,v) for v in scores.values())
    covariance = bread@meat@bread * g/(g-1)*(n-1)/(n-p)
    return beta,np.sqrt(np.maximum(np.diag(covariance),0)),g


def linear_shap(x, beta, background_mean):
    phi = (x-background_mean)*beta
    base = float(background_mean@beta)
    if not np.allclose(base+phi.sum(axis=1), x@beta, atol=1e-10):
        raise ValueError('Linear SHAP additivity failed')
    return phi,base


def feature_group(name):
    return 'lead' if name.startswith('lead_') else 'season' if name.startswith('season_') else 'weather_narrative' if name.startswith('regime_') else name


def model(rows, metric, kind):
    x,names = design(rows,kind=='absolute_revision')
    y = np.asarray([r['outcome'] for r in rows])
    train = np.array([r['year']<2025 for r in rows])
    test = ~train
    if not train.any() or not test.any():
        raise ValueError('Missing chronological training/holdout cases')
    retained, omitted = [], []
    for j,name in enumerate(names):
        candidate = retained+[j]
        if np.linalg.matrix_rank(x[train][:,candidate]) == len(candidate):
            retained.append(j)
        else:
            omitted.append(name)
    x = x[:,retained]
    names = [names[i] for i in retained]
    beta,se,g = fit_cluster_ols(x[train],y[train],[r['valid_date'] for r in rows if r['year']<2025])
    coef = [dict(metric=metric,outcome_kind=kind,feature=name,coefficient_c=float(b),
                 se_7day_cluster=float(s),ci95_low=float(b-1.96*s),ci95_high=float(b+1.96*s),
                 p_normal_approx=float(math.erfc(abs(b/s)/math.sqrt(2))) if s else None)
            for name,b,s in zip(names,beta,se)]
    diagnostics = []
    for subset,mask in (('train_2022_2024',train),('holdout_2025',test)):
        pred = x[mask]@beta
        error = pred-y[mask]
        sst = float(np.sum((y[mask]-y[mask].mean())**2))
        baseline = np.full(mask.sum(), y[train].mean())
        diagnostics.append(dict(metric=metric,outcome_kind=kind,subset=subset,n_cases=int(mask.sum()),
            n_dates=len({r['valid_date'] for r,keep in zip(rows,mask) if keep}),
            outcome_mean_c=float(y[mask].mean()),mae_c=float(np.abs(error).mean()),
            rmse_c=float(np.sqrt(np.mean(error**2))),r_squared=1-float(error@error)/sst if sst else None,
            train_mean_baseline_mae_c=float(np.abs(baseline-y[mask]).mean()),
            n_negative_predictions=int((pred<0).sum()),training_clusters=g,
            design_condition_number=float(np.linalg.cond(x[train])),omitted_features=';'.join(omitted)))
    phi,base = linear_shap(x[test],beta,x[train].mean(axis=0))
    importance = []
    groups = defaultdict(list)
    for j,name in enumerate(names):
        if name!='intercept':
            groups[feature_group(name)].append(j)
    for name,indices in groups.items():
        total = phi[:,indices].sum(axis=1)
        importance.append(dict(metric=metric,outcome_kind=kind,factor=name,
            mean_abs_shap_c=float(np.abs(total).mean()),mean_signed_shap_c=float(total.mean()),
            n_holdout_cases=int(test.sum()),base_value_c=base))
    corr = []
    for j in range(1,len(names)):
        for k in range(j+1,len(names)):
            corr.append(dict(metric=metric,outcome_kind=kind,feature_a=names[j],feature_b=names[k],
                             training_correlation=float(np.corrcoef(x[train,j],x[train,k])[0,1])))
    return coef,diagnostics,importance,corr


def analyze(snapshot):
    folder = result_dir(7)
    factors,panel_audit = factor_data(snapshot)
    cases,coverage = outcome_cases(snapshot,factors)
    stratified,coefficients,diagnostics,importance,correlations,descriptive = [],[],[],[],[],[]
    thresholds = []
    for (metric,kind), rows in sorted(group_rows(cases,('metric','outcome_kind')).items()):
        # Threshold based only on distinct 2022 observed panel dates, not outcomes.
        threshold = float(np.median([v['spatial_spread'] for d,v in factors[metric].items() if d.year==2022]))
        thresholds.append(dict(metric=metric,outcome_kind=kind,spatial_high_threshold_c=threshold,
                               threshold_period='2022 distinct valid dates',temperature_change_threshold_c=2.))
        for row in rows:
            row['change_high'] = int(row['temp_change']>=2)
            row['spread_high'] = int(row['spatial_spread']>=threshold)
        for factor,labels,ref in (('rain10',[1],0),('change_high',[1],0),('spread_high',[1],0),
                                  ('regime',['cyclone_mention','trough_mention','monsoon_mention'],'other'),
                                  ('season',['MAM','JJA','SON'],'DJF')):
            for (value,),group in sorted(group_rows(rows,(factor,)).items()):
                descriptive.append(dict(metric=metric,outcome_kind=kind,factor=factor,value=value,
                    n_cases=len(group),n_dates=len({r['valid_date'] for r in group}),
                    mean_outcome_c=float(np.mean([r['outcome'] for r in group]))))
            for label in labels:
                strata = ('lead_days',) if factor=='season' else ('lead_days','season')
                stratified.append(dict(metric=metric,outcome_kind=kind,
                    **stratified_contrast(rows,factor,label,ref,strata)))
        co,di,im,cr = model(rows,metric,kind)
        coefficients.extend(co);diagnostics.extend(di);importance.extend(im);correlations.extend(cr)
    for name,data in [('station_panel',panel_audit),('join_coverage',coverage),('factor_thresholds',thresholds),
                      ('stratified_contrasts',stratified),('factor_descriptive',descriptive),
                      ('regression_coefficients',coefficients),('model_diagnostics',diagnostics),
                      ('shap_group_importance',importance),('feature_correlations',correlations)]:
        csv_output(folder/(name+'.csv'),data)
    fig,axes = plt.subplots(2,2,figsize=(13,9),sharex=True)
    for ax,((metric,kind),items) in zip(axes.flat,sorted(group_rows(importance,('metric','outcome_kind')).items())):
        items = sorted(items,key=lambda r:r['mean_abs_shap_c'])
        ax.barh([r['factor'] for r in items],[r['mean_abs_shap_c'] for r in items],color=COLORS[0])
        ax.set_title(f'{metric}: {kind.replace("_"," ")}',loc='left')
        ax.set_xlabel('Mean absolute grouped SHAP (°C)')
    fig.suptitle('Linear-model associations · 2025 holdout',fontsize=15)
    save(fig,folder,'factor_shap.png','2022–2024 training; post-event factors, not an operational prediction model. Interventional linear SHAP.')
    for metric in TEMP_CODES:
        fig,axes = plt.subplots(1,2,figsize=(14,6),sharex=True)
        for ax,kind in zip(axes,('absolute_error','absolute_revision')):
            rows = [r for r in stratified if r['metric']==metric and r['outcome_kind']==kind and r['ci95_low'] is not None]
            labels = [f"{r['factor']}: {r['comparison']} vs {r['reference']}" for r in rows]
            for j,r in enumerate(rows):
                ax.hlines(j,r['ci95_low'],r['ci95_high'],color=COLORS[0],linewidth=2)
                ax.plot(r['mean_difference_c'],j,'o',color=COLORS[0])
            ax.set_yticks(range(len(rows)),labels)
            ax.axvline(0,color='#555555',linestyle='--')
            ax.set_title(kind.replace('_',' '),loc='left');ax.set_xlabel('Adjusted group difference (°C)')
        fig.suptitle(f'{metric}: stratified factor associations · 2022–2025',fontsize=15)
        save(fig,folder,f'{metric}_stratified.png','95% percentile intervals: 1,000 fixed 7-day block bootstrap draws. Comparisons are exploratory, not causal.')
    key = [r for r in stratified if r['factor'] in ('rain10','change_high','spread_high')]
    findings = []
    for r in key:
        if r['mean_difference_c'] is not None:
            findings.append(f"{r['metric']} {r['outcome_kind'].replace('_',' ')}: {r['factor']} high-versus-low "
                            f"difference {r['mean_difference_c']:+.3f} °C after lead/season stratification "
                            f"({r['n_cases']:,} common-support cases).")
    findings.append('All four models are explanatory associations. Their 2025 holdout diagnostics and SHAP rankings are exported; '
                    'chronological holdout does not make realized weather available at issuance or establish causality.')
    findings.append('The fixed-panel join retains '+
                    ', '.join(f"{r['matched_dates']:,}/{r['source_dates']:,} {r['metric']} error target dates"
                              for r in coverage if r['outcome_kind']=='absolute_error')+'. '
                    'The error-model holdout R² values are '+
                    ', '.join(f"{r['metric']} {r['r_squared']:.3f}" for r in diagnostics
                              if r['subset']=='holdout_2025' and r['outcome_kind']=='absolute_error')+
                    '; these low values limit how much variation the fitted models explain.')
    for metric in TEMP_CODES:
        top = max((r for r in importance if r['metric']==metric and r['outcome_kind']=='absolute_error'),
                  key=lambda r:r['mean_abs_shap_c'])
        findings.append(f"{metric} error model: {top['factor']} has the largest grouped holdout SHAP magnitude "
                        f"({top['mean_abs_shap_c']:.3f} °C); this ranks fitted-model attributions, not causal importance.")
    report(7,'Conditions associated with temperature errors and revisions','\n\n'.join(findings),
           table(key,['metric','outcome_kind','factor','mean_difference_c','ci95_low','ci95_high'])+
           '\n\n### Season and bulletin-narrative comparisons\n\n'+
           table([r for r in stratified if r['factor'] in ('season','regime')],
                 ['metric','outcome_kind','factor','comparison','reference','n_cases','mean_difference_c','ci95_low','ci95_high'])+
           '\n\n### Fixed-panel join coverage\n\n'+table(coverage,
                 ['metric','outcome_kind','eligible_cases','matched_cases','excluded_cases','matched_dates'])+
           '\n\n### Chronological model check\n\n'+table([r for r in diagnostics if r['subset']=='holdout_2025'],
                   ['metric','outcome_kind','n_cases','mae_c','rmse_c','r_squared','n_negative_predictions']),
           'Daily-latest forecasts and consecutive-issue-day revisions, both endpoints leads 1–9. '
           'Outcome units are °C. HKO-point rainfall ≥10 mm; absolute HKO day-to-day extrema change; '
           'range across a fixed eight-station panel requiring all eight complete numeric readings; target-date season. '
           'Narrative proxy hierarchy: cyclone/typhoon/storm/depression mention, then trough, then monsoon, then other, '
           'using the later/selected issue’s general-situation text. This is a bulletin-level mention, not target-day event membership. '
           'Binary contrasts require ≥10 unique dates in each group per lead×season stratum (season contrasts adjust lead only). '
           'Weights are fixed common-support case counts. 95% intervals use 1,000 resamples of fixed 7-day calendar blocks; '
           'invalid draws are excluded and an interval needs ≥900 valid draws. Additive OLS fits 2022–2024, tests 2025, '
           'with lead/season/regime dummies, rain, continuous change/spread and a linear year term; revision models add elapsed hours. '
           'Zero-variance/collinear terms are explicitly omitted. Coefficient intervals use 7-day cluster sandwich covariance '
           'and asymptotic normal approximation. Exact interventional linear SHAP is beta×(feature−training mean); '
           'dummy attributions are summed within factor before mean absolute magnitude. '
           '[Official linear SHAP definition](https://shap.readthedocs.io/en/latest/generated/shap.LinearExplainer.html). '
           'Additivity is asserted for every holdout row. Station mappings, missing joins, correlations, thresholds and all coefficients are exported.',
           'Realized rainfall, temperature changes and spatial spread are post-event context. Selection requires a complete fixed panel, '
           'so missingness may bias coverage; excluded dates/cases are reported, not imputed. Panel range includes elevation/location '
           'differences and is not forecast uncertainty. Narrative labels can mention remote or future systems. '
           'Exploratory contrasts and coefficient tests have no multiple-testing correction. Seven-day blocks do not guarantee '
           'removal of longer serial dependence. Correlated factors can redistribute interventional SHAP credit. '
           'OLS may produce negative magnitudes, reported without clipping; poor holdout fit limits explanations. '
           'This factor-model analysis covers temperature outcomes. RH endpoint verification is reported separately in RQ3–RQ5; '
           'the fixed station-panel range here is temperature spread, not humidity spread.')
    save_metadata(7,snapshot,{'station_panel':PANEL,'training_years':[2022,2023,2024],'holdout_year':2025,
                            'factor_role':'post-event explanatory','bootstrap_block_days':7,
                            'shap_method':'analytic interventional linear; training background means'})


if __name__=='__main__':
    cli(7,analyze)
