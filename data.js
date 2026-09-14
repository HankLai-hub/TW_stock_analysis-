window.MARKET_DASHBOARD_DATA = {
  product: {
    name: "TW Market Radar",
    tagline: "台股風險 × 資金 × 期現貨研究儀表板",
    disclaimer: "本網站用於市場研究與資訊整理，不構成任何投資建議。"
  },
  sources: [
    { key: "TWSE", name: "臺灣證券交易所", tier: "官方", url: "https://www.twse.com.tw/" },
    { key: "TPEx", name: "證券櫃檯買賣中心", tier: "官方", url: "https://www.tpex.org.tw/" },
    { key: "TAIFEX", name: "臺灣期貨交易所", tier: "官方", url: "https://www.taifex.com.tw/" },
    { key: "CBC", name: "中央銀行", tier: "官方", url: "https://www.cbc.gov.tw/" },
    { key: "FED", name: "Federal Reserve", tier: "官方", url: "https://www.federalreserve.gov/" },
    { key: "BLS", name: "U.S. Bureau of Labor Statistics", tier: "官方", url: "https://www.bls.gov/" },
    { key: "BEA", name: "U.S. Bureau of Economic Analysis", tier: "官方", url: "https://www.bea.gov/" },
    { key: "CENSUS", name: "U.S. Census Bureau", tier: "官方", url: "https://www.census.gov/" },
    { key: "BOJ", name: "Bank of Japan", tier: "官方", url: "https://www.boj.or.jp/en/" },
    { key: "CME", name: "CME Group", tier: "交易所", url: "https://www.cmegroup.com/" },
    { key: "TSMC", name: "TSMC Investor Relations", tier: "公司官方", url: "https://investor.tsmc.com/" },
    { key: "REUTERS", name: "Reuters Markets", tier: "背景資訊", url: "https://www.reuters.com/markets/" }
  ],
  daily: {
    meta: {
      reportType: "每日盤前分析",
      title: "2026/09/14 台股盤前作戰儀表板",
      updatedAt: "2026/09/14 08:30",
      timezone: "Asia/Taipei",
      twDate: "2026/09/11",
      usDate: "2026/09/11",
      dataStatus: "盤前版｜價格與籌碼採最新完整交易日"
    },
    score: 36,
    scoreLabel: "偏空",
    confidence: "中高",
    regime: "Risk-Off",
    headline: "全球環境尚未支持全面 Risk-On；外資正在降低台灣短線曝險，但半導體基本面仍提供中期支撐。",
    quickTake: [
      "週末能源供應風險重新推升油價，市場再度交易「能源通膨 → 美債殖利率 → 科技估值」這條主線。",
      "外資 9/11 現貨賣超 892.70 億元，外資 TX 淨空擴大至 85,067 口；最新邊際資金行為偏空。",
      "選擇權 Put/Call 尚未出現恐慌式堆積，週五融資開始去化，因此目前仍較像高檔去風險，而非失控式崩盤。",
      "45,940–46,000 是第一道防線；若油價、美債、台幣與外資再度同向惡化，短線風險評級需下調。"
    ],
    kpis: [
      { label: "全球環境", value: "Risk-Off", tone: "bad", note: "油價與殖利率壓抑風險偏好" },
      { label: "短線環境", value: "偏空", tone: "bad", note: "高波動，等待支撐驗證" },
      { label: "外資方向", value: "降低曝險", tone: "bad", note: "現貨賣＋TX高淨空" },
      { label: "期貨方向", value: "偏空", tone: "bad", note: "TX 淨空 -85,067 口" },
      { label: "槓桿", value: "開始去化", tone: "warn", note: "單日融資約 -57 億" },
      { label: "市場風險", value: "高", tone: "bad", note: "能源、利率、廣度三重壓力" }
    ],
    marketThemes: [
      {
        rank: 1, tone: "bad", weight: "最高權重", title: "能源風險重新接管全球定價",
        chain: ["中東供給風險", "Brent ↑", "通膨預期 ↑", "10Y / Fed 緊縮", "AI 估值承壓"],
        thesis: "這是盤前最重要的跨資產主線。只要 Brent 與 10Y 同步維持高檔，台股高估值電子的折現率壓力就不容易快速消失。",
        watch: "Brent 100 / 110 美元；美國 10Y 5%。"
      },
      {
        rank: 2, tone: "bad", weight: "高權重", title: "外資由避險轉向實質降風險",
        chain: ["現貨大賣", "TX 淨空擴大", "台幣轉弱", "市場廣度惡化"],
        thesis: "最新兩個交易日的現貨與期貨方向更一致，已不能完全以『現貨布局＋期貨避險』解釋。",
        watch: "外資現貨 5 日滾動值、TX 是否往 -90,000 口、USD/TWD 31.8。"
      },
      {
        rank: 3, tone: "warn", weight: "中高權重", title: "基本面強，但價格主導權暫時在估值",
        chain: ["AI 需求仍強", "企業獲利支撐", "全球利率高", "本益比壓縮", "族群分化"],
        thesis: "台積電與 AI 鏈的基本面並未出現衰退證據，因此中期不能把短線去風險直接等同基本面熊市。",
        watch: "TSMC 營收／財測、SOX 相對強弱、10Y 是否回落。"
      }
    ],
    global: [
      { name: "S&P 500", value: "7,656.98", change: "+0.86%", tone: "good", note: "週五反彈；週線仍弱" },
      { name: "Nasdaq", value: "26,333.04", change: "+0.96%", tone: "good", note: "科技股反彈待利率驗證" },
      { name: "SOX", value: "11,847.15", change: "+2.01%", tone: "good", note: "半導體相對抗跌" },
      { name: "US 10Y", value: "≈ 4.98%", change: "接近 5%", tone: "bad", note: "估值關鍵關卡" },
      { name: "Brent", value: "107–108", change: "盤前約 +3%", tone: "bad", note: "能源通膨再升溫" },
      { name: "USD/TWD", value: "31.638", change: "短線轉弱", tone: "warn", note: "9/11 CBC 收盤" }
    ],
    focus: [
      { rank: 1, name: "Brent 原油", value: "107–108", tone: "bad", why: "油價正在影響通膨、Fed 與美債三個核心變數。", trigger: "站穩 110 → 風險升級；回落 100 下 → 明顯降壓。" },
      { rank: 2, name: "美國 10Y", value: "≈ 4.98%", tone: "bad", why: "目前是科技股合理估值最重要的折現率變數。", trigger: "有效突破 5% → 高估值電子再承壓。" },
      { rank: 3, name: "外資 TX 淨部位", value: "-85,067 口", tone: "bad", why: "與現貨賣超形成偏空共振。", trigger: "往 -90,000 → 風險上升；回到 -80,000 內 → 壓力下降。" },
      { rank: 4, name: "外資現貨", value: "9/11 -892.70 億", tone: "bad", why: "最近兩日約 -1,276 億，邊際轉弱速度快。", trigger: "重新連 3 日買超才視為有效改善。" },
      { rank: 5, name: "USD/TWD", value: "31.638", tone: "warn", why: "可驗證外資賣超是否伴隨真正資金撤出。", trigger: "快速往 31.8 且外資續賣 → 提高警戒。" }
    ],
    news: [
      { category: "地緣政治", impact: 5, tone: "bad", time: "週末更新", title: "能源供應風險升級，油價重新成為風險資產定價中心", fact: "關鍵輸油與航運安全風險升高，能源供應不確定性重新放大。", reaction: "Brent 盤前重新上行，全球股指期貨風險偏好轉弱。", twImpact: "透過通膨與殖利率壓縮科技估值；也會放大航運與原物料族群波動。", sourceKeys: ["REUTERS"] },
      { category: "貨幣政策", impact: 5, tone: "warn", time: "09/15–09/16", title: "FOMC 進入決策週，市場等待利率與 SEP / Dot Plot", fact: "Fed 官方行事曆顯示 FOMC 於 9/15–9/16 舉行。", reaction: "市場提前以高殖利率與較鷹派政策路徑定價。", twImpact: "決定全球折現率與美元方向，是台股本週第一順位總體事件。", sourceKeys: ["FED", "CME"] },
      { category: "總體數據", impact: 5, tone: "bad", time: "09/11", title: "美國 8 月 CPI 維持黏性，能源項重新升溫", fact: "CPI 月增 0.4%、年增 3.4%；核心月增 0.3%、年增 2.4%。", reaction: "美債殖利率維持高檔，利率敏感資產波動放大。", twImpact: "對台股不是需求衰退問題，而是估值折現率問題。", sourceKeys: ["BLS"] },
      { category: "台股資金", impact: 5, tone: "bad", time: "09/11", title: "外資現貨與台指期同步偏空", fact: "外資現貨賣超 892.70 億元；TX 多單 8,242、空單 93,309，淨空 85,067 口。", reaction: "加權下跌、市場廣度惡化，櫃買弱於大型權值。", twImpact: "45,940–46,000 成為短線風險控制位。", sourceKeys: ["TWSE", "TAIFEX"] },
      { category: "半導體", impact: 4, tone: "good", time: "08 月營收", title: "半導體基本面仍提供中期下檔支撐", fact: "台積電 8 月營收 5,148.06 億元、年增 53.3%。", reaction: "SOX 週五反彈約 2%，但利率環境限制估值擴張。", twImpact: "短線偏空不等於基本面熊市；若殖利率回落，AI 鏈可能率先修復。", sourceKeys: ["TSMC"] }
    ],
    flow: {
      headers: ["法人", "當日", "近 5 日", "近 10 日", "近 20 日", "解讀"],
      rows: [
        ["外資", "-892.70 億", "-51.04 億", "-760.76 億", "+585.76 億", "短線快速去風險；中期尚未全面撤出"],
        ["投信", "+82.14 億", "+170.80 億", "+233.84 億", "+49.64 億", "持續承接，但力道不足抵銷外資"],
        ["自營商", "-302.02 億", "-487.00 億", "-705.21 億", "-740.60 億", "自行與避險合計偏空"]
      ]
    },
    derivatives: [
      { label: "外資 TX 多單 OI", value: "8,242", tone: "neutral", note: "9/11" },
      { label: "外資 TX 空單 OI", value: "93,309", tone: "bad", note: "9/11" },
      { label: "外資 TX 淨部位", value: "-85,067", tone: "bad", note: "單日淨空約再增 1,149 口" },
      { label: "成交量 P/C", value: "91.56%", tone: "warn", note: "尚未恐慌" },
      { label: "OI P/C", value: "87.70%", tone: "warn", note: "需考慮到期與結算" },
      { label: "基差", value: "近乎平價", tone: "neutral", note: "結算週，低權重" }
    ],
    leverage: [
      { label: "USD/TWD", value: "31.638", tone: "warn", note: "9/11 CBC 收盤，週後段轉弱" },
      { label: "上市＋上櫃融資", value: "約 7,874 億", tone: "warn", note: "9/11 單日約 -57 億" },
      { label: "上市融資週變化", value: "+59.76 億", tone: "bad", note: "週中槓桿增加，週五才開始去化" },
      { label: "借券", value: "N/A", tone: "neutral", note: "缺少完整同口徑官方序列，不硬填" }
    ],
    breadth: {
      advancers: 229, decliners: 779, unchanged: 68,
      taiex: "46,184.85", taiexChange: "-1.61%", otc: "395.52", otcChange: "-2.40%",
      note: "下跌家數約為上漲家數 3.4 倍；不是單一權值股造成的表面弱勢。"
    },
    sectors: [
      { name: "金融", score: 82, tone: "good", direction: "流入", desc: "防禦型資金集中；9/11 相對強。" },
      { name: "航運", score: 69, tone: "good", direction: "流入", desc: "相對強，但油價與航道風險提高波動。" },
      { name: "資訊服務", score: 63, tone: "good", direction: "偏強", desc: "相對大盤抗跌。" },
      { name: "半導體", score: 42, tone: "warn", direction: "分化", desc: "基本面強、估值面承壓。" },
      { name: "電子零組件", score: 25, tone: "bad", direction: "流出", desc: "高 Beta 去風險明顯。" },
      { name: "上櫃電子", score: 20, tone: "bad", direction: "流出", desc: "中小型股弱於大型權值。" }
    ],
    levels: {
      current: 46184.85,
      support: [{ price: "45,940–46,000", label: "第一支撐", strength: "高" }, { price: "45,850", label: "第二支撐", strength: "中高" }, { price: "45,000", label: "心理關卡", strength: "中" }],
      resistance: [{ price: "46,550–46,650", label: "第一壓力", strength: "中" }, { price: "46,940–47,000", label: "第二壓力", strength: "高" }, { price: "47,300–47,600", label: "波段反轉區", strength: "高" }]
    },
    scenarios: [
      { type: "Bull", probability: 20, tone: "good", title: "風險快速降溫", conditions: ["Brent 回落 100 以下", "10Y 回到 4.8% 以下", "外資現貨重新連買", "TX 淨空回補且非換月", "TAIEX 站回 47,000"], result: "AI / 半導體重新取得主導權。" },
      { type: "Base", probability: 55, tone: "warn", title: "高檔震盪＋防禦輪動", conditions: ["45,940 附近守住", "油價高檔但不再加速", "法人維持保守", "金融與防禦相對強"], result: "46,000 附近反覆測試，指數震盪但個股分化。" },
      { type: "Bear", probability: 25, tone: "bad", title: "估值修正升級", conditions: ["Brent 站穩 110", "10Y 突破 5%", "USD/TWD 往 31.8", "TX 淨空往 -90,000", "45,850 失守"], result: "高 Beta 電子與融資集中股進入波段修正。" }
    ],
    events: [
      { date: "09/16", time: "20:30", name: "美國 8 月零售銷售", importance: 4, watch: "消費是否仍過熱", sourceKeys: ["CENSUS"] },
      { date: "09/16", time: "日盤", name: "台指期 9 月結算週", importance: 4, watch: "近月／次月換倉與基差", sourceKeys: ["TAIFEX"] },
      { date: "09/17", time: "02:00", name: "FOMC 利率決策", importance: 5, watch: "利率、Dot Plot、SEP", sourceKeys: ["FED"] },
      { date: "09/17", time: "待公告", name: "台灣央行理監事會", importance: 4, watch: "利率、匯率與房市政策", sourceKeys: ["CBC"] },
      { date: "09/17–09/18", time: "—", name: "BOJ 會議", importance: 4, watch: "日本利率與日圓", sourceKeys: ["BOJ"] }
    ],
    freshness: [
      { name: "台股價格", date: "2026/09/11", state: "latest" },
      { name: "三大法人", date: "2026/09/11", state: "latest" },
      { name: "期貨／選擇權", date: "2026/09/11", state: "latest" },
      { name: "融資融券", date: "2026/09/11", state: "latest" },
      { name: "USD/TWD", date: "2026/09/11", state: "latest" },
      { name: "美股", date: "2026/09/11", state: "latest" },
      { name: "盤前油價／事件", date: "2026/09/14", state: "intraday" },
      { name: "借券完整序列", date: "N/A", state: "missing" }
    ],
    scoreTrend: [42, 45, 41, 46, 44, 40, 38, 43, 41, 36],
    invalidation: [
      "Brent 明顯跌回 100 美元以下且 10Y 回到 4.8% 以下。",
      "外資現貨重新連續 3 個交易日買超，TX 淨空同步回到 8 萬口內。",
      "USD/TWD 回落、TAIEX 站回 47,000 且市場上漲家數占比顯著改善。"
    ]
  },
  weekly: {
    meta: {
      reportType: "每週市場週報",
      title: "2026/09/13 台股每週市場儀表板",
      updatedAt: "2026/09/13 20:02",
      timezone: "Asia/Taipei",
      twDate: "2026/09/11",
      usDate: "2026/09/11",
      dataStatus: "週報版｜回顧最近完整一週"
    },
    score: 37,
    scoreLabel: "偏空",
    confidence: "中高",
    regime: "Risk-Off",
    headline: "外資短線曝險快速下降，但 20 日累積仍正；本週是『中期基本面強、短線資金風險升高』的典型分歧。",
    quickTake: [
      "全球市場全週仍偏 Risk-Off：大型指數週線走弱、小型股更弱，美債 10Y 接近 5%，Brent 全週大漲。",
      "外資 20 日仍買超約 586 億，但 10 日已轉賣超約 761 億，最新兩日更賣超約 1,276 億，資金邊際明確轉弱。",
      "外資 TX 淨空 -85,067 口，市場廣度與櫃買同步惡化；投信雖承接，尚不足抵銷去風險。",
      "台積電營收與 AI 需求仍強，因此波段仍以估值修正而非基本面衰退解讀。"
    ],
    kpis: [
      { label: "全球環境", value: "Risk-Off", tone: "bad", note: "週線風險收縮" },
      { label: "週線環境", value: "偏空", tone: "bad", note: "TAIEX 週 -0.79%" },
      { label: "外資方向", value: "短線減碼", tone: "bad", note: "10 日與最新兩日明顯轉負" },
      { label: "期貨方向", value: "偏空", tone: "bad", note: "TX 淨空 85,067 口" },
      { label: "基本面", value: "仍強", tone: "good", note: "AI / 半導體未見衰退" },
      { label: "市場風險", value: "高", tone: "bad", note: "油價＋殖利率＋廣度" }
    ],
    marketThemes: [
      { rank: 1, tone: "bad", weight: "最高權重", title: "能源通膨 × 利率重新定價", chain: ["Brent 週漲", "通膨黏性", "10Y 接近 5%", "科技估值折價"], thesis: "本週跨資產最一致的空方訊號。", watch: "Brent 110、美國 10Y 5%。" },
      { rank: 2, tone: "bad", weight: "高權重", title: "外資時間尺度由中期淨流入轉成短線去風險", chain: ["20 日仍正", "10 日轉負", "最新兩日急賣", "TX 高淨空"], thesis: "短線降風險已明確，但還未確認中期全面撤離。", watch: "5 / 10 / 20 日滾動值是否同步轉負。" },
      { rank: 3, tone: "warn", weight: "中高權重", title: "市場內部結構比指數更弱", chain: ["櫃買弱於加權", "下跌家數擴大", "高 Beta 電子走弱", "金融防禦領先"], thesis: "市場廣度惡化使指數表現高估整體強度。", watch: "上漲家數、櫃買相對強弱、防禦股領先幅度。" }
    ],
    global: [
      { name: "S&P 500", value: "週 -0.8%", change: "Risk-Off", tone: "bad", note: "週五反彈未扭轉週線" },
      { name: "Nasdaq", value: "週 -0.7%", change: "偏弱", tone: "bad", note: "利率敏感" },
      { name: "SOX", value: "週 ≈ +0.9%", change: "相對強", tone: "good", note: "半導體仍有基本面支撐" },
      { name: "US 10Y", value: "≈ 4.98%", change: "高檔", tone: "bad", note: "估值壓力核心" },
      { name: "Brent", value: "104.61", change: "週漲 >8%", tone: "bad", note: "能源風險升高" },
      { name: "USD/TWD", value: "31.638", change: "週後段轉弱", tone: "warn", note: "外資賣超的驗證變數" }
    ],
    focus: [
      { rank: 1, name: "Brent 原油", value: "104.61+", tone: "bad", why: "能源風險主導通膨與利率。", trigger: "110 以上 → 壓力升級。" },
      { rank: 2, name: "美國 10Y", value: "≈ 4.98%", tone: "bad", why: "科技估值最重要的折現率。", trigger: "突破 5% → 估值再下修。" },
      { rank: 3, name: "外資 5/10/20 日", value: "-51 / -761 / +586 億", tone: "warn", why: "時間尺度分歧最值得追蹤。", trigger: "20 日也轉負 → 中期資金結構惡化。" },
      { rank: 4, name: "外資 TX", value: "-85,067 口", tone: "bad", why: "期貨風險曝險仍高。", trigger: "-90,000 → 風險升級；-80,000 內 → 改善。" },
      { rank: 5, name: "市場廣度", value: "229 漲 / 779 跌", tone: "bad", why: "內部結構比指數更弱。", trigger: "上漲家數占比回到 50% 以上才是健康修復。" }
    ],
    news: [
      { category: "地緣政治", impact: 5, tone: "bad", time: "週末", title: "能源供應風險延伸到新一週", fact: "中東供應與航運不確定性升高。", reaction: "Brent 週線大漲，週末風險尚未完整反映在週五收盤。", twImpact: "提高通膨、利率與科技估值的三重壓力。", sourceKeys: ["REUTERS"] },
      { category: "總體數據", impact: 5, tone: "bad", time: "09/11", title: "CPI 黏性使高利率環境延長", fact: "8 月 CPI 月增 0.4%、年增 3.4%。", reaction: "10Y 接近 5%，利率敏感資產承壓。", twImpact: "高估值電子承受折現率壓力。", sourceKeys: ["BLS"] },
      { category: "台股資金", impact: 5, tone: "bad", time: "09/10–09/11", title: "外資短線降曝險速度顯著加快", fact: "最新兩日現貨約 -1,276 億，TX 淨空 85,067 口。", reaction: "櫃買與廣度同步惡化。", twImpact: "短線偏空共振，但 20 日累積仍正。", sourceKeys: ["TWSE", "TAIFEX"] },
      { category: "半導體", impact: 4, tone: "good", time: "08 月", title: "台積電營收維持高成長", fact: "8 月營收 5,148.06 億元、年增 53.3%。", reaction: "SOX 週線相對抗跌。", twImpact: "中期下檔仍有基本面支撐。", sourceKeys: ["TSMC"] }
    ],
    flow: {
      headers: ["法人", "近 5 日", "近 10 日", "近 20 日", "週報解讀"],
      rows: [
        ["外資", "-51.04 億", "-760.76 億", "+585.76 億", "短線快速轉弱；中期尚未全面撤出"],
        ["投信", "+170.80 億", "+233.84 億", "+49.64 億", "主要承接力量"],
        ["自營商", "-487.00 億", "-705.21 億", "-740.60 億", "整體偏空"]
      ]
    },
    derivatives: [
      { label: "外資 TX 淨部位", value: "-85,067", tone: "bad", note: "較 9/3 擴大約 3,492 口淨空" },
      { label: "成交量 P/C", value: "91.56%", tone: "warn", note: "週後段回落" },
      { label: "OI P/C", value: "87.70%", tone: "warn", note: "尚無極端恐慌" },
      { label: "換月風險", value: "高", tone: "warn", note: "本週進入月結算／換倉" }
    ],
    leverage: [
      { label: "USD/TWD", value: "31.638", tone: "warn", note: "週線近乎持平、週後段轉弱" },
      { label: "上市融資", value: "5,878.71 億", tone: "warn", note: "週五 -40.27 億" },
      { label: "較 9/4 融資", value: "+59.76 億", tone: "bad", note: "槓桿尚未完全清洗" },
      { label: "借券", value: "N/A", tone: "neutral", note: "缺完整同口徑序列" }
    ],
    breadth: { advancers: 229, decliners: 779, unchanged: 68, taiex: "46,184.85", taiexChange: "週 -0.79%", otc: "395.52", otcChange: "9/11 -2.40%", note: "櫃買與中小型股明顯弱於大型權值。" },
    sectors: [
      { name: "金融", score: 82, tone: "good", direction: "流入", desc: "防禦性資金明顯集中。" },
      { name: "航運", score: 69, tone: "good", direction: "流入", desc: "相對強，但能源風險升高。" },
      { name: "電信 / 防禦", score: 66, tone: "good", direction: "偏強", desc: "風險下降環境相對受惠。" },
      { name: "高 Beta AI / 電子", score: 34, tone: "bad", direction: "流出", desc: "估值壓縮與外資去風險。" },
      { name: "上櫃中小型", score: 22, tone: "bad", direction: "流出", desc: "櫃買弱於加權。" },
      { name: "面板 / 部分記憶體", score: 30, tone: "bad", direction: "流出", desc: "題材型資金波動加大。" }
    ],
    levels: { current: 46184.85, support: [{ price: "45,940–46,000", label: "第一支撐", strength: "高" }, { price: "45,850", label: "第二支撐", strength: "中高" }], resistance: [{ price: "46,940–47,000", label: "第一壓力", strength: "高" }, { price: "47,300–47,600", label: "主要突破區", strength: "高" }] },
    scenarios: [
      { type: "Bull", probability: 20, tone: "good", title: "風險快速降溫", conditions: ["Brent < 100", "10Y < 4.8%", "外資現貨連買", "TX 淨空 < 8 萬", "TAIEX > 47,580"], result: "AI / 半導體重回主導。" },
      { type: "Base", probability: 55, tone: "warn", title: "45,900–47,300 高波動震盪", conditions: ["基本面撐住", "利率壓抑估值", "防禦領先", "AI 分化"], result: "高檔風險行情＋輪動。" },
      { type: "Bear", probability: 25, tone: "bad", title: "波段修正", conditions: ["Brent > 110", "10Y > 5%", "外資連賣", "TX < -90,000", "45,850 失守"], result: "高 Beta 與融資集中股風險最高。" }
    ],
    events: [
      { date: "09/16", time: "20:30", name: "美國 8 月零售銷售", importance: 4, watch: "消費是否仍過熱", sourceKeys: ["CENSUS"] },
      { date: "09/16", time: "日盤", name: "台指期 9 月結算週", importance: 4, watch: "換倉、基差、近次月部位", sourceKeys: ["TAIFEX"] },
      { date: "09/17", time: "02:00", name: "FOMC", importance: 5, watch: "利率、Dot Plot、SEP", sourceKeys: ["FED"] },
      { date: "09/17", time: "待公告", name: "台灣央行理監事會", importance: 4, watch: "利率、台幣、房市", sourceKeys: ["CBC"] },
      { date: "09/17–09/18", time: "—", name: "BOJ 會議", importance: 4, watch: "利率與日圓", sourceKeys: ["BOJ"] }
    ],
    freshness: [
      { name: "台股價格", date: "2026/09/11", state: "latest" }, { name: "三大法人", date: "2026/09/11", state: "latest" },
      { name: "期貨／選擇權", date: "2026/09/11", state: "latest" }, { name: "融資融券", date: "2026/09/11", state: "latest" },
      { name: "USD/TWD", date: "2026/09/11", state: "latest" }, { name: "美股", date: "2026/09/11", state: "latest" },
      { name: "借券完整序列", date: "N/A", state: "missing" }
    ],
    scoreTrend: [52, 49, 47, 50, 46, 44, 41, 43, 40, 37],
    invalidation: ["外資 5/10/20 日滾動值重新同步轉正。", "Brent 回落 100 下且 10Y 回到 4.8% 下。", "TAIEX 站回 47,300–47,600 且市場廣度同步改善。"]
  }
};
