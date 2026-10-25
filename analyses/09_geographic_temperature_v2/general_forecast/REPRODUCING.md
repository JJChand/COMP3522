# 最新提交版本：general forecast、不加 offset

本資料夾包含本次最新的氣溫及濕度結果、圖表、理解用報告、程式與輸入快照。其他歷史 offset 實驗不屬於本次結果。報告入口是 `results/UNDERSTANDING_REPORT.html`，濕度另見 `results/HUMIDITY_REPORT.html`。

## 重建

在本資料夾以 Python 執行（建議使用獨立虛擬環境）：

```text
python -m pip install -r requirements.txt
python build_humidity.py
python build_analysis.py
```

若依賴已在其他位置，可對兩個程式傳入 `--dependency-dir PATH_TO_DEPS`。先重建濕度，氣溫程式才會把濕度章節及摘要整合到 README／報告。兩個程式會覆寫本資料夾的產出；不連接或修改資料庫。圖表為英文標籤，說明為繁體中文。

## 快照與驗證邊界

- `inputs/temperature/`：前輪已驗證的原始（`method=raw`）站對、站點及地理彙總；程式重新彙總檢查並製圖，沿用已有 bootstrap 區間。這是從分析快照重建，不是從逐次原始氣溫觀測重新跑完整上游 pipeline。
- `inputs/humidity/`：2025 逐站每日 RH 取樣極值、每日最後預報、站點名單；本次從這些數據重新計算誤差、同日配對及 bootstrap。另附舊陣列和彙總只用作一致性核對；陣列核對只取 raw 索引，不使用 offset 修正預報。
- `inputs/manifest.json`：每個原檔與打包檔案的 SHA-256，以及是否篩選 raw。舊來源 metadata／plan／verification 是歷史來源紀錄，可能保留當時的本機路徑，並不代表所有上游檔案都隨本次提交。
- 組員 usefulness 定義來源仍為 repository 的 `analyses/04_rq3_revision_usefulness/run_analysis.py`。
- `results/verification.json` 與 `results/humidity_verification.json` 記錄本次算術、站對彙總及報告連結檢查；不能據此宣稱來源觀測完全無誤、因果關係成立或官方預報空間定義已確認。

氣溫與濕度分別使用 30／26 站、14／7 日區塊及不同有效日期，不能直接跨變數排名。所有 2025 結果屬回溯探索。打包輸入後重新執行，主要點估計及區間維持原結論；CSV 重新序列化可產生約 1e-15 級浮點差異。
