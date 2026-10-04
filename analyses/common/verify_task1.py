"""Read-only independent SQL checks plus separately written source-level checks.

This is not full independent verification of bootstrap CIs or regression/SHAP.
Synthetic method tests cover those; the verification receipts state their scope.
"""
from collections import Counter, defaultdict
from datetime import datetime,timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.database import connect
from common.task1 import ANALYSES, FOLDERS, START, END, load_snapshot
from psycopg.rows import dict_row


def records(rq,name):
    with (ANALYSES/FOLDERS[rq]/'results'/name).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))


def check_fields(expected,actual,keys):
    for key in keys:
        e=expected[key];a=actual[key]
        if e is None:
            if a not in ('',None):
                raise AssertionError('Expected unavailable: '+key)
        elif not math.isclose(float(e),float(a),rel_tol=1e-9,abs_tol=1e-9):
            raise AssertionError(f'{key}: independent={e}, result={a}')


def main():
    snapshot=load_snapshot()  # conflict/duplicate/source-quality audit, not calculations
    sql_path=Path(__file__).with_name('verification_query.sql')
    sql=sql_path.read_text(encoding='utf-8')
    with connect() as db,db.cursor(row_factory=dict_row) as cur:
        cur.execute(sql,{'start':START,'end':END});answers=cur.fetchall()
    counts=defaultdict(int)
    for answer in answers:
        rq,kind=answer['rq'],answer['kind'];scope=answer['scope'];metric=answer['metric'];dim=answer['dimension']
        expected=answer['result']
        if kind=='direction':
            actual=next(r for r in records(2,'direction_by_lead.csv') if r['scope']==scope and r['metric']==metric and r['lead_days']==dim)
        elif kind=='psr_transition':
            actual=next(r for r in records(2,'psr_transition_counts.csv') if r['scope']==scope and r['before']==metric and r['after']==dim)
        elif kind=='usefulness':
            actual=next(r for r in records(3,'usefulness_overall.csv') if r['scope']==scope and r['metric']==metric and r['denominator']==dim)
        elif kind=='accuracy':
            actual=next(r for r in records(4,'rh_accuracy_by_lead.csv' if metric.startswith('rh_') else 'temperature_accuracy_by_lead.csv') if r['selection']==scope and r['metric']==metric and r['lead_days']==dim)
        else:
            filename={'bias_overall':'bias_overall.csv','bias_season':'bias_by_season.csv','bias_year':'bias_by_year.csv'}[kind]
            if metric.startswith('rh_'):
                filename='rh_'+filename
            actual=next(r for r in records(5,filename) if r['metric']==metric and (kind=='bias_overall' or r['season' if kind=='bias_season' else 'year']==dim))
        check_fields(expected,actual,expected.keys());counts[rq]+=1
    baseline_sql=Path(__file__).with_name('baseline_verification_query.sql').read_text(encoding='utf-8')
    with connect() as db,db.cursor(row_factory=dict_row) as cur:
        cur.execute(baseline_sql,{'start':START,'end':END});baselines=cur.fetchall()
    for expected in baselines:
        actual=next(r for r in records(4,'baseline_skill_by_lead.csv') if r['selection']=='daily_latest'
                    and r['metric']==expected['metric'] and int(r['lead_days'])==expected['lead_days'] and r['baseline']==expected['baseline'])
        check_fields(expected,actual,[k for k in expected if k not in ('metric','lead_days','baseline')]);counts[4]+=1
    # RH references independently reconstructed from retained JSON, not RQ4 helpers.
    # A leap-year month/day index is reproduced explicitly; verification never
    # includes 2022 training outcomes in the frozen-reference comparisons.
    from datetime import date,timedelta
    rh_actual={metric:{r['report_date']:float(r[field]) for r in snapshot.rh_reports}
               for metric,field in [('rh_min','observed_rh_min_text'),('rh_max','observed_rh_max_text')]}
    latest_rh={}
    for r in snapshot.forecasts:
        key=(r['valid_date'],r['bulletin_time_hkt'].date())
        if key not in latest_rh or (r['bulletin_time_hkt'],r['forecast_issue_id']) > (latest_rh[key]['bulletin_time_hkt'],latest_rh[key]['forecast_issue_id']):
            latest_rh[key]=r
    selected_rh=[r for r in latest_rh.values() if 1<=r['lead_days']<=9]
    for metric,field in [('rh_min','forecast_rh_min_pct'),('rh_max','forecast_rh_max_pct')]:
        training=[((date(2000,d.month,d.day)-date(2000,1,1)).days,v) for d,v in rh_actual[metric].items() if d.year==2022]
        references={}
        for day in range(366):
            values=[v for index,v in training if min(abs(index-day),366-abs(index-day))<=15]
            references[day]=(float(np.mean(values)),float(np.median(values)),len(values))
            a=next(r for r in records(4,'rh_climatology_calendar_day.csv') if r['metric']==metric and int(r['reference_day_index'])==day)
            check_fields(dict(mean=references[day][0],median=references[day][1],n_training=len(values)),a,('mean','median','n_training'))
        # The 366×2 calendar checks are counted explicitly, not as score groups.
        counts[4]+=366
        for lead in range(1,10):
            group=[r for r in selected_rh if r['lead_days']==lead]
            for baseline in ('climatology_mean_2022','climatology_median_2022','persistence_lag2','persistence_lag1'):
                comparisons=[]
                for r in group:
                    target=r['valid_date']
                    if baseline.startswith('climatology'):
                        if target.year==2022:
                            continue
                        day=(date(2000,target.month,target.day)-date(2000,1,1)).days
                        reference=references[day][int('median' in baseline)]
                    else:
                        past=r['bulletin_time_hkt'].date()-timedelta(days=int(baseline[-1]))
                        if past not in rh_actual[metric]:
                            continue
                        reference=rh_actual[metric][past]
                    comparisons.append((float(r[field])-rh_actual[metric][target],reference-rh_actual[metric][target]))
                forecast_errors=np.array([f for f,b in comparisons]);baseline_errors=np.array([b for f,b in comparisons])
                fmae=float(np.abs(forecast_errors).mean());bmae=float(np.abs(baseline_errors).mean())
                frmse=float(np.sqrt((forecast_errors**2).mean()));brmse=float(np.sqrt((baseline_errors**2).mean()))
                expected=dict(n_matched=len(comparisons),n_excluded=len(group)-len(comparisons),forecast_mae=fmae,baseline_mae=bmae,
                              forecast_rmse=frmse,baseline_rmse=brmse,mae_skill=1-fmae/bmae,mse_skill=1-frmse**2/brmse**2)
                a=next(r for r in records(4,'rh_baseline_skill_by_lead.csv') if r['selection']=='daily_latest' and r['metric']==metric and int(r['lead_days'])==lead and r['baseline']==baseline)
                check_fields(expected,a,expected.keys());counts[4]+=1
    # RQ6: independently construct last issue/day, point event and full weighted panel.
    latest={}
    for r in snapshot.forecasts:
        key=(r['valid_date'],r['bulletin_time_hkt'].date())
        if key not in latest or (r['bulletin_time_hkt'],r['forecast_issue_id'])>(latest[key]['bulletin_time_hkt'],latest[key]['forecast_issue_id']):
            latest[key]=r
    bands={'Low':(0,.3),'Medium Low':(.3,.45),'Medium':(.45,.55),'Medium High':(.55,.7),'High':(.7,1.)}
    selected=[r for r in latest.values() if 1<=r['lead_days']<=9 and r['psr'] in bands]
    weights=records(6,'validated_area_weights.csv')
    with (ANALYSES/'01_rainfall/results/psr_area_weights.csv').open(encoding='utf-8',newline='') as handle:
        source_weights=list(csv.DictReader(handle))
    if weights!=source_weights or len(weights)!=22 or len({r['observation_series_id'] for r in weights})!=22:
        raise AssertionError('RQ6 exported weights differ from the source fixed panel')
    w={int(r['observation_series_id']):float(r['weight']) for r in weights}
    total=sum(w.values())
    if abs(total-1)>1e-6:
        raise AssertionError('RQ6 source weights do not sum to one')
    w={k:v/total for k,v in w.items()}
    panel=defaultdict(dict);point={}
    for r in snapshot.observations:
        value=float(r['value_numeric']) if r['value_numeric'] is not None else None
        bounds=(value,value) if value is not None and r['data_completeness']=='C' else (0,.05) if r['value_text']=='Trace' and r['data_completeness']=='C' else None
        if r['observation_series_id'] in w:
            panel[r['observation_date']][r['observation_series_id']]=bounds
        if r['series_code']=='obs_hko_daily_rainfall' and bounds is not None:
            point[r['observation_date']]=int(bounds[0]>=10)
    labels={'hko_point':point,'area_weighted_22':{},'station_mean_22':{}}
    for d,p in panel.items():
        if set(p)!=set(w) or any(v is None for v in p.values()):
            continue
        for proxy,weight in (('area_weighted_22',w),('station_mean_22',dict.fromkeys(w,1/22))):
            lo=sum(weight[k]*v[0] for k,v in p.items());hi=sum(weight[k]*v[1] for k,v in p.items())
            if not lo<10<=hi:
                labels[proxy][d]=int(lo>=10)
    reliability=records(6,'reliability.csv')
    scores=records(6,'brier_scores.csv')
    alarms=records(6,'contingency_tables.csv')
    coverage=records(6,'target_coverage.csv')
    # Assert the whole exported grain: no duplicate or unexpected proxy/group rows.
    expected_keys={filename:set() for filename in ('reliability','scores','alarms','coverage')}
    observed_keys={
        'reliability':[(r['proxy'],r['lead_group'],r['category']) for r in reliability],
        'scores':[(r['proxy'],r['lead_group']) for r in scores],
        'alarms':[(r['proxy'],r['lead_group'],r['alarm_rule']) for r in alarms],
        'coverage':[(r['proxy'],) for r in coverage]}
    rank={category:index for index,category in enumerate(bands)}
    for proxy,target in labels.items():
        paired=[(r,target[r['valid_date']]) for r in selected if r['valid_date'] in target]
        a=next(r for r in coverage if r['proxy']==proxy)
        expected=dict(n_target_dates=len(target),n_events=sum(target.values()),
                      n_matched_forecasts=len(paired),n_candidate_forecasts=len(selected),
                      n_unmatched_forecasts=len(selected)-len(paired))
        check_fields(expected,a,expected.keys());counts[6]+=1
        expected_keys['coverage'].add((proxy,))
        for lead_group,lower_lead,upper_lead in [('all',1,9),('1-3',1,3),('4-6',4,6),('7-9',7,9)]:
            members=[(r,y) for r,y in paired if lower_lead<=r['lead_days']<=upper_lead]
            for category,(lo,hi) in bands.items():
                group=[(r,y) for r,y in members if r['psr']==category]
                if not group:
                    continue
                events=sum(y for r,y in group)
                rate=events/len(group)
                expected=dict(n_forecasts=len(group),n_target_dates=len({r['valid_date'] for r,y in group}),
                              n_events=events,event_rate=rate,forecast_band_low=lo,forecast_band_high=hi,
                              midpoint_p=(lo+hi)/2)
                a=next(r for r in reliability if (r['proxy'],r['lead_group'],r['category'])==(proxy,lead_group,category))
                check_fields(expected,a,expected.keys())
                if (a['rate_within_band'].lower()=='true')!=(lo<=rate<=hi if hi==1 else lo<=rate<hi):
                    raise AssertionError('Incorrect category-band membership')
                counts[6]+=1;expected_keys['reliability'].add((proxy,lead_group,category))
            if not members:
                continue
            quantities=defaultdict(list)
            for r,y in members:
                lo,hi=bands[r['psr']]
                lower=(lo-y)**2;upper=(hi-y)**2
                for field,value in dict(midpoint_bs=((lo+hi)/2-y)**2,
                    lower_endpoint_bs=lower,upper_endpoint_bs=upper,
                    bs_lower_bound=min(lower,upper),bs_upper_bound=max(lower,upper)).items():
                    quantities[field].append(value)
            expected=dict(n_forecasts=len(members),event_rate=sum(y for r,y in members)/len(members),
                          **{k:sum(v)/len(v) for k,v in quantities.items()})
            a=next(r for r in scores if (r['proxy'],r['lead_group'])==(proxy,lead_group))
            check_fields(expected,a,expected.keys());counts[6]+=1
            expected_keys['scores'].add((proxy,lead_group))
            for threshold in ('Medium','Medium High','High'):
                cells=Counter((y,rank[r['psr']]>=rank[threshold]) for r,y in members)
                tp,fp,fn,tn=(cells[(1,True)],cells[(0,True)],cells[(1,False)],cells[(0,False)])
                expected=dict(n_forecasts=len(members),tp=tp,fp=fp,fn=fn,tn=tn,
                    hit_rate=tp/(tp+fn) if tp+fn else None,
                    false_alarm_ratio=fp/(tp+fp) if tp+fp else None,
                    false_positive_rate=fp/(fp+tn) if fp+tn else None)
                rule=threshold+'_or_higher'
                a=next(r for r in alarms if (r['proxy'],r['lead_group'],r['alarm_rule'])==(proxy,lead_group,rule))
                check_fields(expected,a,expected.keys());counts[6]+=1
                expected_keys['alarms'].add((proxy,lead_group,rule))
    for filename,keys in observed_keys.items():
        if len(keys)!=len(set(keys)) or set(keys)!=expected_keys[filename]:
            raise AssertionError('RQ6 output grain mismatch: '+filename)
    # RQ7 means/coverage: reconstruct joins and absolute outcomes independently.
    catalog=records(7,'station_panel.csv')
    obs=defaultdict(dict)
    for r in snapshot.observations:
        if r['data_completeness']=='C' and r['value_numeric'] is not None:
            obs[r['observation_series_id']][r['observation_date']]=float(r['value_numeric'])
    outcomes=defaultdict(list)
    by_target=defaultdict(list)
    for r in latest.values():
        by_target[r['valid_date']].append(r)
    for metric in ('tmin','tmax'):
        sid=next(r['observation_series_id'] for r in snapshot.series if r['series_code']=='obs_hko_daily_'+metric)
        ids=[int(r['observation_series_id']) for r in catalog if r['metric']==metric]
        support=set.intersection(*(set(obs[i]) for i in ids)) & set(point)
        actual=obs[sid]
        from datetime import timedelta
        support={d for d in support if d in actual and d-timedelta(days=1) in actual}
        col='forecast_'+metric+'_c'
        for d,path in by_target.items():
            if d not in support:
                continue
            for r in path:
                if 1<=r['lead_days']<=9 and r['general_situation'] and r['general_situation'].strip():
                    outcomes[(metric,'absolute_error')].append((d,abs(float(r[col])-actual[d])))
            ordered=sorted(path,key=lambda r:r['bulletin_time_hkt'])
            for a,b in zip(ordered,ordered[1:]):
                if (b['bulletin_time_hkt'].date()-a['bulletin_time_hkt'].date()).days==1 and 1<=a['lead_days']<=9 and 1<=b['lead_days']<=9 and b['general_situation'] and b['general_situation'].strip():
                    outcomes[(metric,'absolute_revision')].append((d,abs(float(b[col])-float(a[col]))))
        for kind in ('absolute_error','absolute_revision'):
            a=next(r for r in records(7,'join_coverage.csv') if r['metric']==metric and r['outcome_kind']==kind)
            vals=outcomes[(metric,kind)]
            check_fields({'matched_cases':len(vals),'matched_dates':len({d for d,v in vals})},a,('matched_cases','matched_dates'));counts[7]+=1
            expected=np.mean([v for d,v in vals if d.year<2025])
            a=next(r for r in records(7,'model_diagnostics.csv') if r['metric']==metric and r['outcome_kind']==kind and r['subset']=='train_2022_2024')
            check_fields({'outcome_mean_c':expected},a,('outcome_mean_c',));counts[7]+=1
    # Every executed result must refer to the same current input snapshot.
    for rq in FOLDERS:
        folder=ANALYSES/FOLDERS[rq]/'results'
        meta=json.loads((folder/'run_metadata.json').read_text(encoding='utf-8'))
        for key in ('forecast_rows_sha256','observation_rows_sha256','rh_report_rows_sha256'):
            if meta[key]!=snapshot.meta[key]:
                raise AssertionError('Input snapshot drift: '+FOLDERS[rq])
        output={'verified_at_utc':datetime.now(timezone.utc).isoformat(),'database_modified':False,
            'independent_aggregate_checks':counts[rq],
            'scope':'SQL aggregates RQ2 direction/PSR transitions, RQ3 temperature/RH usefulness, RQ4 temperature/RH accuracy and matched temperature baselines, RQ5 temperature/RH bias. Independently written Python checks RQ4 daily-latest RH matched baselines plus all 732 frozen RH calendar bins; RQ6 all three proxies and all/1-3/4-6/7-9 lead groups: reliability counts/rates/bands, midpoint and endpoint Brier scores, score bounds, all confusion cells/rates, coverage and unique exported grain; RQ7 join/outcome means. No independent CI, FFI, coefficient or SHAP verification.',
            'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_queries_sha256':hashlib.sha256(sql.encode()).hexdigest(),
            'baseline_query_sha256':hashlib.sha256(baseline_sql.encode()).hexdigest(),
            'forecast_rows_sha256':meta['forecast_rows_sha256'],'observation_rows_sha256':meta['observation_rows_sha256'],
            'rh_report_rows_sha256':meta['rh_report_rows_sha256'],
            'output_file_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.suffix in ('.csv','.png','.md','.json') and p.name!='verification.json'}}
        (folder/'verification.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('Independent checks passed:',dict(counts))


if __name__=='__main__':
    main()
