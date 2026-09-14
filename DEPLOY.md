# 部署 TW Market Radar

## A. GitHub Pages（推薦）

1. GitHub 建立 repository，例如 `tw-market-radar`。
2. 把本資料夾內容放在 repository 根目錄。
3. Push 到 `main`。
4. GitHub → Settings → Pages → Source 選 **GitHub Actions**。
5. `.github/workflows/pages.yml` 會先執行資料與 JS 驗證，再部署。

公開網址格式：

`https://<你的帳號>.github.io/tw-market-radar/`

若 repository 叫 `<你的帳號>.github.io`，網址就是：

`https://<你的帳號>.github.io/`

## B. Vercel

1. Vercel → Add New → Project。
2. Import GitHub repository。
3. Framework Preset 選 Other。
4. Build command 留空；Output Directory 使用 `.`。
5. Deploy。

## C. Netlify

把 repository 連到 Netlify，`netlify.toml` 已指定 publish 目錄為根目錄。

## 自訂網域

部署後可在 GitHub Pages / Vercel / Netlify 設定自有網域，例如：

- `market.yourdomain.com`
- `twradar.com`

## 發布前檢查

```bash
npm run check
```

必須通過：

- `app.js` 語法
- `data.js` 語法
- daily / weekly 核心 schema
- 綜合分數範圍
- 5 大指標完整性
