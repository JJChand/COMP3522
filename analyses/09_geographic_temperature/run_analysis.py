"""All eligible stations: shared temperature forecast x coast and administrative region.

Reads existing CSV snapshots only. No DB access or station subsampling. Full daily
pairs can be exported outside the repository with --export-pairs.
"""
from pathlib import Path
import argparse,sys,json,hashlib,platform,itertools,gzip,csv,re
ROOT=Path(__file__).resolve().parent
GROUPS={'coast':['near','transition','inland'],'region':['HKI','KL','NT','Islands']}
EXCLUDED={'TC','TMS'}

def norm(s):return re.sub('[^a-z0-9]','',str(s).lower())

def metrics(e):
    import numpy as np
    a=np.asarray(e,float);a=a[np.isfinite(a)]
    if not len(a):return dict(n=0,mae=float('nan'),rmse=float('nan'),bias=float('nan'),mse=float('nan'))
    return dict(n=len(a),mae=float(np.abs(a).mean()),rmse=float(np.sqrt((a*a).mean())),bias=float(a.mean()),mse=float((a*a).mean()))

def equal_station_metrics(e):
    """Each nonempty station gets equal weight, regardless of coverage."""
    import numpy as np
    e=np.asarray(e,float)
    if e.ndim!=2:raise ValueError('Expected date x station matrix')
    if not np.isfinite(e).any(axis=0).all():raise ValueError('A station has zero observations')
    return dict(mae=float(np.nanmean(np.abs(e),axis=0).mean()),rmse=float(np.sqrt(np.nanmean(e*e,axis=0).mean())),bias=float(np.nanmean(e,axis=0).mean()))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True,help='Directory containing forecasts, observations, series and stations CSVs')
    parser.add_argument('--geography',type=Path,default=ROOT/'inputs/station_geography.csv')
    parser.add_argument('--output',type=Path,default=ROOT/'results')
    parser.add_argument('--export-pairs',type=Path,help='Optional .csv.gz of every valid pair for all 30 main stations; keep outside Git')
    parser.add_argument('--dependency-dir',type=Path,help='Optional local Python dependency directory; not needed in a configured venv')
    args=parser.parse_args()
    if args.dependency_dir:sys.path.insert(0,str(args.dependency_dir.resolve()))
    import numpy as np
    import pandas as pd
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    def save(rows,name):
        df=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
        df.to_csv(out/(name+'.csv'),index=False,encoding='utf-8-sig');return df
    calendar=pd.date_range('2022-01-01','2025-12-31');geo=pd.read_csv(args.geography).set_index('station_code')
    geo.loc[geo.islands_district,'region_group']='Islands'
    raw=args.data_dir.resolve();ss=pd.read_csv(raw/'stations.csv');series=pd.read_csv(raw/'series.csv')
    namecode={norm(r.station_name):r.station_code for r in ss.itertuples()}
    s=series[series.metric_name.str.contains('Maximum Temperature|Minimum Temperature')].copy()
    s['station_code']=s.station_name.map(lambda x:namecode[norm(x)])
    s['variable']=np.where(s.metric_name.str.contains('Maximum'),'Tmax','Tmin')
    assert not s.duplicated(['station_code','variable']).any()
    obs=pd.read_csv(raw/'observations.csv',parse_dates=['observation_date'])
    obs=obs[obs.observation_date.isin(calendar)].merge(s[['observation_series_id','station_code','variable']],on='observation_series_id')
    assert not obs.duplicated(['station_code','variable','observation_date']).any()
    obs['accepted']=obs.value_numeric.where(obs.data_completeness.eq('C'))
    truth={v:q.pivot(index='observation_date',columns='station_code',values='accepted').reindex(calendar) for v,q in obs.groupby('variable')}
    f=pd.read_csv(raw/'forecasts.csv',parse_dates=['valid_date','bulletin_time_hkt']);f=f[f.valid_date.isin(calendar)].copy()
    f['issue_date']=f.bulletin_time_hkt.dt.normalize()
    assert f.lead_days.eq((f.valid_date-f.issue_date).dt.days).all()
    assert not f.groupby(['valid_date','bulletin_time_hkt'])[['forecast_tmax_c','forecast_tmin_c']].nunique(dropna=False).gt(1).any().any()
    f=f.sort_values(['bulletin_time_hkt','forecast_issue_id']).drop_duplicates(['valid_date','issue_date'],keep='last')
    f=f[f.lead_days.between(1,9)]
    F={v:f.pivot(index='valid_date',columns='lead_days',values=c).reindex(index=calendar,columns=range(1,10)) for v,c in [('Tmax','forecast_tmax_c'),('Tmin','forecast_tmin_c')]}
    candidates=geo[geo.primary_aws&geo.temperature_candidate&~geo.index.isin(EXCLUDED)].index.tolist()
    assert len(candidates)==30
    # The strict panel is one intersection across all sites, variables and D1–D9.
    complete=pd.concat([truth[v][candidates] for v in F]+list(F.values()),axis=1).notna().all(axis=1)
    common=calendar[complete]
    save(pd.DataFrame({'valid_date':common}),'strict_common_dates')
    coverage=[]
    for code,row in geo.iterrows():
        status='included_all_available' if code in candidates else 'excluded_TMS_TC' if code in EXCLUDED else 'HKO_reference' if code=='HKO' else 'not_full_period_AWS'
        z=dict(station_code=code,**row.to_dict(),in_main_panel=code in candidates,status=status,calendar_days=len(calendar))
        for v in F:
            q=obs[(obs.station_code==code)&(obs.variable==v)]
            z[v+'_C_days']=int(truth[v][code].notna().sum());z[v+'_not_usable_days']=len(calendar)-z[v+'_C_days']
            z[v+'_non_C_rows']=int((q.data_completeness!='C').sum())
        z['paired_C_days']=int((truth['Tmax'][code].notna()&truth['Tmin'][code].notna()).sum());coverage.append(z)
    save(coverage,'station_inventory')
    panels=[]
    for factor,groups in GROUPS.items():
        for group in groups:
            codes=[c for c in candidates if geo.loc[c,factor+'_group']==group]
            panels.append(dict(factor=factor,group=group,n_stations=len(codes),stations=';'.join(codes),selection='ALL eligible stations; no top-N',strict_common_dates=len(common)))
    save(panels,'station_panels')
    # Shared calendar-day blocks preserve same-date dependencies. No station resampling.
    reps=2000;block=14;rng=np.random.default_rng(3522)
    starts=rng.integers(len(calendar),size=(reps,int(np.ceil(len(calendar)/block))))
    draws=((starts[:,:,None]+np.arange(block))%len(calendar)).reshape(reps,-1)[:,:len(calendar)]
    W=np.zeros((reps,len(calendar)))
    for i,x in enumerate(draws):W[i]=np.bincount(x,minlength=len(calendar))
    def boot_mae(e):
        count=W@np.isfinite(e).astype(float);numerator=W@np.nan_to_num(abs(e))
        return np.divide(numerator,count,out=np.full_like(count,np.nan),where=count>0)
    def interval(z):
        z=np.asarray(z);z=z[np.isfinite(z)]
        return [float(x) for x in np.quantile(z,[.025,.975])] if len(z) else [np.nan,np.nan]
    stationscores=[];groupscores=[];contrasts=[];yearly=[];flow=[];decomp=[];offsets=[];reference=[]
    for v in F:
        for code in candidates:
            delta=(truth[v][code]-truth[v]['HKO']).dropna()
            offsets.append(dict(station_code=code,variable=v,n_dates=len(delta),station_minus_HKO_mean=delta.mean(),station_minus_HKO_median=delta.median(),station_minus_HKO_sd=delta.std(),p10=delta.quantile(.1),p90=delta.quantile(.9)))
        for lead in range(1,10):
            forecast=F[v][lead]
            reference.append(dict(variable=v,lead=lead,**metrics(forecast-truth[v]['HKO'])))
            errors=forecast.to_numpy()[:,None]-truth[v][candidates].to_numpy()
            for j,code in enumerate(candidates):
                y=truth[v][code];valid=y.notna()&forecast.notna()
                flow.append(dict(station_code=code,variable=v,lead=lead,calendar_days=len(calendar),valid_pairs=int(valid.sum()),observation_only_missing=int((y.isna()&forecast.notna()).sum()),forecast_only_missing=int((y.notna()&forecast.isna()).sum()),both_missing=int((y.isna()&forecast.isna()).sum())))
                triple=valid&truth[v]['HKO'].notna();eh=(forecast-truth[v]['HKO'])[triple];gap=(truth[v]['HKO']-y)[triple];e=(forecast-y)[triple]
                assert np.allclose(e,eh+gap)
                decomp.append(dict(station_code=code,variable=v,lead=lead,n_dates=int(triple.sum()),local_mae=metrics(e)['mae'],HKO_mae_same_dates=metrics(eh)['mae'],local_bias=e.mean(),HKO_bias_same_dates=eh.mean(),HKO_minus_station_mean=gap.mean(),identity_residual=float((e-eh-gap).abs().max())))
            for design in ['all_available','strict_common','lowland_available']:
                keep=[j for j,c in enumerate(candidates) if design!='lowland_available' or geo.loc[c,'elevation_m']<300]
                codes=[candidates[j] for j in keep];e=errors[:,keep].copy()
                if design=='strict_common':e[~complete.to_numpy(),:]=np.nan
                boots=boot_mae(e)
                for j,code in enumerate(codes):
                    m=metrics(e[:,j]);valid=np.isfinite(e[:,j]);lo,hi=interval(boots[:,j])
                    stationscores.append(dict(design=design,station_code=code,variable=v,lead=lead,first_valid_date=str(calendar[valid].min().date()),last_valid_date=str(calendar[valid].max().date()),**m,mae_ci_low=lo,mae_ci_high=hi))
                    for year in range(2022,2026):yearly.append(dict(design=design,station_code=code,variable=v,lead=lead,year=year,**metrics(e[calendar.year==year,j])))
                for factor,groups in GROUPS.items():
                    gb={}
                    for group in groups:
                        ix=[i for i,c in enumerate(codes) if geo.loc[c,factor+'_group']==group];g=e[:,ix];bm=boots[:,ix]
                        b=np.where(np.isfinite(bm).all(axis=1),np.nanmean(bm,axis=1),np.nan);gb[group]=b
                        lo,hi=interval(b);n=np.isfinite(g).sum(axis=0)
                        groupscores.append(dict(design=design,factor=factor,group=group,variable=v,lead=lead,n_stations=len(ix),n_station_days=int(n.sum()),n_dates_union=int(np.isfinite(g).any(axis=1).sum()),n_dates_all_group_stations=int(np.isfinite(g).all(axis=1).sum()),station_days_min=int(n.min()),station_days_max=int(n.max()),**equal_station_metrics(g),pooled_station_day_mae=metrics(g)['mae'],mae_ci_low=lo,mae_ci_high=hi))
                    for a,b in itertools.combinations(groups,2):
                        lo,hi=interval(gb[b]-gb[a]);qs=[x for x in groupscores if x['design']==design and x['factor']==factor and x['variable']==v and x['lead']==lead]
                        ma={r['group']:r['mae'] for r in qs}
                        contrasts.append(dict(design=design,factor=factor,variable=v,lead=lead,contrast=b+' minus '+a,mae_difference=ma[b]-ma[a],ci_low=lo,ci_high=hi,interpretation='All available: dates differ by station; strict common: very small date sample. Conditional descriptive interval, not causal.'))
    for rows,name in [(stationscores,'station_metrics'),(groupscores,'group_metrics'),(contrasts,'group_contrasts'),(yearly,'station_year_metrics'),(flow,'pairing_coverage'),(decomp,'HKO_error_decomposition'),(offsets,'station_HKO_observed_offsets'),(reference,'HKO_reference_metrics')]:save(rows,name)
    save([dict(year=y,n_common_dates=int((common.year==y).sum())) for y in range(2022,2026)],'strict_common_year_coverage')
    export_rows=0
    if args.export_pairs:
        target=args.export_pairs.resolve();target.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(target,'wt',encoding='utf-8-sig',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['station_code','variable','valid_date','lead','bulletin_time_hkt','forecast_issue_id','source_file_id','observation_series_id','forecast','observed_C','signed_error','absolute_error','in_strict_common'])
            for v,col in [('Tmax','forecast_tmax_c'),('Tmin','forecast_tmin_c')]:
                for code in candidates:
                    q=obs[(obs.station_code==code)&(obs.variable==v)&obs.accepted.notna()]
                    pairs=f.merge(q,left_on='valid_date',right_on='observation_date').dropna(subset=[col])
                    for r in pairs.itertuples():
                        pred=getattr(r,col);error=pred-r.accepted
                        writer.writerow([code,v,str(r.valid_date.date()),r.lead_days,str(r.bulletin_time_hkt),r.forecast_issue_id,r.source_file_id,r.observation_series_id,pred,r.accepted,error,abs(error),bool(complete.loc[r.valid_date])]);export_rows+=1
    sources=[raw/(n+'.csv') for n in ['forecasts','observations','stations','series']]+[args.geography]
    meta={'period':['2022-01-01','2025-12-31'],'calendar_days':len(calendar),'leads':list(range(1,10)),'variables':list(F),'excluded_codes':sorted(EXCLUDED),'all_candidate_stations':candidates,'selection':'ALL 30 eligible complete-period AWS; never top-N. C quality and missingness still apply.','strict_common_dates':len(common),'station_equal_weighting':'MAE=mean station MAE; RMSE=sqrt(mean station MSE); Bias=mean station Bias. Also report pooled station-day MAE explicitly.','designs':{'all_available':'Every valid station/date/lead/variable pair; no cross-station date dropping. Dates differ, so group differences remain descriptive.','strict_common':'All 30 stations, Tmax/Tmin and all D1–D9 on exactly the same target dates. No imputation.','lowland_available':'All eligible stations below 300 m; descriptive sensitivity, not primary.'},'bootstrap':{'replicates':reps,'block_calendar_days':block,'seed':3522,'scope':'Time sampling conditional on fixed sites and missingness; same day resampled together. No multiple-comparison correction. Does not fix unequal date support or short common panel.'},'forecast_selection':'Latest archived bulletin per target date and issue calendar date; HKT day difference; D0 excluded.','geography_time':'Contemporary coastline/admin classification, not historical reconstruction.','exported_pair_rows':export_rows,'sources':[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sources],'software':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}}
    (out/'run_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'stations':len(candidates),'strict_dates':len(common),'pairs_exported':export_rows,'panels':panels},ensure_ascii=True))

if __name__=='__main__':main()
