## 濕度general forecast：不加offset

[濕度理解報告](results/HUMIDITY_REPORT.html)／[方法](HUMIDITY_PLAN.md)。26站（近岸11、過渡11、內陸4），RHmin/RHmax分開；2025回溯，不假設官方目標是HKO，也不假設全港平均或極值包絡。完全從raw每日觀測及預報重算，沒有使用offset訓練係數。

- RHmin同changed事件彙總：近岸新MAE 7.965、內陸 10.526 pp；近岸U 1.073 [0.778, 1.368]、內陸U 1.500 [1.113, 1.879] pp；U差 0.427 [0.090, 0.758] pp（支持正方向）；C 0.427 [0.090, 0.758] pp（支持正方向）。
- RHmax同changed事件彙總：近岸新MAE 7.327、內陸 8.901 pp；近岸U 1.250 [0.873, 1.600]、內陸U 0.950 [0.533, 1.369] pp；U差 -0.301 [-0.585, -0.015] pp（支持負方向）；C -0.301 [-0.585, -0.015] pp（支持負方向）。

六張圖：每變數的三組同事件舊新MAE／U總覽、D1–D9 validity、D1–D8 revision usefulness。左側三組MAE折線只用89共同日，主要推論使用每對所有共同日；不可混算。來源、全部lead及站對、改善率/惡化率、RMSE/Bias見results/humidity_*.csv。

定義沿用組員U=舊絕對誤差−新絕對誤差，但使用daily_latest情境；主changed-only、all-pairs敏感度。7日區塊bootstrap2000次，固定站群、未校正多重比較。濕度取樣極值、非隨機缺測、內陸僅4站和單一年限制明列。原始站值屬觀測參考，不能證明官方產品代表全港極值；修訂有用不等於足夠準確。

本版C=|組平均G_old|−|組平均G_new|，與general氣溫一致；舊humidity報告使用平均各站對絕對gap縮小量，本版另存mean_pair_absolute_gap_reduction，不混稱同一統計量。

重現：`python build_humidity.py --dependency-dir PATH_TO_DEPS`，再執行`build_analysis.py`整合到共同README/report。
