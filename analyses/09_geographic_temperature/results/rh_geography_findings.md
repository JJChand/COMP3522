# 地理因素與相對濕度（RH）區間

Task 1(b) 探索性分析。以 24 個自動氣象站（AWS）、2025 年 89 個共同 HKT 日期（89/365）及 calendar lead 1–9，比較 HKO 同一份九天公共預報與各站實測 RH 區間的吻合程度。

## 結果

| 因素 | 比較 | 平均 Hausdorff 差距（pp） | 配對 95% CI（pp） |
|---|---|---:|---:|
| 海岸距離 | >2 km 減 ≤0.5 km | +2.48 | [+1.36, +3.62] |
| 城市化（500 m） | 低開發減高開發 | +0.56 | [−0.17, +1.32] |
| 地形（300 m） | 平坦低起伏減山坡 | +1.33 | [+0.82, +1.90] |
| 地形（500 m） | 平坦低起伏減山坡 | +1.76 | [+1.07, +2.48] |

- **海岸距離。** 近岸、過渡帶和內陸分別有 11、9、4 站，平均距離為 11.04、11.59、13.52 pp。九個 lead 的內陸減近岸差距方向一致。逐一移除任一內陸或近岸站後，差距仍為 +2.17 至 +2.93 pp。
- **城市化。** 500 m 主分析中，高、中、低開發組分別有 6、11、7 站，平均距離為 11.44、11.56、12.00 pp。三個 pairwise 95% CI 均包含 0。這批站點和日期未見開發程度與 RH Hausdorff distance 有明確 association。1 km 及 500 m 納入 GIC 的設定各有 7/24 站換組，列作 sensitivity。
- **地形。** 平坦低起伏組的平均距離在兩個尺度均高於山坡組。全部地形配對中，300 m 有 4/6 個 CI 排除 0，500 m 有 5/6 個。六站隨尺度換組，谷地候選相對平坦組的差距亦轉向。300 m 分類下，四個內陸站均屬平坦低起伏組。結果支持部分地形分組有樣本內 association。現有比較無法分離地形與海岸位置的影響。

## 方法與範圍

- **配對與 metric。** 每站以 HKT 日內每 10 分鐘發布的一分鐘平均 RH 重構 sampled min/max。24 站均有 144 個有效時刻才保留該日。同一 valid date 和 lead 使用相同 daily-latest forecast vintage。Hausdorff distance 是預報及觀測兩個端點的絕對差中較大的一個，單位為百分點（pp）。先逐站計算，再在組內等權平均。Pooled 結果對九個 leads 等權。CI 以配對 7 日 calendar block bootstrap 計算，反映固定站網的日期變異。Pairwise CI 未作多重比較校正。 [HKO RH 觀測](https://data.gov.hk/en-data/dataset/hk-hko-rss-latest-one-minute-mean-rh) · [HKO 九天預報](https://data.gov.hk/en-data/dataset/hk-hko-rss-9-day-weather-forecast) · [RH interval 方法](../../05_rq4_accuracy_by_lead/REGIONAL_RH_METHOD.md)
- **海岸距離。** 以地政總署海岸線的最近距離分為 ≤0.5 km、>0.5–2 km、>2 km。距離反映位置，海風曝露程度仍取決於風向與地形。 [地政總署地形圖](https://data.gov.hk/en-data/dataset/hk-landsd-openmap-b50k-topographic-map-of-hong-kong)
- **城市化。** 用規劃署 2022 land-use raster 計算 500 m 半徑內有效陸地的開發比例。以 ≥50%、20–<50%、<20% 分組。主定義把 GIC（政府、機構及社區用地）留在分母，整類 GIC 計入開發是另一個 sensitivity。 [規劃署 land-use metadata](https://portal.csdi.gov.hk/csdi-webpage/metadata/pland_rcd_1665742315124_26227/html)
- **地形。** 用地政總署 5 m 數碼地形模型（DTM）及 land-use mask 計算局部坡度、相對高度和起伏。分為平坦低起伏、山坡、谷地候選、山脊／丘頂候選。300 m 和 500 m 分別有 2 和 3 站未能分類。各組比較仍用同一批共同日期。 [地政總署 DTM](https://www.landsd.gov.hk/tc/spatial-data/open-data.html)
- **解讀。** 共同預報與各站 sampled interval 的距離衡量地方代表性。樣本限於 2025 年固定站網及共同完整日期。所有可重構 RH interval 的站點均低於 300 m，原定海拔比較因 coverage 不足而停止。

## 彙總結果

- [組別指標](rh_geography_group_metrics.csv) 含 pooled 和 lead 1–9 的站數、共同日期數、平均 Hausdorff distance 及 signed endpoint differences。
- [組別配對差](rh_geography_group_contrasts.csv) 含各組配對差、95% CI 及 pooled leave-one-station-out 範圍。差距方向為 `group − reference`。
