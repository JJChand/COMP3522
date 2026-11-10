"""Reframe audited raw forecasts as a territory-wide common product, no offsets."""
from pathlib import Path
import argparse,json,hashlib,sys,re
p=argparse.ArgumentParser();p.add_argument('--dependency-dir',type=Path);a=p.parse_args()
if a.dependency_dir:sys.path.insert(0,str(a.dependency_dir.resolve()))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;SRC=ROOT/'inputs/temperature';OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
sources=[]
def read(name):
    path=SRC/(name+'.csv');sources.append(path);return pd.read_csv(path,low_memory=False)
def save(frame,name):frame.to_csv(OUT/(name+'.csv'),index=False,encoding='utf-8-sig')
geo=read('station_inventory');assert len(geo)==30
g=read('geographic_contrasts');g=g[g.method.eq('raw')].drop(columns=['is_selected']).copy()
pairs=read('pair_metrics');pairs=pairs[pairs.method.eq('raw')].copy()
stations=read('station_revision_metrics');stations=stations[stations.method.eq('raw')].copy()
v=read('distance_threshold_contrasts');v=v[v.method.eq('raw')&v.scheme.eq('0.50/2.0')&v['sample'].eq('pairwise_available')].copy()
vp=read('distance_pair_metrics');vp=vp[vp.method.eq('raw')].copy()
save(geo,'station_inventory');save(g,'matched_revision_contrasts');save(pairs,'matched_revision_pairs');save(stations,'station_revision_metrics');save(v,'all_forecast_validity');save(vp,'all_forecast_pairs')
# Independent group aggregation checks from audited per-pair records.
keys=['variable','later_lead','denominator','factor','contrast']
metrics=['old_mae_a','old_mae_b','new_mae_a','new_mae_b','benefit_a','benefit_b','usefulness_a','usefulness_b','mean_worsening_contribution_a','mean_worsening_contribution_b']
for frame in [g,pairs,stations]:frame['later_lead']=frame.later_lead.astype(str)
joined=g.merge(pairs.groupby(keys)[metrics].mean().reset_index(),on=keys,suffixes=('','_rebuilt'),validate='one_to_one')
assert len(joined)==len(g)
maxerr=max(float(abs(joined[k]-joined[k+'_rebuilt']).max()) for k in metrics);assert maxerr<1e-10
assert np.allclose(g.old_gap-g.new_gap,g.benefit_difference,atol=1e-10)
assert np.allclose(abs(g.old_gap)-abs(g.new_gap),g.absolute_gap_reduction,atol=1e-10)
for r in v.itertuples():
    B,A=r.contrast.split(' minus ');ac=set(geo[geo.coast_group.eq(A)].station_code);bc=set(geo[geo.coast_group.eq(B)].station_code)
    q=vp[vp.variable.eq(r.variable)&vp.lead.eq(r.lead)]
    pos=q.station_a.isin(ac)&q.station_b.isin(bc);neg=q.station_a.isin(bc)&q.station_b.isin(ac)
    gaps=pd.concat([q.loc[pos,'mae_b_minus_a'],-q.loc[neg,'mae_b_minus_a']])
    assert len(gaps)==r.n_pairs and abs(gaps.mean()-r.mae_gap)<1e-10
assert set(stations.station_code)==set(geo.station_code)
headline=g[g.later_lead.astype(str).eq('all')&g.denominator.eq('changed_only')].copy();save(headline,'headline_all_transitions')
sens=g[g.later_lead.astype(str).eq('all')].pivot(index=['variable','factor','contrast'],columns='denominator',values=['benefit_difference','benefit_difference_direction','absolute_gap_reduction','absolute_gap_reduction_direction']);sens.columns=['_'.join(c) for c in sens.columns];save(sens.reset_index(),'denominator_sensitivity')
COL={'near':'#168493','transition':'#c68c24','inland':'#ab416f'}
CON={'transition minus near':'#c68c24','inland minus near':'#ab416f','inland minus transition':'#6857ac'}
LABEL={'transition minus near':'Transition - near coast','inland minus near':'Inland - near coast','inland minus transition':'Inland - transition'}
ZH={'transition minus near':'過渡−近岸','inland minus near':'內陸−近岸','inland minus transition':'內陸−過渡'}
plt.rcParams.update({'font.size':12,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':160})
sections=[];images=[]
def finish(fig,name):
    fig.tight_layout();fig.savefig(OUT/(name+'.png'));fig.savefig(OUT/(name+'.svg'));plt.close(fig);images.append(name+'.png')
def ci(row,key):return f'{row[key]:.3f} [{row[key+"_ci_low"]:.3f}, {row[key+"_ci_high"]:.3f}]'
def direction(x):return {'positive':'支持正方向','negative':'支持負方向','insufficient':'證據不足'}[x]
overview_sections=[]
from matplotlib.lines import Line2D
group_labels={'near':'Near coast','transition':'Transition','inland':'Inland'}
overview_data=[]
for var in ['Tmax','Tmin']:
    fig,axs=plt.subplots(2,3,figsize=(15,8),sharey='row')
    for column,contrast in enumerate(CON):
        B,A=contrast.split(' minus ')
        row=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq(contrast)].iloc[0]
        for pos,(group,suffix) in enumerate([(A,'a'),(B,'b')]):
            yy=[row['old_mae_'+suffix],row['new_mae_'+suffix]]
            axs[0,column].plot([0,1],yy,'o-',color=COL[group],lw=2.5,markersize=8)
            for x,y in enumerate(yy):axs[0,column].annotate(f'{y:.3f}',(x,y),xytext=(0,9 if pos else -16),textcoords='offset points',ha='center',fontsize=10,color=COL[group])
            u=row['benefit_'+suffix];lo=row['benefit_'+suffix+'_ci_low'];hi=row['benefit_'+suffix+'_ci_high']
            axs[1,column].errorbar(pos,u,yerr=[[u-lo],[hi-u]],fmt='o',color=COL[group],capsize=6,markersize=9,lw=2)
            axs[1,column].annotate(f'U = {u:.3f}',(pos,hi),xytext=(0,10),textcoords='offset points',ha='center',fontsize=10,color=COL[group])
            overview_data.append(dict(variable=var,contrast=contrast,group=group,old_mae=yy[0],new_mae=yy[1],benefit=u,ci_low=lo,ci_high=hi,usefulness_rate=row['usefulness_'+suffix],n_pairs=row.n_pairs,min_events=row.min_events,max_events=row.max_events))
        axs[0,column].set_title(group_labels[A]+' vs '+group_labels[B],fontsize=13)
        axs[0,column].set_xticks([0,1],['Old forecast','New forecast']);axs[0,column].set_xlim(-.25,1.25)
        axs[1,column].set_xticks([0,1],[group_labels[A],group_labels[B]]);axs[1,column].set_xlim(-.5,1.5);axs[1,column].axhline(0,color='#777777',lw=1)
        for ax in axs[:,column]:ax.grid(axis='y',alpha=.15)
    axs[0,0].set_ylabel('Validity: MAE (°C)\nLower is better')
    limits=headline[headline.variable.eq(var)&headline.factor.eq('coast')][['old_mae_a','old_mae_b','new_mae_a','new_mae_b']].to_numpy()
    axs[0,0].set_ylim(float(limits.min())-.20,float(limits.max())+.20)
    axs[1,0].set_ylabel('Revision usefulness U (°C)\nAbove zero = mean improvement')
    axs[1,0].set_ylim(-.03,max(headline[headline.variable.eq(var)&headline.factor.eq('coast')][['benefit_a_ci_high','benefit_b_ci_high']].max())+.09)
    fig.suptitle(var+' · Raw general forecast · 2025 changed revisions\nD9→D8 through D2→D1 combined; each column uses its own matched events',fontsize=16)
    fig.legend([Line2D([0],[0],color=c,marker='o',lw=2) for c in COL.values()],[group_labels[k] for k in COL],ncol=3,loc='lower center',frameon=False)
    fig.tight_layout(rect=(0,.05,1,.93));fn='group_overview_'+var;fig.savefig(OUT/(fn+'.png'));fig.savefig(OUT/(fn+'.svg'));plt.close(fig);images.append(fn+'.png')
    r=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq('inland minus near')].iloc[0]
    reading=(f'Tmax內陸MAE由{r.old_mae_b:.3f}降至{r.new_mae_b:.3f}°C，仍高於近岸的{r.new_mae_a:.3f}°C；但內陸減少{r.benefit_b:.3f}°C，比近岸{r.benefit_a:.3f}°C略多。' if var=='Tmax' else f'Tmin內陸更新後MAE仍為{r.new_mae_b:.3f}°C，高於近岸的{r.new_mae_a:.3f}°C；然而兩組U接近：內陸{r.benefit_b:.3f}、近岸{r.benefit_a:.3f}°C。兩者有用性差的區間跨零，不能說內陸修訂較沒用。')
    overview_sections.append(f'''<section id="overview-{var}"><h2>{var}：三組顏色固定，一起理解validity與revision usefulness</h2><img src="{fn}.png"><p><b>為何選這組圖：</b>讓「誤差剩多少」與「更新改善多少」分開看，避免將內陸較不準等同於修訂沒用。藍綠近岸、橙色過渡、紫紅內陸；三欄依次比較近岸／過渡、近岸／內陸、過渡／內陸，保留全部站點，不是挑三個站。</p><p><b>上排讀法：</b>X只有舊、新兩個預報版本，連線向下代表更新後MAE下降；Y為MAE（°C），越低越吻合。不是把所有舊預報日與所有新預報日各自平均，而是逐事件評分同一目標日的兩個版本，再站對等權。數字是描述性均值，沒有用線條高度代替組差區間。</p><p><b>下排讀法：</b>X是兩個地理組，Y=U=舊絕對誤差−新絕對誤差，點越高表示平均改善越多；誤差棒為95%區間。點高於零不代表每次修訂都改善；兩根誤差棒是否重疊也不能代替配對U差的區間檢定。</p><p><b>實際發現：</b>{reading} 內陸−近岸的U差 {ci(r,'benefit_difference')}°C；地域差距縮小C {ci(r,'absolute_gap_reduction')}°C，{direction(r.absolute_gap_reduction_direction)}。</p><p><b>資料範圍與假設：</b>2025年未修正共同預報、changed-only修訂，D9→D8至D2→D1全部彙總；不是單一D9結果，也不是八個lead等權。每一欄的兩組、舊新和U完全使用同一批配對事件；不同欄的日期交集略不同，因此同組數字可不同，不能跨欄相減。圖中沒有將三組強行拼成同一日期樣本。完整逐lead結果保留於後文。</p></section>''')
overview_frame=pd.DataFrame(overview_data)
assert len(overview_frame)==12 and np.allclose(overview_frame.old_mae-overview_frame.new_mae,overview_frame.benefit,atol=1e-10)
save(overview_frame,'group_overview_values')
pair_explanation='''<section id="why-pair"><h2>為甚麼經常pair，而不是各站獨立計算？</h2><p><b>「各自計算」可以做；「統計上獨立」則不能直接假設。</b>各站的MAE是有用的描述，但若近岸與內陸缺測日期不同，組間差可能同時反映不同季節、寒潮或其他難預報天氣。兩者又共用同一份預報及大範圍天氣，同日誤差有依賴性。</p><h3>這裡其實有兩種pair</h3><ol><li><b>預報修訂配對：</b>同一站、同一目標日、同一實測值，對比舊／新預報。這才回答「這一次修訂令同一件事改善多少」。若新舊預報來自不同目標日，就混入天氣難度。</li><li><b>地理站點配對：</b>近岸站A與內陸站B只用兩站同日都有實測的日期，評分同一版本。先計各日的誤差差，再平均，減少日期組成不一致。這不是只挑一對站：近岸10×內陸5=50對，近岸×過渡150對、過渡×內陸75對，對比內站對等權。</li></ol><h3>一個假設例子（不是本研究實測）</h3><table><tr><th>日期</th><th>近岸絕對誤差</th><th>內陸絕對誤差</th></tr><tr><td>較易預報日</td><td>1°C</td><td>1°C</td></tr><tr><td>較難預報日</td><td>缺測</td><td>4°C</td></tr></table><p>各自平均會得到近岸1°C、內陸2.5°C；但共同那一天兩站都是1°C。不能從不一致的日期直接說內陸天生較差。配對只顯示已觀測共同日沒有差異，仍不能知道近岸在缺測日的誤差；不能宣稱已解決全部缺測偏差。</p><h3>甚麼時候不用逐站pair也可以？</h3><ul><li>純粹描述各站在其可用日期的表現，可以獨立算MAE，但清楚標示不同樣本，不用來直接判斷地理差異。</li><li>若各站使用完全相同的日期、版本及權重，直接比較組平均與對應的平均差可一致；逐站pair不是唯一方法。</li><li>可採所有站的共同日期，先每天算各組平均，再同日比組；或另建控制日期／天氣因素的模型。本次沿用站對交集，因全部30站×兩變數×D1–D9的嚴格交集只有13日。按單一變數／lead取交集可有更多日，不能把13日當所有方案的共同天數。</li></ul><p><b>Pair不會製造獨立樣本：</b>50個內陸／近岸站對會重用同一站與同一天，不能當50個獨立實驗。所以現有區間按目標日區塊一起重抽所有站及事件，而不是把每條站對記錄獨立重抽。不同站對仍有不同日期、站群小、未控制海拔與建成環境，結論仍限於目前樣本。</p><h3>為甚麼內陸較不準，但修訂不一定較沒用？</h3><p>MAE衡量<b>剩餘誤差的水平</b>，U衡量<b>這一次更新的改善量</b>。例如一組誤差3.0→2.7°C（改善0.3），另一組1.5→1.3°C（改善0.2），前者更新後仍較不準，卻改善更多。這是算術例子，不代表內陸一定有較大改善空間；真正方向仍由同事件U差的區間判斷。</p></section>'''
for var in ['Tmax','Tmin']:
    fig,ax=plt.subplots(figsize=(10,5.6));find=[]
    for contrast,color in CON.items():
        q=v[v.variable.eq(var)&v.contrast.eq(contrast)].sort_values('lead')
        ax.plot(q.lead,q.mae_gap,'o-',color=color,label=LABEL[contrast]);ax.fill_between(q.lead,q.ci_low,q.ci_high,color=color,alpha=.1)
        r=q[q.lead.eq(9)].iloc[0];find.append(f'{ZH[contrast]} D9差 {r.mae_gap:.3f}°C [{r.ci_low:.3f}, {r.ci_high:.3f}]；{direction(r.direction)}')
    ax.axhline(0,color='#555',lw=1);ax.set_xticks(range(1,10));ax.set_xlabel('Lead (days)');ax.set_ylabel('Paired MAE difference (°C)');ax.set_title(var+' · Raw common forecast · All valid forecast days');ax.legend();ax.grid(alpha=.15)
    name='validity_'+var;finish(fig,name)
    sections.append(f'''<section><h2>{var} validity：共同預報較貼近哪一組？</h2><img src="{name}.png"><p><b>目的／選軸：</b>X=預報lead 1–9，顯示地方吻合度是否隨時效不同；Y=圖例前一組減後一組的同日MAE差，正值表示前一組較不吻合，負值相反。此圖是組差，不是各組MAE，零也不是零預報誤差。</p><p><b>資料如何得來：</b>全部有效預報日，兩站使用同一版本同一天；先在各站對的共同有效日平均絕對誤差差，再對跨組站對等權。三條線分別為過渡−近岸、內陸−近岸、內陸−過渡；陰影95%日期區塊bootstrap區間。</p><p><b>發現：</b>{'；'.join(find)}。</p><p><b>假設／限制：</b>每對交集不同，缺測組成仍可能影響；三條線也不一定可相減得到另一條。距海門檻是研究選擇，不是官方分區。不能據此把general預報判定為官方逐站失準，亦不能與下圖changed-only事件的MAE直接相減。</p></section>''')
    q=g[g.variable.eq(var)&g.factor.eq('coast')&g.contrast.eq('inland minus near')&g.denominator.eq('changed_only')&g.later_lead.astype(str).ne('all')].copy();q['lead']=q.later_lead.astype(int);q=q.sort_values('lead')
    fig,axs=plt.subplots(1,2,figsize=(14,5.5))
    for group,suffix in [('near','a'),('inland','b')]:
        for vintage,ls in [('old','--'),('new','-')]:axs[0].plot(q.lead,q[vintage+'_mae_'+suffix],ls+'o',color=COL[group],label=group+' / '+vintage)
        axs[1].plot(q.lead,q['benefit_'+suffix],'o-',color=COL[group],label=group)
        axs[1].fill_between(q.lead,q['benefit_'+suffix+'_ci_low'],q['benefit_'+suffix+'_ci_high'],color=COL[group],alpha=.12)
    axs[0].set_ylabel('MAE (°C)');axs[0].set_title('Same events: old versus new forecast')
    axs[1].set_ylabel('Mean absolute-error reduction U (°C)');axs[1].set_title('Revision usefulness');axs[1].axhline(0,color='#555',lw=1)
    for ax in axs:ax.set_xlabel('New lead k: D(k+1) → Dk');ax.set_xticks(range(1,9));ax.grid(alpha=.15);ax.legend(fontsize=10)
    fig.suptitle(var+' · Inland versus near coast · Changed revisions',fontsize=16);name='matched_'+var;finish(fig,name)
    r=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq('inland minus near')].iloc[0]
    sections.append(f'''<section><h2>{var}：內陸與近岸，同一修訂是否都有用？</h2><img src="{name}.png"><p><b>目的：</b>將validity與revision usefulness限制在完全同一修訂事件，以免把不同樣本的表現誤當改善。這個內陸／近岸對比保留50個跨組站對；其他對比完整結果另列。</p><p><b>X軸：</b>新版本lead k，k=1代表D2→D1，k=8代表D9→D8；沒有D10資料，所以沒有D10→D9。<b>左Y：</b>相同事件上的絕對MAE，虛線舊／實線新；藍綠近岸，紫紅內陸，越低越好。<b>右Y：</b>U=舊絕對誤差−新絕對誤差；高於零才代表平均改善，陰影為95%區間。</p><p><b>數據：</b>每站對先平均有效changed-only事件，再站對等權。同一對比的兩組、舊新及U完全同事件。彙總所有轉換時，近岸MAE {r.old_mae_a:.3f}→{r.new_mae_a:.3f}°C、內陸 {r.old_mae_b:.3f}→{r.new_mae_b:.3f}°C；近岸U {ci(r,'benefit_a')}、內陸U {ci(r,'benefit_b')}°C。改善率各為 {r.usefulness_a:.1%}、{r.usefulness_b:.1%}；這是誤差變小的事件比例，不是預報準確率。</p><p><b>發現及限制：</b>內陸原本較不吻合，不表示更新一定較沒用。平均U與改善率也不同：少數大幅惡化可抵消多次小改善。all彙總按各站對事件平均，不是八個lead等權，亦不保證每個lead都有足夠改善證據。此為事後有用性，不是機率預報的校準reliability。</p></section>''')
    fig,axs=plt.subplots(1,2,figsize=(14,5.5));details=[]
    for contrast,color in CON.items():
        z=g[g.variable.eq(var)&g.factor.eq('coast')&g.contrast.eq(contrast)&g.denominator.eq('changed_only')&g.later_lead.astype(str).ne('all')].copy();z['lead']=z.later_lead.astype(int);z=z.sort_values('lead')
        for ax,key in zip(axs,['benefit_difference','absolute_gap_reduction']):
            ax.plot(z.lead,z[key],'o-',color=color,label=LABEL[contrast]);ax.fill_between(z.lead,z[key+'_ci_low'],z[key+'_ci_high'],color=color,alpha=.1)
        r=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq(contrast)].iloc[0]
        details.append(f'{ZH[contrast]}：U差 {ci(r,"benefit_difference")}°C（{direction(r.benefit_difference_direction)}）；差距縮小量C {ci(r,"absolute_gap_reduction")}°C（{direction(r.absolute_gap_reduction_direction)}）')
    for ax in axs:ax.axhline(0,color='#555',lw=1);ax.set_xlabel('New lead k: D(k+1) → Dk');ax.set_xticks(range(1,9));ax.grid(alpha=.15);ax.legend(fontsize=9)
    axs[0].set_ylabel('Difference in revision benefit (°C)');axs[0].set_title('Which group benefits more?')
    axs[1].set_ylabel('Absolute group-gap reduction C (°C)');axs[1].set_title('Does the geographical gap shrink?')
    fig.suptitle(var+' · Raw common forecast · Same changed events',fontsize=16);name='gap_'+var;finish(fig,name)
    sections.append(f'''<section><h2>{var}：誰獲益更多？地域差距有縮小嗎？</h2><img src="{name}.png"><p><b>為何需要兩張：</b>兩組都改善，不代表差距縮小。左Y=U_B−U_A，正值表示圖例前一組獲益更多；右Y=C=|G_old|−|G_new|，正值表示兩組MAE絕對差距縮小。X為新版本lead，三色對應三個跨組比較，陰影是95%區間。</p><p><b>數據與讀法：</b>兩張圖均使用上一節相同的站對同事件方法，但每條對比線有自己的交集。若G不轉號，U差與C可相同；若接近零或重抽時轉號，兩者區間可以不同。因此不能用左圖支持正方向就自動宣稱右圖差距顯著縮小。</p><p><b>全部轉換彙總發現：</b>{'；'.join(details)}。</p><p><b>限制：</b>彙總結果不等於每個lead的結果；跨零只能說方向證據不足，不能說毫無影響。C使用先站對等權形成的組間gap，不是各站對|gap|縮小量的平均。全相鄰版本敏感度另見表，不以changed-only改善率代表所有預報日。</p></section>''')
table=[]
for r in headline[headline.factor.eq('coast')].iterrows():
    r=r[1];table.append(dict(變數=r.variable,對比=ZH[r.contrast],新MAE差=ci(r,'new_gap'),後組U=ci(r,'benefit_a'),前組U=ci(r,'benefit_b'),U差=ci(r,'benefit_difference'),差距縮小C=ci(r,'absolute_gap_reduction'),C判讀=direction(r.absolute_gap_reduction_direction)))
table=pd.DataFrame(table)
summary=[]
for var in ['Tmax','Tmin']:
    r=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq('inland minus near')].iloc[0]
    summary.append(f'<li><b>{var}：</b>同修訂事件中，更新後內陸比近岸的MAE仍高 {ci(r,"new_gap")}°C。兩組U：近岸 {ci(r,"benefit_a")}、內陸 {ci(r,"benefit_b")}°C。差距縮小量 {ci(r,"absolute_gap_reduction")}°C：{direction(r.absolute_gap_reduction_direction)}。</li>')
intro='''<h1>把九天預報視為香港共同預報：地方validity與revision usefulness</h1><p>私人理解用版本。研究假設：共同預報面向香港地區，不假設以尖沙咀為目標。也不把它自行定義成全港平均、人口加權平均或全港各站極值。主分析完全不加offset，不使用距HKO的容忍額度。</p><h2>可以回答甚麼？</h2><p>「同一份預報對哪些站群較吻合？同一次更新對哪些站群較有用？更新是否縮小地理組間的誤差差距？」不是比較不同地區自己的預報。general定位也不代表應消除所有地域溫差；本版本保留這些差異，將它們視為共同產品地方適用性的部分。</p><h2>主要發現：相同修訂事件</h2><ul>'''+''.join(summary)+'''</ul><p>氣溫較不吻合與修訂較沒有用是兩個不同結論。以下圖表保留全部lead和三個海岸對比，不只展示內陸／近岸。</p><h2>如何公平比較？</h2><ol><li>保留30站：近岸10、過渡15、內陸5；NGP保留，TMS/TC按既定範圍排除。有效C觀測，不補缺值。</li><li>2025年、每日最後存檔版本，HKT日曆lead。全年validity D1–D9；修訂用相鄰發布日D(k+1)→Dk。</li><li>跨組兩站必須同一天都有觀測，評分同一預報版本；同修訂分析的舊新MAE、U與C完全同事件。先站對平均，再跨組站對等權。</li><li>主修訂分析只算該變數確有改動事件；全部相鄰版本另作敏感度。Tmax與Tmin的changed事件不同，不能直接把兩者U大小作完全同事件比較。</li><li>沿用2000次14日循環日期區塊bootstrap，seed3522；同日所有站與事件一起重抽。固定站群、未校正多重比較；區間不等於因果證明。</li></ol><p>本版重用已審計的raw結果，重新核對站對彙總，沒有重新擬合模型。只改變研究問題的解讀，原始F−O與U計算沒有因假設改變。2025已被研究過，是回溯分析。</p><h2>指標與組員方法對齊</h2><p>Validity使用MAE、RMSE、Bias（F−O；正值偏高）。Reliability在本輪具體指revision usefulness：U=|F_old−O|−|F_new−O|，改善率為U&gt;0的比例；與組員RQ3一致。使用daily_latest配對，並非組員consecutive_le24h主情境。因所有站收到相同預報，不能說內陸本身有更多修訂；MAR/FFI/修訂頻率應整體報告，本輪沒有重算。此處亦不是機率校準reliability。</p><p>同一組在不同對比中的MAE略有不同是因為配對日期不同，不應將不同對比的數字拼成一條通用地區MAE線。所有彙總使用相同的該對比事件；all是站對內事件平均，不是lead等權平均。</p>'''
appendix='''<h2>相同修訂事件的全部海岸彙總</h2><p>前組／後組依「對比」順序；例如內陸−近岸，前組是內陸。數值單位°C，方括號為95%區間。</p>'''+table.to_html(index=False)+'''<h2>全部相鄰版本敏感度</h2><p>以下同時保留沒有改動的事件；這些事件U=0。分母與changed-only不同，改善率會不同，不能混稱同一指標。</p>'''+sens.reset_index().to_html(index=False)+'''<h2>四區附錄與完整資料</h2><p>四區依行政區：港島、九龍、新界、離島；不是都市化程度。所有四區對比及區間保存在下列完整CSV，海岸為本次主圖。四區結果僅作補充探索。</p>'''+headline[headline.factor.eq('region')][['variable','contrast','new_gap','new_gap_ci_low','new_gap_ci_high','benefit_difference','benefit_difference_ci_low','benefit_difference_ci_high','absolute_gap_reduction','absolute_gap_reduction_ci_low','absolute_gap_reduction_ci_high']].to_html(index=False,float_format=lambda x:f'{x:.3f}')+'''<h2>仍不足以說甚麼？</h2><ul><li>不能證明海岸距離導致誤差；海拔、建成環境等可混雜。內陸5站不能代表所有內陸位置。</li><li>未確認官方general預報的空間統計定義；本輪是站群適用性評估，不能直接取代官方準確率。</li><li>配對沒有完全解決不同站對的日期／季節組成及非隨機缺測；單一年、探索性多重對比。</li><li>修訂有用不表示最終預報已足夠準確；需要另定用途容許誤差。誤差較大也不等於修訂較沒用。</li><li>沒有雨量或濕度新分析，沒有將general假設證明為事實；沒有因結果刪站。</li></ul><h2>完整輸出與來源</h2>'''
files=['station_inventory','all_forecast_validity','all_forecast_pairs','matched_revision_contrasts','matched_revision_pairs','station_revision_metrics','headline_all_transitions','denominator_sensitivity','group_overview_values']
sections=overview_sections+[pair_explanation]+sections
appendix+='<p>'+' · '.join(f'<a href="{name}.csv">{name}</a>' for name in files)+'</p><p><a href="../PLAN.md">固定解讀與方法</a> · <a href="metadata.json">來源hash</a> · <a href="verification.json">核對範圍</a></p>'
page='<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>General Hong Kong forecast — 理解用</title><style>body{font:17px/1.75 system-ui;max-width:1250px;margin:35px auto;padding:0 24px;color:#24323c}img{width:100%}section{border-top:1px solid #ccd7dc;margin-top:40px;padding-top:20px}table{border-collapse:collapse;font-size:13px;display:block;overflow:auto}td,th{border:1px solid #ccd7dc;padding:6px;white-space:nowrap}a{color:#168493}</style><body>'+intro+''.join(sections)+appendix+'</body></html>'
if (OUT/'humidity_fragment.html').exists():
    page=page.replace('</body>',(OUT/'humidity_fragment.html').read_text(encoding='utf-8')+'</body>')
    page=page.replace('<body>','<body><p><a href="#humidity-general">跳至濕度general forecast：RHmin／RHmax</a> · <a href="HUMIDITY_REPORT.html">濕度完整數據與限制</a></p>',1)
    page=page.replace('沒有雨量或濕度新分析，沒有將general假設證明為事實','本版沒有雨量分析；濕度另見新增章節。沒有將general假設證明為事實')
(OUT/'UNDERSTANDING_REPORT.html').write_text(page,encoding='utf-8')
readme='# 香港general forecast情境 — 未修正氣溫\n\n[理解報告](results/UNDERSTANDING_REPORT.html)；[方法與假設](PLAN.md)。\n\n不假設TST為預報目標，也不假設全港平均。完全不加offset。30站、2025、Tmax/Tmin分開；海岸10/15/5站，四區完整數據作附錄。沿用已審計raw資料，並非重新訓練或新獨立實驗。\n\n'
for var in ['Tmax','Tmin']:
    r=headline[headline.variable.eq(var)&headline.factor.eq('coast')&headline.contrast.eq('inland minus near')].iloc[0]
    readme+=f'- {var}內陸−近岸（同changed事件、all轉換）：新MAE差 {ci(r,"new_gap")}°C；近岸U {ci(r,"benefit_a")}，內陸U {ci(r,"benefit_b")}°C；C {ci(r,"absolute_gap_reduction")}°C，{direction(r.absolute_gap_reduction_direction)}。\n'
readme+='\n第一組圖為所有有效預報日D1–D9，其他圖為完全同事件的validity/U/C，新lead1–8。樣本不可混算。每張圖交代軸、讀法、數據、假設與結論。完整CSV包括所有lead、站對、站點、四區及all-pairs敏感度；RMSE/Bias可在站對表查閱。\n\nReliability此處只指修訂有用性，不是校準或穩定性；共用預報不能按地區有不同修訂頻率。不同站對仍有不同日期交集；2000次14日區塊bootstrap固定站群、未校正多重比較。區間沿用既有分析，本版未獨立重寫bootstrap。不能說已足夠準確或海岸造成差異。\n\n重現：`python build_analysis.py --dependency-dir PATH_TO_DEPS`。核對站對彙總及恆等式，來源hash及驗證見results/metadata.json和verification.json。\n'
readme+='\n## 圖解與為甚麼配對\n\n新增Tmax/Tmin各一張固定三組顏色的圖：上排舊新MAE，下排U與95%區間；三欄各自使用相同事件比較近岸／過渡、近岸／內陸、過渡／內陸。數字見results/group_overview_values.csv。[配對方法解釋](results/UNDERSTANDING_REPORT.html#why-pair)區分修訂pair、地理站對、各站獨立描述及統計依賴，也說明共同日期方案與缺測限制。三個對比的同組數字可能不同，不得跨欄相減。\n'
if (ROOT/'HUMIDITY_NOTES.md').exists():
    readme=readme.replace('# 香港general forecast情境 — 未修正氣溫','# 香港general forecast情境 — 未修正氣溫與濕度',1)
    readme+='\n'+(ROOT/'HUMIDITY_NOTES.md').read_text(encoding='utf-8')
readme+='\n## 提交版本與重現\n\n本次提交以本資料夾的 general forecast 結果為最新版本；不加 offset。所需輸入快照放在 inputs/，安裝及重建步驟、來源範圍見 [REPRODUCING.md](REPRODUCING.md)。inputs/ 中舊驗證文件只供來源追蹤，不是本次新增實驗結果。\n'
(ROOT/'README.md').write_text(readme,encoding='utf-8')
sources += [ROOT/'PLAN.md',Path(__file__),SRC/'source_plan.md',BASE.parent/'04_rq3_revision_usefulness/run_analysis.py',SRC/'run_metadata.json',SRC/'geography_verification.json',SRC/'distance_metadata.json']
metadata=dict(scenario='Hypothetical general Hong Kong common forecast; raw only; no spatial-average assumption',year=2025,station_counts=geo.coast_group.value_counts().to_dict(),images=images,sources=[dict(path=str(x.resolve()),sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in sources],reuse='Existing raw point estimates and bootstrap intervals; no independent new evidence',bootstrap='2000 circular 14-day calendar blocks, seed 3522, fixed stations, unadjusted exploratory intervals')
(OUT/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
for link in re.findall(r'(?:src|href)="([^"]+)"',page):
    if link.startswith('#'):
        assert f'id="{link[1:]}"' in page,link
    elif not link.startswith('http') and link!='verification.json':assert (OUT/link.split('#')[0]).exists(),link
audit=dict(passed=True,geographic_raw_rows=len(g),pair_raw_rows=len(pairs),all_forecast_contrasts=len(v),all_stations_retained=True,max_group_reaggregation_error=maxerr,all_validity_gaps_reaggregated=True,gap_benefit_identities=True,images_and_links=len(images),limits='Raw source values previously independently checked; this run reaggregates saved pair outputs. Bootstrap not independently reimplemented.')
(OUT/'verification.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit),flush=True)
