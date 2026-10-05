"""Independent standard-library verification of all exported pairs and aggregates."""
from pathlib import Path
import argparse,csv,gzip,collections,math,json,hashlib
ROOT=Path(__file__).resolve().parent
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',type=Path,required=True);ap.add_argument('--pairs',type=Path,required=True);a=ap.parse_args()
    out=ROOT/'results';checks=[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    meta=json.loads((out/'run_metadata.json').read_text(encoding='utf-8'));inv={r['station_code']:r for r in rows(out/'station_inventory.csv')};codes={c for c,r in inv.items() if r['in_main_panel']=='True'}
    check('exactly all 30 eligible stations, not top-N',len(codes)==30 and codes==set(meta['all_candidate_stations']))
    check('named exclusions',not codes.intersection({'TC','TMS'}))
    check('four separate island sites',{c for c in codes if inv[c]['region_group']=='Islands'}=={'CCH','NGP','PEN','WGL'})
    common={r['valid_date'] for r in rows(out/'strict_common_dates.csv')};check('24 common dates',len(common)==24)
    forecasts={}
    for r in rows(a.data_dir/'forecasts.csv'):
        if not ('2022-01-01'<=r['valid_date']<='2025-12-31') or not 1<=int(r['lead_days'])<=9:continue
        k=r['valid_date'],int(r['lead_days']);previous=forecasts.get(k)
        if previous is None or (r['bulletin_time_hkt'],int(r['forecast_issue_id']))>(previous['bulletin_time_hkt'],int(previous['forecast_issue_id'])):forecasts[k]=r
    truth={}
    for r in rows(a.data_dir/'observations.csv'):
        if r['data_completeness']=='C' and r['value_numeric']:truth[r['observation_series_id'],r['observation_date']]=float(r['value_numeric'])
    acc=collections.defaultdict(lambda:[0,0.,0.,0.]);seen=set();nrows=0;max_source_delta=0.;date_sites=collections.defaultdict(set)
    with gzip.open(a.pairs,'rt',encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            c,v,day,lead=r['station_code'],r['variable'],r['valid_date'],int(r['lead']);key=c,v,day,lead
            assert key not in seen and c in codes;seen.add(key)
            src=forecasts[day,lead];p=float(src['forecast_tmax_c' if v=='Tmax' else 'forecast_tmin_c']);o=truth[r['observation_series_id'],day]
            assert str(src['forecast_issue_id'])==r['forecast_issue_id'] and src['bulletin_time_hkt']==r['bulletin_time_hkt']
            e=p-o;max_source_delta=max(max_source_delta,abs(p-float(r['forecast'])),abs(o-float(r['observed_C'])),abs(e-float(r['signed_error'])),abs(abs(e)-float(r['absolute_error'])))
            assert (r['in_strict_common']=='True')==(day in common)
            for design in (['all_available','strict_common'] if day in common else ['all_available']):
                z=acc[design,c,v,lead];z[0]+=1;z[1]+=abs(e);z[2]+=e*e;z[3]+=e
            if day in common:date_sites[day].add((c,v,lead))
            nrows+=1
    check('every one of 670865 pairs matches raw forecast, observation, IDs and error',nrows==670865==meta['exported_pair_rows'] and max_source_delta<1e-10)
    check('every common day contains 30 sites x 2 variables x 9 leads',all(len(v)==540 for v in date_sites.values()))
    def stat(key):
        n,ab,sq,b=acc[key];return dict(n=n,mae=ab/n,mse=sq/n,rmse=math.sqrt(sq/n),bias=b/n)
    for r in rows(out/'station_metrics.csv'):
        design='all_available' if r['design']=='lowland_available' else r['design'];s=stat((design,r['station_code'],r['variable'],int(r['lead'])))
        check('station metrics '+str((r['design'],r['station_code'],r['variable'],r['lead'])),int(r['n'])==s['n'] and all(abs(float(r[k])-s[k])<1e-9 for k in ['mae','rmse','bias']))
    for r in rows(out/'group_metrics.csv'):
        cs=[c for c in codes if inv[c][r['factor']+'_group']==r['group'] and (r['design']!='lowland_available' or float(inv[c]['elevation_m'])<300)]
        design='all_available' if r['design']=='lowland_available' else r['design'];m=[stat((design,c,r['variable'],int(r['lead']))) for c in cs]
        expect={'mae':sum(x['mae'] for x in m)/len(m),'rmse':math.sqrt(sum(x['mse'] for x in m)/len(m)),'bias':sum(x['bias'] for x in m)/len(m),'pooled_station_day_mae':sum(x['mae']*x['n'] for x in m)/sum(x['n'] for x in m)}
        check('group equal-station weighting '+str((r['design'],r['factor'],r['group'],r['variable'],r['lead'])),len(cs)==int(r['n_stations']) and sum(x['n'] for x in m)==int(r['n_station_days']) and all(abs(float(r[k])-x)<1e-9 for k,x in expect.items()))
    for r in rows(out/'pairing_coverage.csv'):check('calendar flow '+str((r['station_code'],r['variable'],r['lead'])),sum(int(r[k]) for k in ['valid_pairs','observation_only_missing','forecast_only_missing','both_missing'])==1461)
    decomp=rows(out/'HKO_error_decomposition.csv');check('all 540 signed error decompositions',len(decomp)==540 and all(abs(float(r['local_bias'])-float(r['HKO_bias_same_dates'])-float(r['HKO_minus_station_mean']))<1e-10 and float(r['identity_residual'])<1e-10 for r in decomp))
    benchmark=rows(ROOT.parent/'05_rq4_accuracy_by_lead/results/temperature_accuracy_by_lead.csv')
    for r in rows(out/'HKO_reference_metrics.csv'):
        ref=next(x for x in benchmark if x['selection']=='daily_latest' and x['metric']==r['variable'].lower() and x['lead_days']==r['lead'])
        check('Chandler HKO reproduction '+r['variable']+'/'+r['lead'],int(ref['n'])==int(r['n']) and all(abs(float(ref[k])-float(r[k]))<1e-10 for k in ['mae','rmse','bias']))
    summary={'passed':True,'checks':len(checks),'pair_rows_checked':nrows,'max_raw_pair_difference':max_source_delta,'items':checks,'scope':'All exported daily pairs checked against original C observations and independently selected daily-latest forecasts; all station/group metrics and weighting checked. Bootstrap intervals are not independently reimplemented. No claim of full original archive completeness or historical geography accuracy.','pairs_sha256':hashlib.sha256(a.pairs.read_bytes()).hexdigest()}
    (out/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS',len(checks),'checks;',nrows,'raw-source pairs checked.')
if __name__=='__main__':main()
