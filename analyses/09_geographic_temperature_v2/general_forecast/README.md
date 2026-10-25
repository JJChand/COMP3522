# 香港general forecast情境 — 未修正氣溫與濕度

[理解報告](results/UNDERSTANDING_REPORT.html)；[方法與假設](PLAN.md)。

不假設TST為預報目標，也不假設全港平均。完全不加offset。30站、2025、Tmax/Tmin分開；海岸10/15/5站，四區完整數據作附錄。沿用已審計raw資料，並非重新訓練或新獨立實驗。

- Tmax內陸−近岸（同changed事件、all轉換）：新MAE差 1.035 [0.885, 1.180]°C；近岸U 0.183 [0.116, 0.245]，內陸U 0.236 [0.180, 0.290]°C；C 0.053 [0.006, 0.102]°C，支持正方向。
- Tmin內陸−近岸（同changed事件、all轉換）：新MAE差 1.254 [1.010, 1.489]°C；近岸U 0.224 [0.114, 0.327]，內陸U 0.219 [0.111, 0.323]°C；C -0.006 [-0.029, 0.015]°C，證據不足。

第一組圖為所有有效預報日D1–D9，其他圖為完全同事件的validity/U/C，新lead1–8。樣本不可混算。每張圖交代軸、讀法、數據、假設與結論。完整CSV包括所有lead、站對、站點、四區及all-pairs敏感度；RMSE/Bias可在站對表查閱。

Reliability此處只指修訂有用性，不是校準或穩定性；共用預報不能按地區有不同修訂頻率。不同站對仍有不同日期交集；2000次14日區塊bootstrap固定站群、未校正多重比較。區間沿用既有分析，本版未獨立重寫bootstrap。不能說已足夠準確或海岸造成差異。

重現：`python build_analysis.py --dependency-dir PATH_TO_DEPS`。核對站對彙總及恆等式，來源hash及驗證見results/metadata.json和verification.json。

## 圖解與為甚麼配對

新增Tmax/Tmin各一張固定三組顏色的圖：上排舊新MAE，下排U與95%區間；三欄各自使用相同事件比較近岸／過渡、近岸／內陸、過渡／內陸。數字見results/group_overview_values.csv。[配對方法解釋](results/UNDERSTANDING_REPORT.html#why-pair)區分修訂pair、地理站對、各站獨立描述及統計依賴，也說明共同日期方案與缺測限制。三個對比的同組數字可能不同，不得跨欄相減。

## 濕度general forecast：不加offset

[濕度理解報告](results/HUMIDITY_REPORT.html)／[方法](HUMIDITY_PLAN.md)。26站（近岸11、過渡11、內陸4），RHmin/RHmax分開；2025回溯，不假設官方目標是HKO，也不假設全港平均或極值包絡。完全從raw每日觀測及預報重算，沒有使用offset訓練係數。

- RHmin同changed事件彙總：近岸新MAE 7.965、內陸 10.526 pp；近岸U 1.073 [0.778, 1.368]、內陸U 1.500 [1.113, 1.879] pp；U差 0.427 [0.090, 0.758] pp（支持正方向）；C 0.427 [0.090, 0.758] pp（支持正方向）。
- RHmax同changed事件彙總：近岸新MAE 7.327、內陸 8.901 pp；近岸U 1.250 [0.873, 1.600]、內陸U 0.950 [0.533, 1.369] pp；U差 -0.301 [-0.585, -0.015] pp（支持負方向）；C -0.301 [-0.585, -0.015] pp（支持負方向）。

六張圖：每變數的三組同事件舊新MAE／U總覽、D1–D9 validity、D1–D8 revision usefulness。左側三組MAE折線只用89共同日，主要推論使用每對所有共同日；不可混算。來源、全部lead及站對、改善率/惡化率、RMSE/Bias見results/humidity_*.csv。

定義沿用組員U=舊絕對誤差−新絕對誤差，但使用daily_latest情境；主changed-only、all-pairs敏感度。7日區塊bootstrap2000次，固定站群、未校正多重比較。濕度取樣極值、非隨機缺測、內陸僅4站和單一年限制明列。原始站值屬觀測參考，不能證明官方產品代表全港極值；修訂有用不等於足夠準確。

本版C=|組平均G_old|−|組平均G_new|，與general氣溫一致；舊humidity報告使用平均各站對絕對gap縮小量，本版另存mean_pair_absolute_gap_reduction，不混稱同一統計量。

重現：`python build_humidity.py --dependency-dir PATH_TO_DEPS`，再執行`build_analysis.py`整合到共同README/report。

## 提交版本與重現

本次提交以本資料夾的 general forecast 結果為最新版本；不加 offset。所需輸入快照放在 inputs/，安裝及重建步驟、來源範圍見 [REPRODUCING.md](REPRODUCING.md)。inputs/ 中舊驗證文件只供來源追蹤，不是本次新增實驗結果。
