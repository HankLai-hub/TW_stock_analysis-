# 自動更新引擎

這個目錄由 GitHub Actions 執行，不需要在 iPad 安裝 Python。

- `fetch_market.py`：抓 TWSE / TPEx / TAIFEX / CBC 官方開放資料並寫入 `data/live.json`。
- `validate_live.py`：部署前檢查資料結構。
- `common.py`：共用 HTTP、日期、數值與安全寫檔函式。

## 盤中資料的授權保護

TWSE 對即時交易資訊的傳輸／重播有授權規範。這個專案**不會**以爬取 MIS 等方式，把未授權的即時交易資訊重新散布到公開 GitHub Pages。

如果日後你有合法授權的盤中資料供應商，可在 Repository Secrets 設：

- `INTRADAY_FEED_URL`
- `INTRADAY_FEED_TOKEN`（若供應商需要）

供應商回傳最簡單格式：

```json
{
  "metrics": {
    "taiex": {"value":"46321.5","change":"+0.30%","asOf":"2026-09-14 10:07","source":"你的供應商"},
    "otc": {"value":"398.1","change":"+0.20%","asOf":"2026-09-14 10:07","source":"你的供應商"},
    "tx": {"value":"46310","change":"+0.25%","asOf":"2026-09-14 10:07","source":"你的供應商"}
  }
}
```

未設定時，GitHub Actions 仍會每小時執行，並檢查官方開放資料是否有新版本；盤中即時價位顯示 `N/A` 或上一筆官方有效值，不自行杜撰。
