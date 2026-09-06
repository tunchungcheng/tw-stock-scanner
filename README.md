# 台股動能蓄勢掃描器

每天收盤後由 GitHub Actions 抓取 TWSE、TPEx 官方盤後資料，計算動能蓄勢策略，並將結果發布到 GitHub Pages。

## 結果

- **蓄勢名單**：月營收 YoY 至少 30%、累計 YoY 至少 15%，搭配上市／上櫃分流、產業強度、分組動能計分、必要量能與乖離控制。
- 網頁顯示產業別，股票名稱可直接開啟個股資訊頁，並支援代號／名稱／產業搜尋、欄位排序、依入選原因優先排序、CSV 下載與歷史交易日切換。
- 網頁直接顯示次日突破觸發價、追價上限、取消價與初始停損；另以前瞻方式追蹤網站實際發布過的訊號。

## 啟用方式

1. 建立 GitHub repository，把本專案全部檔案推上去。
2. 到 **Settings → Pages → Build and deployment**，Source 選擇 **GitHub Actions**。
3. 到 **Actions → 台股每日掃描與網頁發布 → Run workflow** 手動執行第一次。
4. 完成後，網頁網址會顯示在 workflow 的 `deploy` job 與 repository 的 Pages 設定頁。

排程設定為週一至週五台灣時間 18:30（UTC 10:30）。休市日會沿用 API 可取得的最近共同交易日，不會製造不存在的當日行情。

## 本機執行

```bash
python -m pip install -r requirements.txt
python scanner.py
python -m http.server 8000 --directory docs
```

開啟 <http://localhost:8000>。

## 可調整參數

集中在 `scanner.py` 頂部：

- `BACKFILL_CALENDAR_DAYS`：每次重新抓取的歷史日數。
- `MIN_AVG_TURNOVER_20`：20 日平均成交額下限。
- `MIN_REVENUE_YOY`：最新月營收年增率下限。
- `MIN_REVENUE_YTD_YOY`：累計營收年增率下限。
- `REVENUE_AVAILABLE_DAY`：回測與回補時採用的保守營收可用日。
- `MIN_VOLUME_RATIO`：當日量比必要門檻。
- `MAX_MA20_DEVIATION_PCT`：MA20 正乖離排除上限。
- `SETUP_MIN_SCORE`：蓄勢名單最低分數。
- `NEUTRAL_SETUP_MIN_SCORE`：震盪行情最低分數。
- `SETUP_LIMIT`：網頁顯示筆數。

## 資料與限制

- 行情、產業分類與月營收來源是 TWSE／TPEx 官方盤後資料及公開資訊觀測站彙整資料，價格未還原；輸出會記錄次月 11 日的保守營收可用日，供後續歷史驗證使用。
- GitHub Actions 每次重抓近 150 個日曆日，repository 不保存大型股價資料庫，只保存小型結果檔。
- `performance.json` 只統計網站曾經實際發布的訊號，並以 0.7% 估計來回交易成本；樣本少時不應據此推論策略有效。
- 訊號在收盤後才成立，不能假設以當日收盤價成交。
- 本專案僅供研究，不構成投資建議。
