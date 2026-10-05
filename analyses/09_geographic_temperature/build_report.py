"""Build GitHub findings, figures and an offline all-station result viewer."""
from pathlib import Path
import sys,argparse,json
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--dependency-dir',type=Path);args=parser.parse_args()
if args.dependency_dir:sys.path.insert(0,str(args.dependency_dir.resolve()))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=ROOT/'results'
def read(n):return pd.read_csv(OUT/(n+'.csv'))
def md(df):
    def fmt(v):return f'{v:.3f}' if isinstance(v,(float,np.floating)) else str(v)
    return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
def ht(df):return '<div class="scroll">'+df.to_html(index=False,border=0,float_format=lambda x:f'{x:.3f}')+'</div>'
names={'coast':'海岸距離','region':'四大區','near':'近岸','transition':'海岸過渡','inland':'內陸','HKI':'港島','KL':'九龍','NT':'新界','Islands':'離島區'}
groups={'coast':['near','transition','inland'],'region':['HKI','KL','NT','Islands']}
colours=['#187e89','#c18b2a','#a6446b','#6558a6']
meta=json.loads((OUT/'run_metadata.json').read_text(encoding='utf-8'));geo=read('station_inventory');g=read('group_metrics');s=read('station_metrics');pan=read('station_panels');off=read('station_HKO_observed_offsets')
d3=g[(g.design=='all_available')&(g.lead==3)][['factor','group','variable','n_stations','station_days_min','station_days_max','mae','rmse','bias']].replace(names)
d3.columns=['因素','組別','變數','站數','最少配對日／站','最多配對日／站','MAE °C','RMSE °C','Bias °C']
strict=g[(g.design=='strict_common')&(g.lead==3)][['factor','group','variable','n_stations','mae','rmse','bias']].replace(names)
strict.columns=['因素','組別','變數','站數','MAE °C','RMSE °C','Bias °C']
stationd3=s[(s.design=='all_available')&(s.lead==3)].merge(geo[['station_code','name_zh','coast_group','region_group','elevation_m']],on='station_code')[['station_code','name_zh','coast_group','region_group','elevation_m','variable','n','mae','rmse','bias']].replace(names)
stationd3.columns=['站碼','站名','海岸組','地區','海拔 m','變數','配對日','MAE °C','RMSE °C','Bias °C']
panelshow=pan[['factor','group','n_stations','stations']].replace(names);panelshow.columns=['因素','組別','站數','全部站碼']
plt.rcParams.update({'font.family':['Microsoft JhengHei','DejaVu Sans'],'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.15,'svg.fonttype':'none'})
fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
for i,factor in enumerate(groups):
 for j,v in enumerate(['Tmax','Tmin']):
  ax=axes[i,j]
  for group,c in zip(groups[factor],colours):
   q=g[(g.design=='all_available')&(g.factor==factor)&(g.variable==v)&(g.group==group)].sort_values('lead')
   ax.plot(q.lead,q.mae,'o-',label=names[group],color=c)
  ax.set(title=names[factor]+' · '+v,ylabel='站點等權 MAE (°C)',xlabel='Lead (日)',xticks=range(1,10));ax.legend(fontsize=9)
fig.suptitle('全站、全部有效配對｜描述性比較：各站日期不同',fontsize=15)
for ext in ['png','svg']:fig.savefig(OUT/('temperature_all_station_leads.'+ext),dpi=170)
plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(13,10),constrained_layout=True)
ordered=geo[geo.in_main_panel].sort_values(['region_group','station_code']).station_code.tolist()
for ax,v in zip(axes,['Tmax','Tmin']):
 q=s[(s.design=='all_available')&(s.variable==v)&(s.lead==3)].set_index('station_code').loc[ordered]
 colours2=[colours[groups['region'].index(geo.set_index('station_code').loc[c,'region_group'])] for c in ordered]
 ax.barh(range(len(q)),q.mae,color=colours2);ax.set(yticks=range(len(q)),yticklabels=[c+' '+geo.set_index('station_code').loc[c,'name_zh'] for c in ordered],title='D3 '+v,xlabel='逐站 MAE (°C)');ax.invert_yaxis();ax.tick_params(axis='y',labelsize=8)
fig.suptitle('全部 30 個主分析站｜各站使用全部有效配對日期',fontsize=15)
for ext in ['png','svg']:fig.savefig(OUT/('temperature_all_stations_D3.'+ext),dpi=170)
plt.close(fig)
method='''## 方法與解讀

- 研究期：2022-01-01 至 2025-12-31，1,461 個日曆日。D1–D9，Tmax／Tmin 分開，D0 不納入。
- 全部 30 個完整期 AWS 候選都納入，沒有 top-3、top-N 或按誤差選站。TMS、TC 依既定範圍排除；HKO 作基準，HKA 及搬站／非完整期站不進主分組。37 站的資格及缺值均保留在 station_inventory.csv。
- 海岸：近岸 ≤0.5 km；過渡 >0.5–2 km；內陸 >2 km。四大區按行政區分：港島、九龍、新界、離島區。離島不再併入新界，亦不是把所有地理上的島嶼都改列離島區。
- 每個目標日／發布日取最後存檔版本。Lead 為香港時間日曆差。只接受 C 且有數值的觀測，不補值、不以零代缺值。
- 全部有效資料（all_available）：每站用其全部有效配對日；組別 MAE = 各站 MAE 等權平均，RMSE = 各站 MSE 等權平均後開根號，Bias = 各站 Bias 等權平均。避免資料較多的站支配結果。另列 pooled_station_day_mae 供核對。
- 嚴格共同日期（strict_common）：同時要求 30 站、Tmax／Tmin、D1–D9 都有效。只有 24 日；每年分布為 4、3、4、13 日。這是稀疏診斷，並非四年天氣的充分代表樣本。
- 低海拔敏感度（lowland_available）：所有 <300 m 的合資格站，共 29 站。主分析仍保留昂坪 NGP（593 m）；只排除 TMS／TC 不等於排除全部高海拔站。
- 每個有正負號的誤差為 F−O。95% 區間使用 2,000 次、14 日循環日曆區塊重抽（seed 3522），同日所有站一起抽。區間只反映固定站點與缺值模式下的時間不確定性，不能修復各站日期不一致或 24 日樣本過少；未作多重比較校正。
- 當代海岸／行政區作固定地理代理；沒有重建 2022–2025 海岸變動。排除 TMS／TC 是在前一輪結果後按研究範圍修訂，不聲稱預先註冊。

## 觀測地域差異與 HKO baseline

本次另計算所有主站相對 HKO 同日實測的差異：`station_HKO_observed_offsets.csv` 列出 O_station−O_HKO 的均值、中位數、標準差及分位數。它是研究期觀測差異，不是長期氣候常值。

`HKO_error_decomposition.csv` 在相同三方有效日期核對：

`F − O_station = (F − O_HKO) + (O_HKO − O_station)`。

這個等式適用於 signed error／Bias，不能把 MAE 相加或相減。這些結果用來區分地域差異和基準預報誤差，沒有用全期觀測修正預報再在同一資料評分，亦沒有假裝建立官方逐站預報。

## 可以與不可以說的結論

1. 使用全站全部有效資料時，D3 描述性均值顯示近岸 MAE 小於內陸；港島小於新界。這與先前小站群的某些方向一致，但本次數值已改用全部站，不能沿用之前三站的數值或主張。
2. 所有站的觀測日期不同，所以以上不能當作完全控制天氣條件的公平排名。嚴格共同日期僅有 24 日，不足以對四年間穩定的地理排名給出強結論。
3. 離島有 4 站，含 593 m 的昂坪；其均值與其他地區的差異不能歸因於「離島」本身。應同看 29 站低海拔敏感度及逐站數據。
4. 「證據不足以支持穩定地區排名」是有效結果；不是證明地理因素沒有關聯。這裡也沒有足夠設計識別獨立或因果效果。
5. 研究對象是同一份公共預報的地方吻合程度，不是各站自己的預報能力；未取得本研究期 ARWF 歷史發布版本。人口、雨量、城市化、revision reliability 均不屬本目錄範圍。
'''
findings='# Geographic temperature representativeness — all eligible stations\n\n氣溫 × 海岸距離，以及氣溫 × 港島／九龍／新界／離島。2026-10-05 執行。\n\n## 核心結果\n\n**全部 30 個合資格站，沒有抽三站。** 全部 D1–D9、Tmax／Tmin 共 **670,865 筆有效站日預報配對**；同一站日出現在不同 lead 屬不同預報個案，不是獨立觀測日。完整逐筆壓縮檔留在 Git 倉庫外，避免把大型資料副本提交。\n\n**資料限制本身就是結果：全站嚴格共同日期只有 24 日（1.64%）。** 主表保留每站全部有效資料作描述；不能在日期不一致的情況下宣稱地理因素造成預報更準。\n\n## 全部站群\n\n'+md(panelshow)+'\n\n## D3 全部有效資料（站點等權，日期不同）\n\n'+md(d3)+'\n\n![All-station lead curves](temperature_all_station_leads.png)\n\n## D3 嚴格共同 24 日（稀疏診斷）\n\n'+md(strict)+'\n\n## 全部 30 站的 D3 明細\n\n'+md(stationd3)+'\n\n![All 30 stations](temperature_all_stations_D3.png)\n\n'+method+'\n## 結果索引\n\n[互動全站檢視](report.html) · [完整站點分數](station_metrics.csv) · [完整組別分數](group_metrics.csv) · [配對覆蓋](pairing_coverage.csv) · [站點資格](station_inventory.csv) · [共同日期](strict_common_dates.csv) · [來源與版本](run_metadata.json) · [獨立核對](verification.json)\n'
(OUT/'findings.md').write_text(findings,encoding='utf-8')
data={n:json.loads(read(n).to_json(orient='records',force_ascii=False)) for n in ['station_inventory','station_metrics','group_metrics','group_contrasts']};data['land']=json.loads((ROOT/'inputs/map_land.json').read_text())
template=(ROOT/'viewer_template.html').read_text(encoding='utf-8')
for k,v in {'__DATA__':json.dumps(data,ensure_ascii=False,allow_nan=False).replace('</','<\\/'),'__PANEL__':ht(panelshow),'__D3__':ht(d3),'__STATIONS__':ht(stationd3)}.items():template=template.replace(k,v)
(OUT/'report.html').write_text(template,encoding='utf-8')
print('Built findings.md, all-station viewer and 4 figure files.')
