"""Uncorrected general RH forecast: matched geographic validity/usefulness."""
from pathlib import Path
import argparse,hashlib,json,sys,re,itertools
p=argparse.ArgumentParser();p.add_argument('--dependency-dir',type=Path);a=p.parse_args()
if a.dependency_dir:sys.path.insert(0,str(a.dependency_dir.resolve()))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results';SRC=ROOT/'inputs/humidity';OUT.mkdir(exist_ok=True)
sources=[]
def read(name,**kw):
    path=SRC/(name+'.csv');sources.append(path);return pd.read_csv(path,**kw)
def save(x,name):pd.DataFrame(x).to_csv(OUT/('humidity_'+name+'.csv'),index=False,encoding='utf-8-sig')
geo=read('station_inventory');codes=geo.station_code.tolist();assert len(codes)==26
assert geo.coast_group.value_counts().to_dict()=={'near':11,'transition':11,'inland':4} or geo.coast_group.value_counts().to_dict()=={'transition':11,'near':11,'inland':4}
daily=read('daily_observations',parse_dates=['date']);daily=daily[daily.complete].copy();assert daily.n_nominal_slots.eq(144).all()
fore=read('forecast_daily_latest',parse_dates=['valid_date','issue_date','bulletin_time_hkt']);fore=fore[fore.valid_date.dt.year.eq(2025)&fore.issue_date.dt.year.eq(2025)]
assert fore.lead_days.eq((fore.valid_date-fore.issue_date).dt.days).all()
assert not fore.duplicated(['valid_date','lead_days']).any()
dates=pd.date_range('2025-01-01','2025-12-31');errs={};preds={};common=np.ones(365,bool)
sources.append(SRC/'analysis_arrays.npz');legacy=np.load(SRC/'analysis_arrays.npz');assert codes==legacy['codes'].tolist()
for var in ['rh_min','rh_max']:
    truth=daily.pivot(index='date',columns='station_code',values=var).reindex(index=dates,columns=codes).to_numpy()
    pred=fore.pivot(index='valid_date',columns='lead_days',values='forecast_'+var+'_pct').reindex(index=dates,columns=range(1,10)).to_numpy()
    assert ((pred[np.isfinite(pred)]>=0)&(pred[np.isfinite(pred)]<=100)).all()
    errs[var]=pred[:,:,None]-truth[:,None,:];preds[var]=pred
    assert np.allclose(errs[var],legacy[var+'_errors'][0],equal_nan=True)
    common &= np.isfinite(errs[var]).all(axis=(1,2))
assert common.sum()==89
save(geo,'station_inventory');save([dict(date=str(d.date()),month=d.month,common_all26_both_variables_all9=bool(ok)) for d,ok in zip(dates,common)],'calendar')
save(pd.DataFrame({'month':dates.month,'common':common}).groupby('month',as_index=False).agg(common_days=('common','sum')),'month_coverage')
groups=['near','transition','inland'];registry=[]
for A,B in itertools.combinations(groups,2):
    for i in np.flatnonzero(geo.coast_group.eq(A)):
        for j in np.flatnonzero(geo.coast_group.eq(B)):registry.append(dict(group_a=A,group_b=B,station_a=codes[i],station_b=codes[j],i=i,j=j))
reg=pd.DataFrame(registry);ai=reg.i.to_numpy();bi=reg.j.to_numpy();assert len(reg)==209
rng=np.random.default_rng(3522);starts=rng.integers(365,size=(2000,53));draw=((starts[:,:,None]+np.arange(7))%365).reshape(2000,-1)[:,:365]
weights=np.array([np.bincount(d,minlength=365) for d in draw],float)
def divide(num,den):return np.divide(num,den,out=np.full_like(num,np.nan,dtype=float),where=den>0)
def summary_ci(bt):
    bt=bt[np.isfinite(bt)]
    if len(bt)<1900:return dict(low=np.nan,high=np.nan,n_boot_valid=len(bt),direction='insufficient_bootstrap_support')
    lo,hi=np.quantile(bt,[.025,.975]);return dict(low=float(lo),high=float(hi),n_boot_valid=len(bt),direction='positive' if lo>0 else 'negative' if hi<0 else 'insufficient')
rows=[];pair_rows=[];station_rows=[];common_rows=[];point_errors=[]
for var in errs:
    e=errs[var];pred=preds[var]
    for lead in range(1,10):
        for i,code in enumerate(codes):
            z=e[:,lead-1,i];z=z[np.isfinite(z)]
            station_rows.append(dict(variable=var,lead=lead,station_code=code,n_dates=len(z),mae=abs(z).mean(),rmse=np.sqrt(np.mean(z*z)),bias=z.mean()))
        for group in groups:
            z=e[common,lead-1,:][:,geo.coast_group.eq(group).to_numpy()]
            common_rows.append(dict(variable=var,lead=lead,group=group,n_stations=z.shape[1],n_dates=int(common.sum()),mae=abs(z).mean(),rmse=np.sqrt((z*z).mean()),bias=z.mean()))
    specifications=[('validity','all_valid',k) for k in range(1,10)]+[('revision',den,k) for den in ['changed_only','all_pairs'] for k in list(range(1,9))+['all']]
    for scope,denominator,lead in specifications:
        if scope=='validity':old=new=e[:,lead-1:lead,:];changed=np.ones((365,1),bool)
        else:
            take=np.arange(8) if lead=='all' else np.array([lead-1])
            old=e[:,take+1,:];new=e[:,take,:];changed=np.isfinite(pred[:,take+1])&np.isfinite(pred[:,take])&(pred[:,take+1]!=pred[:,take])
        mask=np.isfinite(old[:,:,ai])&np.isfinite(old[:,:,bi])&np.isfinite(new[:,:,ai])&np.isfinite(new[:,:,bi])
        if denominator=='changed_only':mask &= changed[:,:,None]
        daily_counts=mask.sum(axis=1);count=daily_counts.sum(axis=0);assert (count>0).all()
        boot_count=weights@daily_counts;pm={};bm={}
        for version,ar in [('old',old),('new',new)]:
            for suffix,ix in [('a',ai),('b',bi)]:
                z=ar[:,:,ix];ae=abs(z);num=np.where(mask,ae,0).sum(axis=1);key=version+'_mae_'+suffix
                pm[key]=num.sum(axis=0)/count;bm[key]=divide(weights@num,boot_count)
                pm[version+'_rmse_'+suffix]=np.sqrt(np.where(mask,z*z,0).sum(axis=(0,1))/count)
                pm[version+'_bias_'+suffix]=np.where(mask,z,0).sum(axis=(0,1))/count
        pm['old_gap']=pm['old_mae_b']-pm['old_mae_a'];pm['new_gap']=pm['new_mae_b']-pm['new_mae_a']
        bm['old_gap']=bm['old_mae_b']-bm['old_mae_a'];bm['new_gap']=bm['new_mae_b']-bm['new_mae_a']
        for suffix,ix in [('a',ai),('b',bi)]:
            u=abs(old[:,:,ix])-abs(new[:,:,ix]);pm['benefit_'+suffix]=pm['old_mae_'+suffix]-pm['new_mae_'+suffix];bm['benefit_'+suffix]=bm['old_mae_'+suffix]-bm['new_mae_'+suffix]
            pm['improvement_rate_'+suffix]=np.where(mask,u>1e-10,False).sum(axis=(0,1))/count
            pm['worsening_rate_'+suffix]=np.where(mask,u< -1e-10,False).sum(axis=(0,1))/count
            pm['mean_worsening_'+suffix]=np.where(mask,np.maximum(-u,0),0).sum(axis=(0,1))/count
            point_errors.append(float(abs(np.where(mask,u,0).sum(axis=(0,1))/count-pm['benefit_'+suffix]).max()))
        pm['benefit_difference']=pm['benefit_b']-pm['benefit_a'];bm['benefit_difference']=bm['benefit_b']-bm['benefit_a']
        for j,r in enumerate(registry):
            pair_rows.append(dict(variable=var,scope=scope,denominator=denominator,lead=lead,**{k:r[k] for k in ['group_a','group_b','station_a','station_b']},n_events=int(count[j]),n_dates=int((daily_counts[:,j]>0).sum()),**{k:float(v[j]) for k,v in pm.items()}))
        for A,B in itertools.combinations(groups,2):
            ids=np.flatnonzero(reg.group_a.eq(A)&reg.group_b.eq(B));point={k:float(x[ids].mean()) for k,x in pm.items()}
            ci_keys=['new_gap'] if scope=='validity' else ['old_gap','new_gap','benefit_a','benefit_b','benefit_difference']
            for key in ci_keys:point.update({key+'_'+k:v for k,v in summary_ci(bm[key][:,ids].mean(axis=1)).items()})
            if scope=='revision':
                point['absolute_gap_reduction']=abs(point['old_gap'])-abs(point['new_gap'])
                cb=abs(bm['old_gap'][:,ids].mean(axis=1))-abs(bm['new_gap'][:,ids].mean(axis=1))
                point.update({'absolute_gap_reduction_'+k:v for k,v in summary_ci(cb).items()})
                point['mean_pair_absolute_gap_reduction']=float((abs(pm['old_gap'][ids])-abs(pm['new_gap'][ids])).mean())
            rows.append(dict(variable=var,scope=scope,denominator=denominator,lead=lead,group_a=A,group_b=B,n_pairs=len(ids),n_a=int(geo.coast_group.eq(A).sum()),n_b=int(geo.coast_group.eq(B).sum()),min_events=int(count[ids].min()),max_events=int(count[ids].max()),min_dates=int((daily_counts[:,ids]>0).sum(axis=0).min()),max_dates=int((daily_counts[:,ids]>0).sum(axis=0).max()),**point))
    print(var+' paired calculation complete',flush=True)
g=pd.DataFrame(rows);pa=pd.DataFrame(pair_rows);co=pd.DataFrame(common_rows);assert max(point_errors)<1e-10
save(g,'contrasts');save(pa,'pairs');save(station_rows,'station_metrics');save(co,'common89_group_mae')
head=g[g.scope.eq('revision')&g.denominator.eq('changed_only')&g.lead.eq('all')];save(head,'headline')
# Reconcile prior humidity raw results: C definitions explicitly kept separate.
old=read('paired_contrasts');old=old[old.method.eq('raw')&old.factor.eq('coast_group')]
comparison_error=0.
for r in old.itertuples():
    scope='validity' if r.scope=='D9_validity' else 'revision';den='all_valid' if scope=='validity' else r.scope.removeprefix('revision_');lead=9 if scope=='validity' else 'all'
    q=g[g.variable.eq(r.variable)&g.scope.eq(scope)&g.denominator.eq(den)&g.lead.eq(lead)&g.group_a.eq(r.group_a)&g.group_b.eq(r.group_b)].iloc[0]
    for key in (['new_gap'] if scope=='validity' else ['old_gap','new_gap','benefit_a','benefit_b','benefit_difference']):comparison_error=max(comparison_error,abs(q[key]-getattr(r,key)))
    assert np.allclose([q.new_gap_low,q.new_gap_high],[r.new_gap_low,r.new_gap_high],atol=1e-10)
    if scope=='revision':assert abs(q.mean_pair_absolute_gap_reduction-r.absolute_gap_reduction)<1e-10
assert comparison_error<1e-10
# Reaggregate saved pair-level values independently through pandas.
keys=['variable','scope','denominator','lead','group_a','group_b'];pp=pa.copy();gg=g.copy();pp['lead']=pp.lead.astype(str);gg['lead']=gg.lead.astype(str)
for key in ['old_mae_a','old_mae_b','new_mae_a','new_mae_b','benefit_a','benefit_b','new_gap']:
    rebuilt=pp.groupby(keys)[key].mean().reset_index();merged=gg.merge(rebuilt,on=keys,suffixes=('','_check'),validate='one_to_one');assert len(merged)==len(g);assert np.allclose(merged[key],merged[key+'_check'],atol=1e-10)
COL={'near':'#168493','transition':'#c68c24','inland':'#ab416f'};EN={'near':'Near coast','transition':'Transition','inland':'Inland'};ZH={'near':'近岸','transition':'過渡','inland':'內陸'};V={'rh_min':'RHmin','rh_max':'RHmax'}
plt.rcParams.update({'font.size':12,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':160})
sections=[];images=[]
def ci(r,k):return f'{r[k]:.3f} [{r[k+"_low"]:.3f}, {r[k+"_high"]:.3f}]'
def verdict(x):return {'positive':'支持正方向','negative':'支持負方向','insufficient':'證據不足','insufficient_bootstrap_support':'重抽有效樣本不足'}[x]
def export(fig,name):fig.savefig(OUT/(name+'.png'));fig.savefig(OUT/(name+'.svg'));plt.close(fig);images.append(name+'.png')
def take(var,A,B,scope='revision',den='changed_only',lead='all'):return g[g.variable.eq(var)&g.group_a.eq(A)&g.group_b.eq(B)&g.scope.eq(scope)&g.denominator.eq(den)&g.lead.eq(lead)].iloc[0]
for var in V:
    fig,axs=plt.subplots(2,3,figsize=(15,8),sharey='row')
    for c,(A,B) in enumerate(itertools.combinations(groups,2)):
        r=take(var,A,B)
        for pos,(group,suffix) in enumerate([(A,'a'),(B,'b')]):
            yy=[r['old_mae_'+suffix],r['new_mae_'+suffix]];axs[0,c].plot([0,1],yy,'o-',color=COL[group],lw=2.5)
            for x,y in enumerate(yy):axs[0,c].annotate(f'{y:.2f}',(x,y),xytext=(0,9 if pos else -16),textcoords='offset points',ha='center',color=COL[group],fontsize=10)
            u=r['benefit_'+suffix];lo=r['benefit_'+suffix+'_low'];hi=r['benefit_'+suffix+'_high'];axs[1,c].errorbar(pos,u,yerr=[[u-lo],[hi-u]],fmt='o',color=COL[group],capsize=5,markersize=8,lw=2)
            axs[1,c].annotate(f'U={u:.2f}',(pos,hi),xytext=(0,9),textcoords='offset points',ha='center',color=COL[group],fontsize=10)
        axs[0,c].set_title(EN[A]+' vs '+EN[B]);axs[0,c].set_xticks([0,1],['Old forecast','New forecast']);axs[0,c].set_xlim(-.25,1.25)
        axs[1,c].set_xticks([0,1],[EN[A],EN[B]]);axs[1,c].set_xlim(-.5,1.5);axs[1,c].axhline(0,color='#777',lw=1)
        for ax in axs[:,c]:ax.grid(axis='y',alpha=.15)
    limits=head[head.variable.eq(var)][['old_mae_a','old_mae_b','new_mae_a','new_mae_b']].to_numpy();axs[0,0].set_ylim(limits.min()-.55,limits.max()+.55)
    axs[0,0].set_ylabel('Validity: MAE (pp)\nLower is better');axs[1,0].set_ylabel('Mean revision benefit U (pp)\nAbove zero = improvement')
    lo=head[head.variable.eq(var)][['benefit_a_low','benefit_b_low']].min().min();hi=head[head.variable.eq(var)][['benefit_a_high','benefit_b_high']].max().max();axs[1,0].set_ylim(min(-.1,lo-.15),hi+.35)
    fig.suptitle(V[var]+' · Raw general forecast · 2025 changed revisions\nD9→D8 through D2→D1 combined; each column uses its own matched events',fontsize=16)
    fig.legend([Line2D([0],[0],color=COL[k],marker='o') for k in groups],[EN[k] for k in groups],loc='lower center',ncol=3,frameon=False);fig.tight_layout(rect=(0,.05,1,.93));name='humidity_overview_'+var;export(fig,name)
    r=take(var,'near','inland')
    sections.append(f'''<section><h2>{V[var]}：同事件validity與revision usefulness</h2><img src="{name}.png"><p><b>為何做這圖：</b>不假設尖沙咀為目標，直接檢查共同預報的地方吻合度與更新效益。上排X=舊／新版本，Y=MAE（pp），越低越吻合；下排X=地理組，Y=平均U，越高改善越多，誤差棒為95%區間。近岸藍綠、過渡橙、內陸紫紅，三欄各用自己的完全同事件樣本。</p><p><b>資料與讀法：</b>每站對只用同目標日、同兩個版本，先平均事件，再跨組站對等權；26站全部保留，跨組共209站對。彙總D9→D8至D2→D1的changed-only事件，不是單一D9或八個lead等權。兩根U誤差棒的重疊不代替配對U差區間。</p><p><b>內陸／近岸發現：</b>近岸MAE {r.old_mae_a:.3f}→{r.new_mae_a:.3f} pp；內陸 {r.old_mae_b:.3f}→{r.new_mae_b:.3f} pp。更新後組差 {ci(r,'new_gap')} pp（{verdict(r.new_gap_direction)}）。近岸U {ci(r,'benefit_a')}、內陸U {ci(r,'benefit_b')} pp；U差 {ci(r,'benefit_difference')} pp（{verdict(r.benefit_difference_direction)}）。差距縮小C {ci(r,'absolute_gap_reduction')} pp（{verdict(r.absolute_gap_reduction_direction)}）。</p><p><b>限制：</b>每欄日期不同，同一組可有略不同數字，不能跨欄相減。所有指標都是對取樣RH極值的事後評分；general不是已確認的區域極值預報。MAE衡量剩餘誤差，U衡量改善量，所以原本較不吻合的組也可能獲益更多。這是探索性固定站群區間，不是因果結論。</p></section>''')
    fig,axs=plt.subplots(1,2,figsize=(14,5.5))
    for group in groups:
        q=co[co.variable.eq(var)&co.group.eq(group)].sort_values('lead');axs[0].plot(q.lead,q.mae,'o-',color=COL[group],label=EN[group])
    for (A,B),color in zip(itertools.combinations(groups,2),['#c68c24','#ab416f','#6857ac']):
        q=g[g.variable.eq(var)&g.scope.eq('validity')&g.group_a.eq(A)&g.group_b.eq(B)].sort_values('lead');axs[1].plot(q.lead,q.new_gap,'o-',color=color,label=EN[B]+' - '+EN[A]);axs[1].fill_between(q.lead.to_numpy(float),q.new_gap_low.to_numpy(),q.new_gap_high.to_numpy(),color=color,alpha=.1)
    axs[0].set_title('Same 89 dates · All 26 stations');axs[0].set_ylabel('MAE (pp)');axs[1].set_title('All available same-day station pairs');axs[1].set_ylabel('Paired MAE difference (pp)');axs[1].axhline(0,color='#777',lw=1)
    for ax in axs:ax.set_xlabel('Lead (days)');ax.set_xticks(range(1,10));ax.legend(fontsize=9);ax.grid(alpha=.15)
    fig.suptitle(V[var]+' · Validity · Raw common forecast',fontsize=16);fig.tight_layout();name='humidity_validity_'+var;export(fig,name)
    r=take(var,'near','inland','validity','all_valid',9)
    sections.append(f'''<section><h2>{V[var]}：全部lead的地方吻合度</h2><img src="{name}.png"><p><b>左圖：</b>X=lead1–9、Y=絕對MAE，三種顏色直接代表三組。每站同樣89個日期，每站先平均，再組內等站權；全年日曆只覆蓋89日，僅描述性，月份覆蓋見CSV。此圖沒有以缺測站偷偷改變組成。</p><p><b>右圖：</b>X同樣lead，Y是B−A配對MAE差，線色代表對比而非單一組；正值表示前一組較不吻合。使用每站對所有可配對日期，保留更多資料；陰影為95%區間。不能把左圖的組差與右圖要求完全一致，因日期不同。</p><p><b>D9主要配對發現：</b>內陸−近岸差 {ci(r,'new_gap')} pp，{verdict(r.new_gap_direction)}；各站對有{int(r.min_dates)}–{int(r.max_dates)}個有效日。所有lead和三組對比均保存，沒有只抽D9作分析。</p><p><b>假設／限制：</b>共同預報不加offset、不按離HKO遠近放寬誤差。不同站對日期交集仍不同、缺測非隨機、每十分鐘取樣可能漏掉真實極值；此處的RHmin/RHmax不是日平均，也不是概率預報區間。</p></section>''')
    fig,axs=plt.subplots(1,3,figsize=(15,5))
    for ax,(A,B) in zip(axs,itertools.combinations(groups,2)):
        q=g[g.variable.eq(var)&g.scope.eq('revision')&g.denominator.eq('changed_only')&g.group_a.eq(A)&g.group_b.eq(B)&g.lead.ne('all')].copy();q['k']=q.lead.astype(int);q=q.sort_values('k')
        for group,suffix in [(A,'a'),(B,'b')]:
            ax.plot(q.k,q['benefit_'+suffix],'o-',color=COL[group],label=EN[group]);ax.fill_between(q.k,q['benefit_'+suffix+'_low'],q['benefit_'+suffix+'_high'],color=COL[group],alpha=.12)
        ax.set_title(EN[A]+' vs '+EN[B]);ax.set_xlabel('New lead k: D(k+1) → Dk');ax.set_xticks(range(1,9));ax.axhline(0,color='#777',lw=1);ax.grid(alpha=.15);ax.legend(fontsize=10)
    axs[0].set_ylabel('Mean revision benefit U (pp)');fig.suptitle(V[var]+' · Revision usefulness by lead · Changed events',fontsize=16);fig.tight_layout();name='humidity_usefulness_'+var;export(fig,name)
    near_inland=g[g.variable.eq(var)&g.scope.eq('revision')&g.denominator.eq('changed_only')&g.group_a.eq('near')&g.group_b.eq('inland')&g.lead.ne('all')]
    lead_findings=f'內陸／近岸比較中，近岸有{int(near_inland.benefit_a_direction.eq("positive").sum())}/8個lead的U區間高於零，內陸有{int(near_inland.benefit_b_direction.eq("positive").sum())}/8個；內陸−近岸U差有{int(near_inland.benefit_difference_direction.eq("positive").sum())}個支持正方向、{int(near_inland.benefit_difference_direction.eq("negative").sum())}個支持負方向、{int(near_inland.benefit_difference_direction.eq("insufficient").sum())}個證據不足。這些lead互相關聯，不能算作八次獨立驗證。'
    sections.append(f'''<section><h2>{V[var]}：更新的效益是否各lead一樣？</h2><img src="{name}.png"><p><b>選軸與目的：</b>X是新版本lead k=1–8，表示D(k+1)→Dk；Y為平均U（pp）。三組顏色固定，分欄以相同事件對比，避免all彙總掩蓋時效差異。高於零表示平均改善，陰影跨零表示該組該lead的方向證據不足；不能從線的上下順序判定兩組差異顯著。</p><p><b>數據：</b>僅確有改動事件、同一目標日實測，站對等權。D9沒有D10舊版可配，不能補造D10→D9修訂。RHmin與RHmax的changed事件各自定義，所以兩變數圖不是完全同一批事件。</p><p><b>發現：</b>{lead_findings}</p><p><b>限制：</b>彙總U不是每個lead保證改善。逐lead區間、改善率、惡化率與平均惡化幅度完整保存在contrasts及pairs CSV；採用同日區塊重抽，不能把重複站對當獨立事件。改善率與平均改善量是兩個不同指標。</p></section>''')
print('plots complete',flush=True)
readme='## 濕度general forecast：不加offset\n\n[濕度理解報告](results/HUMIDITY_REPORT.html)／[方法](HUMIDITY_PLAN.md)。26站（近岸11、過渡11、內陸4），RHmin/RHmax分開；2025回溯，不假設官方目標是HKO，也不假設全港平均或極值包絡。完全從raw每日觀測及預報重算，沒有使用offset訓練係數。\n\n'
headline_html=[]
for var in V:
    r=take(var,'near','inland');text=f'{V[var]}同changed事件彙總：近岸新MAE {r.new_mae_a:.3f}、內陸 {r.new_mae_b:.3f} pp；近岸U {ci(r,"benefit_a")}、內陸U {ci(r,"benefit_b")} pp；U差 {ci(r,"benefit_difference")} pp（{verdict(r.benefit_difference_direction)}）；C {ci(r,"absolute_gap_reduction")} pp（{verdict(r.absolute_gap_reduction_direction)}）。'
    readme+='- '+text+'\n';headline_html.append('<li>'+text+'</li>')
readme+='\n六張圖：每變數的三組同事件舊新MAE／U總覽、D1–D9 validity、D1–D8 revision usefulness。左側三組MAE折線只用89共同日，主要推論使用每對所有共同日；不可混算。來源、全部lead及站對、改善率/惡化率、RMSE/Bias見results/humidity_*.csv。\n\n定義沿用組員U=舊絕對誤差−新絕對誤差，但使用daily_latest情境；主changed-only、all-pairs敏感度。7日區塊bootstrap2000次，固定站群、未校正多重比較。濕度取樣極值、非隨機缺測、內陸僅4站和單一年限制明列。原始站值屬觀測參考，不能證明官方產品代表全港極值；修訂有用不等於足夠準確。\n\n本版C=|組平均G_old|−|組平均G_new|，與general氣溫一致；舊humidity報告使用平均各站對絕對gap縮小量，本版另存mean_pair_absolute_gap_reduction，不混稱同一統計量。\n\n重現：`python build_humidity.py --dependency-dir PATH_TO_DEPS`，再執行`build_analysis.py`整合到共同README/report。\n'
(ROOT/'HUMIDITY_NOTES.md').write_text(readme,encoding='utf-8')
intro='''<h1>Humidity × geography：香港general forecast假設</h1><p>理解用報告；RHmin/RHmax分開、完全不加offset。26站全保留（近岸11、過渡11、內陸4），不是氣溫30站。general只表示共同產品面向香港，並未假設全港平均、區域極值包絡或尖沙咀目標。</p><h2>主要發現：內陸與近岸，同一修訂事件</h2><ul>'''+''.join(headline_html)+'''</ul><h2>資料如何得來、為甚麼配對</h2><p>沿用自行重建的官方歷史讀數，完整日144個名義十分鐘時槽；每天取各站RHmin/RHmax。它們是取樣的一分鐘平均值的極值，不是完整逐分鐘日極值。最新capture規則沿用，缺值不補零。原始每日最後預報與實測相減，沒有訓練或使用HKO offset。</p><p>每站對同一目標日、同一預報版本；修訂同事件評分舊新版本。先在每對共同有效事件內平均，再站對等權。近岸×過渡121對、近岸×內陸44對、過渡×內陸44對；這209對重用相同站及天氣日，不是209個獨立實驗。7日循環目標日區塊bootstrap2000次，同日所有站一起抽；固定站群，不校正多重比較。</p><p>同組在不同對比的數值略有不同，因交集不同；跨欄不能直接相減。描述性三組折線另使用26站、兩變數、所有九lead皆有效的89日交集。主要推論使用站對的全部可用同日資料，仍不能完全修復非隨機缺測。</p><h2>Usefulness與組員定義一致</h2><p>U=|F_old−O|−|F_new−O|；U&gt;0改善、U&lt;0惡化、U=0不變（浮點容差1e−10）。改善率是U&gt;0事件比例，平均U衡量改善幅度，兩者不能互換。每日最後版本相鄰發布日D(k+1)→Dk；主changed-only，all-pairs敏感度。不同地區沒有自己的修訂頻率，共同產品的MAR/FFI未在本輪重做。pp表示百分點，例如RH誤差10→7pp，U=3pp。</p><p>主地域差距縮小量C=|G_old|−|G_new|，G先在對比內站對等權平均。它與舊humidity報告的平均各站對|gap|縮小量不同，後者另存於mean_pair_absolute_gap_reduction；不把兩種C混合比較。</p>'''
tablecols=['variable','group_a','group_b','new_mae_a','new_mae_b','new_gap','new_gap_low','new_gap_high','benefit_a','benefit_b','benefit_difference','benefit_difference_low','benefit_difference_high','absolute_gap_reduction','absolute_gap_reduction_low','absolute_gap_reduction_high','improvement_rate_a','improvement_rate_b','min_events','max_events']
sensitivity=g[g.scope.eq('revision')&g.lead.eq('all')];save(sensitivity,'denominator_sensitivity')
limits='''<h2>限制與證據不足</h2><ul><li>共同預報的確切空間定義仍未獲確認；此處評分是站群地方吻合度，不是官方合格率。</li><li>每十分鐘取樣可能漏極值，完整時槽不等於完整逐分鐘資料。缺測天氣可能有系統性；89日不能代表全年。</li><li>內陸4站、各組站數與環境不同；海岸距離與海拔、建成環境等未分離，不能作因果推論。</li><li>2025已在舊研究看過；結果屬回溯探索。區間跨零表示方向證據不足，不能說完全沒有差異。</li><li>修訂平均有用不表示每次有用或最終已足夠準；沒有預設可接受pp誤差。RHmin/RHmax和氣溫使用不同站群、事件、單位及區塊長度，不直接排名。</li><li>沒有用後見實測風向或其他條件修正預報；沒有以日平均濕度替代極值，也沒有將所有站的日極值合成一個全港包絡。</li></ul>'''
links=['station_inventory','calendar','month_coverage','contrasts','pairs','station_metrics','common89_group_mae','headline','denominator_sensitivity']
footer='<h2>所有海岸對比：same-event彙總</h2>'+head[tablecols].to_html(index=False,float_format=lambda x:f'{x:.3f}')+'<h2>分母敏感度（包含不變版本）</h2>'+sensitivity[['variable','denominator','group_a','group_b','benefit_difference','benefit_difference_direction','absolute_gap_reduction','absolute_gap_reduction_direction']].to_html(index=False,float_format=lambda x:f'{x:.3f}')+limits+'<p>'+' · '.join(f'<a href="humidity_{x}.csv">{x}</a>' for x in links)+'</p><p><a href="../HUMIDITY_PLAN.md">方法</a> · <a href="humidity_metadata.json">來源</a> · <a href="humidity_verification.json">核對</a></p>'
fragment='<section id="humidity-general"><h2>新增：濕度general forecast、不加offset</h2><p>RHmin/RHmax、26站、三個海岸組。完整資料及全部圖見<a href="HUMIDITY_REPORT.html">濕度理解報告</a>。</p><ul>'+''.join(headline_html)+'</ul>'+''.join(sections)+limits+'</section>'
(OUT/'humidity_fragment.html').write_text(fragment,encoding='utf-8')
page='<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>General humidity — 理解用</title><style>body{font:17px/1.75 system-ui;max-width:1250px;margin:35px auto;padding:0 24px;color:#24323c}img{width:100%}section{border-top:1px solid #ccd7dc;margin-top:40px;padding-top:20px}table{border-collapse:collapse;display:block;overflow:auto;font-size:13px}td,th{border:1px solid #ccd7dc;padding:6px;white-space:nowrap}a{color:#168493}</style><body>'+intro+''.join(sections)+footer+'</body></html>'
(OUT/'HUMIDITY_REPORT.html').write_text(page,encoding='utf-8')
sources += [ROOT/'HUMIDITY_PLAN.md',Path(__file__),SRC/'verification.json',ROOT.parent.parent/'04_rq3_revision_usefulness/run_analysis.py']
metadata=dict(year=2025,method='raw; no offset; general common forecast hypothesis',stations=26,group_counts=geo.coast_group.value_counts().to_dict(),common_days=89,bootstrap=dict(reps=2000,block_days=7,seed=3522,fixed_stations=True,multiple_comparisons_adjusted=False),primary_C='absolute gap of pair-averaged group means; legacy pairwise absolute-gap metric also retained separately',images=images,sources=[dict(path=str(x.resolve()),sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in sources])
(OUT/'humidity_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
for link in re.findall(r'(?:src|href)="([^"]+)"',page):
    if link!='humidity_verification.json':assert (OUT/link).exists(),link
audit=dict(passed=True,contrast_rows=len(g),pair_rows=len(pa),station_rows=len(station_rows),common89_rows=len(co),raw_arrays_rebuilt_match_prior=True,prior_D9_and_revision_point_max_error=comparison_error,prior_new_gap_intervals_match=True,legacy_C_matches_separate_pairwise_metric=True,all_pair_means_reaggregated=True,max_benefit_identity_error=max(point_errors),images=len(images),limitations='Bootstrap algorithm not independently reimplemented. Raw source quality and official spatial definition not established by these arithmetic checks.')
(OUT/'humidity_verification.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit),flush=True)
print(head[['variable','group_a','group_b','new_gap','benefit_a','benefit_b','benefit_difference','benefit_difference_direction','absolute_gap_reduction','absolute_gap_reduction_direction']].to_json(orient='records'),flush=True)
