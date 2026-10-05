# Geographic temperature representativeness — all eligible stations

Sena 的地理延伸分析：**Temperature × 海岸距離**，以及 **Temperature × 港島／九龍／新界／離島**。

使用全部 **30 個合資格 AWS**，沒有每組選三站、top-N 或按預報誤差挑站。研究期為 2022-01-01 至 2025-12-31，共 1,461 日；Tmax／Tmin 分開，D1–D9 全部輸出。

先看 [完整執行結果](results/findings.md) 或 [離線互動全站地圖及分數](results/report.html)。本目錄沿用 GitHub 的 `README.md + run_analysis.py + results/` 結構，屬地理延伸，**不是 Task 2 的 RQ8／RQ9 外部模型比較**。

## 研究問題

同一份公共九天天氣預報直接與各站實測比較時，吻合程度是否隨海岸距離或地區而有差異？

這裡的「地方代表性」是共同預報和當地觀測的吻合程度，不能改寫為各站自己的預報模型能力。現有公共預報不是逐站 ARWF 歷史發布資料。

## Assumptions、操作定義與限制

### 1. 全部資料與站點範圍

- 37 个已收集氣溫站的資格、資料覆蓋及排除原因，全部列在 [station_inventory.csv](results/station_inventory.csv)。主站群是其中全部 30 個完整期 AWS 候選。
- **大帽山 TMS、大老山 TC** 依研究範圍排除。這項範圍修訂是在前一輪結果後提出，不能稱為預先註冊，也不能把「誤差較大」當成刪站理由。
- HKO 作觀測驗證基準；HKO／HKA 有人站不混入 AWS 地理組。SE1 搬站、TPO／YCT 非完整期，不納入主組。
- 「完整期資格」不等於 1,461 日沒有缺值。不以最低覆蓋排名抽樣，全部合資格站都保留。
- **昂坪 NGP（593 m）仍在主分析**。排除 TMS／TC 不等於只保留低海拔。另做全部 <300 m 的 29 站敏感度，不能混稱為同一主樣本。
- 沒有將缺測日補成零，也沒有插值或以其他站數值替代。

### 2. 地理分組

| 因素 | 分組 | 全部主分析站數 |
| --- | --- | ---: |
| 海岸距離 | 近岸 ≤0.5 km | 10 |
| 海岸距離 | 過渡 >0.5–2 km | 15 |
| 海岸距離 | 內陸 >2 km | 5 |
| 行政地區 | 港島 | 5 |
| 行政地區 | 九龍 | 5 |
| 行政地區 | 新界，不含離島區 | 16 |
| 行政地區 | 離島區，獨立一組 | 4 |

- 離島組為 **CCH 長洲、NGP 昂坪、PEN 坪洲、WGL 橫瀾島**。按行政「離島區」歸類，不是把所有地理上的島嶼重新歸類；例如青衣仍隨其行政區歸新界。
- 站點座標、海岸距離及行政區繼承已盤點的官方地理資料，見 [inputs/geography_provenance.json](inputs/geography_provenance.json)。海岸是 2026-10-04 當代代理，沒有重建 2022–2025 岸線。
- 地區標籤不是地形、城市化或人口密度的替代。本目錄只研究海岸與四區，不分析建築、人口、雨量或修訂 reliability。

### 3. 預報和觀測配對

- 同一個目標日／發布日取最後存檔預報（daily latest），不平均同日不同版本。
- `lead = HKT 目標日期 − HKT 發布日期`。D1–D9 分開；原始資料雖有 D0，此分析不納入。
- 每個站使用相同公共預報，對應該站同日 Tmax 或 Tmin。只接受 `data_completeness = C` 且數值存在的觀測。
- 存檔發布時間依來源欄位，沒有另外證明原始抓取時間等於當時正式可用時間。
- Tmax／Tmin 是日極值，不是日平均溫度。

### 4. 兩種資料支持範圍，不能混讀

**`all_available`：全部有效配對的描述性主表。**

每站使用其全部有效日期；D1–D9、Tmax／Tmin 共 **670,865 筆**。同一個站日對應不同 lead，是不同預報個案，不能當成獨立觀測日。站點和 lead 的有效日期不同，組別差距仍可能受日期構成影響。

**`strict_common`：全站共同日期的嚴格對照。**

要求 30 站、Tmax／Tmin、D1–D9 同時有資料，只餘 **24 日（1.64%）**：2022 年 4 日、2023 年 3 日、2024 年 4 日、2025 年 13 日。這個樣本不足以充分代表四年的天氣。

**`lowland_available`：全部 29 個低海拔站的敏感度。**

保留所有 <300 m 合資格站，各用全部有效配對。它改變研究範圍，也不能消除各站日期差異。

因此，本次不以選三站的方法換取更多共同日，也不把不同日期的全資料結果說成完全公平的地理能力排名。

### 5. 指標與權重

`error = forecast − observation`。

- 逐站：MAE = mean(abs(error))；RMSE = sqrt(mean(error²))；Bias = mean(error)。
- 組別：每站同等權重。MAE = mean(站 MAE)；RMSE = sqrt(mean(站 MSE))；Bias = mean(站 Bias)。**組別 RMSE 不是站 RMSE 的算術平均。**
- 另列 `pooled_station_day_mae`，讓人核對每筆站日等權的另一個估計量；它會給資料較多的站較大權重，不能和主指標混用。
- 不先平均各站觀測後再算誤差，以免站間正負差抵銷。
- Bias 正值為偏高、負值為偏低；不能把數值較負解作較準。

### 6. 不確定性與「證據不足」

- 2,000 次、14 日循環日曆區塊 bootstrap，seed=3522。同一天所有站一起重抽，保留空間配對。
- 每次重抽仍按每站有效資料計分，再站點等權合成。沒有將同日各站當成獨立日期，也沒有站點母群抽樣。
- 區間只反映固定站點、地理分類及缺值模式下的時間抽樣不確定性。不能修復 `all_available` 日期支持不同，亦不能令 24 日代表四年；未作多重比較校正。
- 有些描述性方向一致，不代表已有足夠證據支持穩定地理排名。**證據不足不等於證明沒有差異。**
- 不做因果主張；海拔、海岸、站址、區域及缺值可能混雜。全年結果沒有按季節建模；逐年站點結果另列出。

### 7. HKO baseline 與地域差異

- 本次計算全部主站的同日 `O_station − O_HKO` 分布，屬 2022–2025 可用觀測差异，不稱為長期氣候常值。
- 在 `F`、`O_HKO`、`O_station` 三者都有效的同日核對：`F − O_station = (F − O_HKO) + (O_HKO − O_station)`。
- 這是 signed error／Bias 的等式；不能把 MAE 相加或相減。
- 沒有用全期地域偏差去修正預報再在同一期評分；未做獨立測試期的地方化預報驗證。HKO 只是本研究的基準，不能憑此宣稱每個歷史產品的官方空間定義已獲全面證實。

## Run from repository root

使用既有本機 CSV 副本，**沒有資料庫連線或資料庫寫入**。`--data-dir` 需包含 `forecasts.csv`、`observations.csv`、`series.csv`、`stations.csv`。來源檔案的 SHA256 保存在 [run_metadata.json](results/run_metadata.json)。

```powershell
.\.venv\Scripts\python.exe -m pip install -r analyses/09_geographic_temperature/requirements.txt
.\.venv\Scripts\python.exe analyses/09_geographic_temperature/run_analysis.py --data-dir "PATH_TO_EXISTING_ALL_DATA" --export-pairs "PATH_OUTSIDE_REPO/temperature_matched_pairs.csv.gz"
.\.venv\Scripts\python.exe analyses/09_geographic_temperature/build_report.py
.\.venv\Scripts\python.exe -m unittest discover -s analyses/09_geographic_temperature -p test_methods.py -v
.\.venv\Scripts\python.exe analyses/09_geographic_temperature/verify_results.py --data-dir "PATH_TO_EXISTING_ALL_DATA" --pairs "PATH_OUTSIDE_REPO/temperature_matched_pairs.csv.gz"
```

`--export-pairs` 可略過，但逐筆匯出核對需要這個檔案。本次逐筆壓縮檔放在工作區 `analysis/temperature-all-stations-evidence/temperature_matched_pairs.csv.gz`，**不在此 Git 倉庫內**；Git 目錄只放站點 metadata、研究彙總、程式與圖。

在此次 Windows 工作區，程式以 `--dependency-dir analysis/geographic-representativeness/.deps` 使用既有套件。其他電腦的正常 virtualenv 不需要此選項。

## Outputs

- [findings.md](results/findings.md)：完整研究結果，包含所有 30 站 D3 表，不是抽選示例。
- [report.html](results/report.html)：離線互動地圖，切換全部資料／共同日期／低海拔、四區／海岸、Tmax／Tmin、D1–D9。
- [station_inventory.csv](results/station_inventory.csv)：37 站資格及缺值，30 站明確標記納入。
- [station_panels.csv](results/station_panels.csv)：每組全部站碼。
- [station_metrics.csv](results/station_metrics.csv)：所有納入站、D1–D9、Tmax／Tmin、三種設計。
- [group_metrics.csv](results/group_metrics.csv)、[group_contrasts.csv](results/group_contrasts.csv)：完整組別指標及差值。
- [pairing_coverage.csv](results/pairing_coverage.csv)：逐站／lead／變數的有效、缺實測、缺預報及兩者缺失數目。
- [station_year_metrics.csv](results/station_year_metrics.csv)：逐年站點結果；零有效日不補造分數。
- [strict_common_dates.csv](results/strict_common_dates.csv)、[strict_common_year_coverage.csv](results/strict_common_year_coverage.csv)：24 個共同日期及年度分布。
- [station_HKO_observed_offsets.csv](results/station_HKO_observed_offsets.csv)：站點與 HKO 同日實測差異。
- [HKO_error_decomposition.csv](results/HKO_error_decomposition.csv)、[HKO_reference_metrics.csv](results/HKO_reference_metrics.csv)：HKO 基準及誤差分解。
- PNG／SVG 圖：全站 D1–D9 曲線、全部 30 站 D3 圖。
- [verification.json](results/verification.json)：核對範圍與結果；不是官方來源完整性或歷史地理精度的保證。
- [viewer_verification.json](results/viewer_verification.json)：離線互動頁驗證；不是瀏覽器整頁視覺驗證。

## Executed verification

- 670,865 筆配對逐筆與原始 C 觀測、獨立選出的 daily-latest 預報核對，涵蓋發布時間及來源 ID。
- 2,545 項數值檢查，包含全部站點／組別指標、站點等權、缺值流程、離島獨立、HKO 誤差分解及 18 組 Chandler 基準重現。
- 5 個方法測試：不同覆蓋的站點權重、RMSE 合成、缺值非零、Bias 可加但 MAE 不可加、零覆蓋站拒絕。
- 505 項 JSDOM 離線互動檢查，涵蓋全部 3 種資料模式 × 2 因素 × 2 變數 × 9 leads、37 個地圖點、全部 30／29 個結果列及離島四站點選。PNG 圖另經視覺檢查，沒有宣稱完成瀏覽器整頁視覺驗證。
- Bootstrap 區間沒有獨立重寫算法驗證；檢查不能證明來源存檔完整，亦不能消除樣本與地理代理限制。

若要重跑互動檢查，在任意本機測試工具目錄安裝 `jsdom`，再執行：

```powershell
node analyses/09_geographic_temperature/verify_viewer.cjs --jsdom "PATH_TO_JSDOM_PACKAGE"
```

`package_results.py --output PATH_OUTSIDE_REPO/09_geographic_temperature.zip` 可打包本目錄，會排除 Python 快取；不含倉庫外的完整逐筆資料或 runtime dependencies。

## Source references

- [HKO weather station information](https://www.hko.gov.hk/en/cis/stn.htm)
- [HKO nine-day public forecast](https://www.hko.gov.hk/tc/wxinfo/currwx/fnd.htm)
- [ARWF product description](https://maps.weather.gov.hk/ocf/help_uc.html)：確認有逐站預報；未找到本研究可用的完整 2022–2025 歷史發布版本，不等於官方未保存。
- [Geographic provenance](inputs/geography_provenance.json)：本機站點與海岸／行政區代理的來源記錄。
