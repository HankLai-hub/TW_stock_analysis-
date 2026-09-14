# TW Market Radar 2.0

台股大盤「消息面 × 資金面 × 全球市場 × 期現貨」研究儀表板。

## 設計目標

- **10 秒**：看到市場 regime、綜合分數與 6 個核心 KPI。
- **30 秒**：讀完市場主線與 30 秒結論。
- **3 分鐘**：完成消息、法人、期貨、選擇權、槓桿、廣度、產業與情境研究。

## 功能

- 日報 / 週報 URL 狀態：`?mode=daily` / `?mode=weekly`
- 市場綜合分數與近 10 次趨勢
- 主線因果鏈
- 消息情報分類 + 搜尋
- 5 個最重要追蹤指標與改判條件
- 三大法人 5 / 10 / 20 日
- TX / Put-Call / 基差
- 匯率 / 融資 / 借券 N/A 原則
- 市場廣度與支撐壓力
- 產業相對強弱
- Bull / Base / Bear 機率與判斷失效條件
- 事件行事曆
- 資料新鮮度與官方來源
- 深淺色、分享、複製摘要、列印研究版
- GitHub Pages / Vercel / Netlify 可部署
- 零前端框架、零外部 JS 依賴

## 本機啟動

```bash
npm run check
npm run serve
```

然後開啟 `http://localhost:8080`。

## 更新資料

日常只需要維護 `data.js`。UI 會依 `daily` / `weekly` 物件自動重新渲染。

## 自動化下一步

正式營運建議把資料產生層拆成：

`TWSE / TPEx / TAIFEX / CBC / Fed / BLS → ETL → validation → daily.json / weekly.json → 前端`

網站目前故意保持靜態，原因是部署成本低、速度快、GitHub Pages 直接可用；等資料管線穩定後再切 API。
