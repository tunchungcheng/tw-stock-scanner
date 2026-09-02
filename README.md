# 台股蓄勢／發動掃描器

每天收盤後由 GitHub Actions 抓取 TWSE、TPEx 官方盤後資料，計算目前唯一保留的雙名單策略，並將結果發布到 GitHub Pages。

## 結果

- **蓄勢名單**：低檔 KD、量縮、波動收斂、接近突破但尚未突破。
- **發動名單**：突破前 20 日高點、量比 1.2～2.5 倍、單日漲幅 0%～4%。
- 網頁支援名單切換、股票搜尋、欄位排序、CSV 下載與歷史交易日切換。

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
- `SETUP_MIN_SCORE`：蓄勢名單最低分數。
- `SETUP_LIMIT`、`TRIGGER_LIMIT`：網頁顯示筆數。

## 資料與限制

- 行情來源是 TWSE／TPEx 官方盤後資料，價格未還原。
- GitHub Actions 每次重抓近 150 個日曆日，repository 不保存大型股價資料庫，只保存小型結果檔。
- 訊號在收盤後才成立，不能假設以當日收盤價成交。
- 本專案僅供研究，不構成投資建議。

