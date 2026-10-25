# 濕度general forecast情境

按用戶要求：不以TST為指定預報目標、不加offset、不把general解釋為全港空間平均或各站極值包絡。2025回溯研究，既定26站全保留；RHmin/RHmax分開，近岸≤0.5km 11站、過渡>0.5–2km 11站、內陸>2km 4站。不沿用氣溫30站名單。

由既有逐站每日觀測及每日最後預報CSV重新計算，不讀入任何offset係數。觀測是名義每十分鐘一筆的一分鐘平均RH，完整日須144個有效時槽；日min/max是取樣極值，不冒充完整一分鐘極值。缺測不補值，舊資料的latest-capture規則沿用。發布及目標日均在2025，D1–D9。

1. 全預報日validity：每跨組站對只用同日同版本。MAE主、RMSE/Bias輔；先站對內平均，再對比內站對等權。各lead分開。
2. 共26站、兩變數、九lead的89日固定交集只作三組描述性折線，明示樣本受限；主要區間來自站對可用日。
3. 修訂：相鄰發布日daily-latest D(k+1)→Dk，新lead1–8；同一站對的舊新validity及U完全同事件。主分析changed-only，all-pairs敏感度。RHmin與RHmax各自決定是否改動。
4. 沿用組員RQ3 U=|F_old−O|−|F_new−O|；改善率為U>1e-10，惡化率U<−1e-10。數值誤差以pp表達，不是相對百分比。平均U和改善率分開。
5. 組間差G=MAE_B−MAE_A；主C=|平均G_old|−|平均G_new|，與general氣溫一致。既有humidity報告的C是平均各站對(|G_old|−|G_new|)，本版另保留該統計量，但不能混稱同一C。
6. 2000次7日循環日曆區塊bootstrap、seed3522，沿用濕度既有方法，同日所有站與事件一起重抽，固定站群、不校正多重比較。all是在每站對內按事件平均，再站對等權，不是八個lead等權。

圖顏色固定近岸藍綠、過渡橙、內陸紫紅。輸出全部lead/站對/站點數據、每圖解讀、樣本與限制，加入general_forecast README和理解報告；不修改既有氣溫結論。驗證raw陣列與舊NPZ一致、重新彙總站對、核對既有D9與revision差/U，明示bootstrap未獨立重寫。
