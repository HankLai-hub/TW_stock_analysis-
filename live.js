(() => {
  const $ = (sel) => document.querySelector(sel);
  const esc = (v = "") => String(v).replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const order = ["taiex", "otc", "tx", "turnover", "breadth", "usdTwd", "foreignSpot", "foreignTx", "putCall", "margin"];
  const labels = {
    taiex: "TAIEX", otc: "櫃買指數", tx: "臺指期 TX", turnover: "上市成交金額", breadth: "市場廣度",
    usdTwd: "USD/TWD", foreignSpot: "外資現貨", foreignTx: "外資 TX 淨部位", putCall: "Put/Call", margin: "融資餘額"
  };

  let latestLive = null;
  let latestBrief = null;
  let latestGlobal = null;
  let latestHistory = [];

  function mainDailyActive() {
    const weekly = document.querySelector('.mode-btn[data-mode="weekly"]');
    return !(weekly && weekly.classList.contains("active"));
  }

  function metricNumber(row) {
    const m = String(row?.value ?? "").replace(/,/g, "").match(/[+-]?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  }

  function isoDay(value) {
    const m = String(value || "").match(/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})/);
    return m ? `${m[1]}-${String(m[2]).padStart(2,"0")}-${String(m[3]).padStart(2,"0")}` : null;
  }

  function slashDay(value) {
    const d = isoDay(value);
    return d ? d.replaceAll("-", "/") : "N/A";
  }

  function fmtGenerated(value) {
    const s = String(value || "");
    const d = isoDay(s);
    const t = (s.match(/T(\d{2}:\d{2})/) || [])[1];
    return d ? `${d.replaceAll("-","/")}${t ? " " + t : ""}` : (value || "N/A");
  }

  function currentMetric(row, benchmark) {
    if (!row || row.state === "stale") return false;
    const d = isoDay(row.asOf);
    const b = isoDay(benchmark);
    return !(d && b && d < b);
  }

  function shortEnvironment(score) {
    if (!Number.isFinite(score)) return "資料不足";
    if (score < 30) return "偏空";
    if (score < 45) return "震盪偏空";
    if (score < 55) return "中性";
    if (score < 70) return "震盪偏多";
    return "偏多";
  }

  function marketRiskLabel(score) {
    if (!Number.isFinite(score)) return "資料不足";
    if (score < 30) return "高";
    if (score < 45) return "中高";
    if (score < 55) return "中";
    return "中低";
  }

  function syncMainTrend() {
    const svg = document.querySelector("#scoreTrend");
    const points = latestHistory
      .filter(x => x?.risk && typeof x.risk.score === "number")
      .slice(-10)
      .map(x => Number(x.risk.score));
    if (!svg || points.length < 2) return;

    const w=220,h=64,pad=5;
    const min=Math.min(...points)-3, max=Math.max(...points)+3;
    const pts=points.map((v,i)=>{
      const x=pad+i*((w-pad*2)/Math.max(1,points.length-1));
      const y=h-pad-((v-min)/Math.max(1,max-min))*(h-pad*2);
      return [x,y];
    });
    const last=pts[pts.length-1];
    svg.innerHTML = `<line x1="5" y1="58" x2="215" y2="58" stroke="var(--line)" stroke-width="1"/>
      <polyline points="${pts.map(p=>p.join(",")).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="var(--bad)" stroke="var(--surface)" stroke-width="2"/>`;
  }

  function syncDailyLanding() {
    if (!mainDailyActive() || !latestLive) return;

    const m = latestLive.metrics || {};
    const brief = latestBrief?.daily || {};
    const globalRisk = latestGlobal?.risk || {};
    const risk = latestLive.risk || {};
    const score = Number.isFinite(Number(risk.score)) ? Number(risk.score) : (Number.isFinite(Number(brief.score)) ? Number(brief.score) : null);
    const tradeDate = m.taiex?.asOf || "N/A";
    const reportDate = isoDay(latestLive.generatedAt) || isoDay(new Date().toISOString()) || "N/A";
    const reportDateSlash = reportDate.replaceAll("-", "/");

    let phaseWord = "盤後";
    const hour = Number((String(latestLive.generatedAt || "").match(/T(\d{2}):/) || [])[1]);
    if (Number.isFinite(hour) && hour < 9) phaseWord = "盤前";
    else if (String(latestLive.marketPhase || "").includes("盤中")) phaseWord = "盤中";

    const setText = (sel, value) => { const el=$(sel); if(el && value != null) el.textContent=value; };
    setText("#reportType", `每日${phaseWord}分析`);
    setText("#dataStatus", `${phaseWord}版｜價格與籌碼採最新完整交易日`);
    setText("#reportTitle", `${reportDateSlash} 台股${phaseWord}作戰儀表板`);
    setText("#headline", brief.headline || risk.note || "依最新官方資料更新市場風險。");

    const meta = $("#metaLine");
    if (meta) meta.innerHTML = `
      <span>更新 <strong>${esc(fmtGenerated(latestLive.generatedAt))}</strong></span>
      <span>台股 <strong>${esc(slashDay(tradeDate))}</strong></span>
      <span>外資期貨 <strong>${esc(slashDay(m.foreignTx?.asOf))}</strong></span>
      <span>時區 <strong>Asia/Taipei</strong></span>`;

    if (score != null) {
      setText("#scoreValue", score.toFixed(0));
      setText("#scoreLabel", risk.label || brief.label || shortEnvironment(score));
      const ring=$("#scoreRing");
      if (ring) {
        ring.style.setProperty("--score", score);
        ring.style.setProperty("--ring", score >= 60 ? "var(--good)" : score >= 45 ? "var(--warn)" : "var(--bad)");
      }
    }
    setText("#regime", globalRisk.label || "N/A");
    setText("#confidencePill", `可信度 ${risk.confidence ?? "N/A"}%`);

    const foreignSpot = metricNumber(m.foreignSpot);
    const foreignTx = metricNumber(m.foreignTx);
    const txCurrent = currentMetric(m.foreignTx, tradeDate);
    const kpis = [
      {
        label:"全球環境",
        value:globalRisk.label || "N/A",
        tone:(globalRisk.score ?? 50) < 35 ? "bad" : ((globalRisk.score ?? 50) < 45 ? "warn" : "neutral"),
        note:Number.isFinite(Number(globalRisk.score)) ? `Global Macro ${Number(globalRisk.score).toFixed(0)}/100` : "官方宏觀資料"
      },
      { label:"短線環境", value:shortEnvironment(score), tone:score != null && score < 45 ? "bad" : "warn", note:`Risk Score ${score == null ? "N/A" : score.toFixed(0)}` },
      {
        label:"外資方向",
        value:foreignSpot == null ? "資料不足" : (foreignSpot < 0 ? "降低曝險" : "增加曝險"),
        tone:foreignSpot == null ? "neutral" : (foreignSpot < 0 ? "bad" : "good"),
        note:`現貨 ${m.foreignSpot?.value || "N/A"} · ${slashDay(m.foreignSpot?.asOf)}`
      },
      {
        label:"期貨方向",
        value:!txCurrent ? "資料落後" : (foreignTx == null ? "資料不足" : (foreignTx < -80000 ? "偏空" : (foreignTx > 0 ? "偏多" : "中性"))),
        tone:!txCurrent ? "warn" : (foreignTx != null && foreignTx < -80000 ? "bad" : "neutral"),
        note:`外資 TX ${m.foreignTx?.value || "N/A"} · ${slashDay(m.foreignTx?.asOf)}`
      },
      {
        label:"槓桿",
        value:m.margin?.state === "stale" ? "沿用上一筆" : "盤後監控",
        tone:m.margin?.state === "stale" ? "warn" : "neutral",
        note:`${m.margin?.value || "N/A"} · ${slashDay(m.margin?.asOf)}`
      },
      { label:"市場風險", value:marketRiskLabel(score), tone:score != null && score < 45 ? "bad" : "warn", note:risk.drivers?.[0]?.reason || "依價格、資金與廣度綜合" },
    ];
    const kpiGrid=$("#kpiGrid");
    if (kpiGrid) kpiGrid.innerHTML = kpis.map(k=>`<article class="kpi-card" data-tone="${esc(k.tone)}">
      <div class="kpi-label">${esc(k.label)}</div><div class="kpi-value">${esc(k.value)}</div><div class="kpi-note">${esc(k.note)}</div></article>`).join("");

    const quick=$("#quickTake");
    if (quick && Array.isArray(brief.quickTake) && brief.quickTake.length) {
      quick.innerHTML = brief.quickTake.map(x=>`<li>${esc(x)}</li>`).join("");
    }

    const ribbon=$("#statusRibbon");
    if (ribbon) {
      const staleTx = !txCurrent;
      ribbon.innerHTML = `<span class="dot"></span><strong>自動日報已同步</strong> · 更新 ${esc(fmtGenerated(latestLive.generatedAt))} · 最新台股完整交易日 ${esc(slashDay(tradeDate))}${staleTx ? ` · <span style="color:var(--warn)">外資 TX 尚停在 ${esc(slashDay(m.foreignTx?.asOf))}，未視為今日訊號</span>` : ""}`;
    }

    // Update current daily institutional / derivative / leverage summaries where
    // the live layer has an official comparable value.
    const firstFlowCell = document.querySelector("#flowTable tbody tr:first-child td:nth-child(2)");
    if (firstFlowCell && m.foreignSpot?.value) firstFlowCell.textContent = m.foreignSpot.value;

    const derivatives=$("#derivativesGrid");
    if (derivatives) {
      const rows=[
        ["臺指期 TX",m.tx?.value || "N/A",`${m.tx?.change || ""} · ${slashDay(m.tx?.asOf)}`],
        ["外資 TX 淨部位",m.foreignTx?.value || "N/A",`${txCurrent ? "最新交易日" : "資料落後"} · ${slashDay(m.foreignTx?.asOf)}`],
        ["外資 TX 多／空",m.foreignTx?.change || "N/A",txCurrent ? "官方盤後" : "不納入今日方向"],
        ["Put/Call",m.putCall?.value || "N/A",`${m.putCall?.change || ""} · ${slashDay(m.putCall?.asOf)}`],
      ];
      derivatives.innerHTML=rows.map(r=>`<div class="stat-row" data-tone="neutral"><div class="stat-row-top"><span class="stat-label">${esc(r[0])}</span><strong class="stat-value">${esc(r[1])}</strong></div><div class="stat-note">${esc(r[2])}</div></div>`).join("");
    }

    const leverage=$("#leverageGrid");
    if (leverage) {
      const rows=[
        ["USD/TWD",m.usdTwd?.value || "N/A",`${slashDay(m.usdTwd?.asOf)} · ${m.usdTwd?.source || ""}`],
        ["融資餘額",m.margin?.value || "N/A",`${m.margin?.change || ""} · ${slashDay(m.margin?.asOf)}`],
      ];
      leverage.innerHTML=rows.map(r=>`<div class="stat-row" data-tone="neutral"><div class="stat-row-top"><span class="stat-label">${esc(r[0])}</span><strong class="stat-value">${esc(r[1])}</strong></div><div class="stat-note">${esc(r[2])}</div></div>`).join("");
    }

    const b = String(m.breadth?.value || "").match(/([\d,]+)↑\s*\/\s*([\d,]+)↓/);
    const breadthPanel=$("#breadthPanel");
    if (b && breadthPanel) {
      const up=Number(b[1].replaceAll(",","")), down=Number(b[2].replaceAll(",","")), total=Math.max(1,up+down);
      const upPct=(up/total*100).toFixed(1), downPct=(down/total*100).toFixed(1);
      breadthPanel.innerHTML=`<div class="breadth-bars"><div class="breadth-header">
        <div class="mini-stat"><span>上漲家數</span><strong style="color:var(--good)">${up}</strong></div>
        <div class="mini-stat"><span>下跌家數</span><strong style="color:var(--bad)">${down}</strong></div>
        <div class="mini-stat"><span>TAIEX</span><strong>${esc(m.taiex?.change || "")}</strong></div>
        <div class="mini-stat"><span>櫃買</span><strong>${esc(m.otc?.change || "")}</strong></div>
      </div><div class="ratio-bar"><span class="up" style="width:${upPct}%"></span><span class="down" style="width:${downPct}%"></span></div>
      <div class="ratio-legend"><span>上漲 ${upPct}%</span><span>下跌 ${downPct}%</span></div>
      <div class="breadth-note">最新官方完整交易日 ${esc(slashDay(m.breadth?.asOf))}。</div></div>`;
    }

    document.title = `${reportDateSlash} 台股${phaseWord}作戰儀表板｜TW Market Radar`;
    syncMainTrend();
  }

  function stateLabel(state) {
    return ({licensed_intraday:"授權盤中", official_close:"官方收盤", official_daily:"官方日資料", official_afterhours:"官方盤後", stale:"沿用上一筆", waiting:"等待", missing:"N/A"})[state] || state || "—";
  }


  function riskClass(score) {
    if (score == null || Number.isNaN(score)) return "na";
    if (score >= 70) return "strong-on";
    if (score >= 55) return "on";
    if (score >= 45) return "neutral";
    if (score >= 30) return "off";
    return "strong-off";
  }

  function renderRisk(data) {
    const grid = $("#autoMetricGrid");
    if (!grid) return;
    let panel = $("#autoRiskPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "autoRiskPanel";
      panel.className = "auto-risk-panel";
      grid.parentNode.insertBefore(panel, grid);
    }

    const risk = data.risk || {};
    const score = typeof risk.score === "number" ? risk.score : null;
    const cls = riskClass(score);
    const drivers = Array.isArray(risk.drivers) ? risk.drivers : [];
    const confidence = Number.isFinite(Number(risk.confidence)) ? Number(risk.confidence) : 0;

    panel.dataset.risk = cls;
    panel.innerHTML = `
      <div class="auto-risk-score">
        <div class="auto-risk-kicker">MARKET RISK SCORE</div>
        <div class="auto-risk-number">${score == null ? "N/A" : esc(score.toFixed(0))}</div>
        <div class="auto-risk-label">${esc(risk.label || "資料不足")}</div>
        <div class="auto-risk-confidence">模型完整度 ${esc(confidence)}%</div>
      </div>
      <div class="auto-risk-body">
        <div class="auto-risk-title">目前市場主導力量</div>
        <div class="auto-risk-drivers">
          ${drivers.length ? drivers.map(d => `
            <div class="auto-risk-driver" data-direction="${esc(d.direction || "neutral")}">
              <span>${esc(d.name || "")}</span>
              <strong>${esc(d.reason || "")}</strong>
            </div>
          `).join("") : `<div class="auto-risk-empty">等待足夠資料建立風險判讀。</div>`}
        </div>
        <div class="auto-risk-note">${esc(risk.note || "")}</div>
      </div>
    `;
  }

  function render(data) {
    const badge = $("#autoUpdateBadge");
    const generated = $("#autoGeneratedAt");
    const phase = $("#autoMarketPhase");
    const next = $("#autoNextExpected");
    const grid = $("#autoMetricGrid");
    const feed = $("#autoFeedNotice");
    const errors = $("#autoErrors");
    if (!grid) return;

    const ok = !data.errors || data.errors.length === 0;
    badge.textContent = ok ? "AUTO · OK" : `AUTO · ${data.errors.length} SOURCE WARNING`;
    badge.dataset.state = ok ? "ok" : "warn";
    generated.textContent = data.generatedAt || "N/A";
    phase.textContent = data.marketPhase || "N/A";
    next.textContent = data.nextExpected || "N/A";

    renderRisk(data);

    grid.innerHTML = order.map(key => {
      const m = (data.metrics || {})[key] || {};
      return `<article class="auto-metric" data-state="${esc(m.state || "missing")}">
        <div class="auto-metric-top"><span>${esc(labels[key])}</span><span class="auto-state">${esc(stateLabel(m.state))}</span></div>
        <strong>${esc(m.value || "N/A")}</strong>
        <div class="auto-change">${esc(m.change || "")}</div>
        <div class="auto-asof">資料時間 ${esc(m.asOf || "N/A")} · ${esc(m.source || "")}</div>
      </article>`;
    }).join("");

    const f = data.intradayFeed || {};
    feed.dataset.state = f.state || "not_configured";
    feed.innerHTML = `<strong>${esc(f.label || "盤中資料源狀態")}</strong><span>${esc(f.note || "")}</span>${f.vendor ? `<em>${esc(f.vendor)}</em>` : ""}`;

    if (data.errors && data.errors.length) {
      errors.hidden = false;
      errors.innerHTML = `<strong>本次更新有部分來源失敗：</strong>${data.errors.slice(0, 4).map(e => `<span>${esc(e.source)}：${esc(e.message)}</span>`).join("")}`;
    } else {
      errors.hidden = true;
      errors.innerHTML = "";
    }
  }

  async function renderTrend() {
    const panel = $("#autoRiskPanel");
    if (!panel) return;
    try {
      const r = await fetch(`data/live-history.json?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) return;
      const rows = await r.json();
      latestHistory = Array.isArray(rows) ? rows : [];
      const points = (Array.isArray(rows) ? rows : [])
        .filter(x => x && x.risk && typeof x.risk.score === "number")
        .slice(-8);
      if (!points.length) { syncMainTrend(); return; }

      let trend = panel.querySelector(".auto-risk-trend");
      if (!trend) {
        trend = document.createElement("div");
        trend.className = "auto-risk-trend";
        panel.querySelector(".auto-risk-body")?.appendChild(trend);
      }

      syncMainTrend();
      trend.innerHTML = `
        <span class="auto-risk-trend-label">近期風險分數</span>
        <div class="auto-risk-spark">
          ${points.map(p => {
            const s = Math.max(0, Math.min(100, Number(p.risk.score)));
            const dt = String(p.generatedAt || "").slice(11,16);
            return `<div class="auto-risk-bar-wrap" title="${esc(dt)} · ${esc(s.toFixed(0))}">
              <div class="auto-risk-bar" style="height:${Math.max(8, s)}%"></div>
              <span>${esc(s.toFixed(0))}</span>
            </div>`;
          }).join("")}
        </div>
      `;
    } catch (_) {}
  }


  function renderAutoBrief(brief) {
    const grid = $("#autoMetricGrid");
    if (!grid) return;
    let panel = $("#autoBriefPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "autoBriefPanel";
      panel.className = "auto-brief-panel";
      grid.parentNode.insertBefore(panel, grid);
    }

    const daily = brief?.daily || {};
    const weekly = brief?.weekly || {};
    panel.innerHTML = `
      <div class="auto-brief-head">
        <div>
          <span class="auto-brief-kicker">AUTO RESEARCH BRIEF</span>
          <h3>自動市場判讀</h3>
        </div>
        <div class="auto-brief-tabs" role="group" aria-label="自動報告模式">
          <button class="auto-brief-tab active" data-brief-mode="daily">日報</button>
          <button class="auto-brief-tab" data-brief-mode="weekly">週報</button>
        </div>
      </div>
      <div class="auto-brief-content" data-brief-view="daily"></div>
      <div class="auto-brief-content" data-brief-view="weekly" hidden></div>
    `;

    const renderDaily = () => {
      const target = panel.querySelector('[data-brief-view="daily"]');
      const bullets = Array.isArray(daily.quickTake) ? daily.quickTake : [];
      const invalidation = Array.isArray(daily.invalidation) ? daily.invalidation : [];
      target.innerHTML = `
        <div class="auto-brief-hero" data-tone="${esc(daily.tone || 'neutral')}">
          <div><span>即時判讀</span><strong>${esc(daily.label || '資料不足')}</strong></div>
          <div class="auto-brief-score">${daily.score == null ? 'N/A' : esc(Number(daily.score).toFixed(0))}</div>
        </div>
        ${daily.resonance ? `<div class="auto-resonance" data-tone="${esc(daily.resonance.tone || 'neutral')}">
          <div><span>CROSS-MARKET RESONANCE</span><strong>${esc(daily.resonance.label || '')}</strong></div>
          <div class="auto-resonance-score">${daily.resonance.score == null ? 'N/A' : esc(Number(daily.resonance.score).toFixed(0))}</div>
          <p>${esc(daily.resonance.note || '')}</p>
        </div>` : ''}
        <p class="auto-brief-headline">${esc(daily.headline || '')}</p>
        <div class="auto-brief-bullets">${bullets.map(x => `<div><span>•</span><p>${esc(x)}</p></div>`).join('')}</div>
        <div class="auto-brief-outlook">
          <div><span>短線 1–5 日</span><p>${esc(daily.shortView || '')}</p></div>
          <div><span>波段 2–8 週</span><p>${esc(daily.swingView || '')}</p></div>
        </div>
        <div class="auto-brief-invalidation">
          <span>改判條件</span>
          <ol>${invalidation.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
        </div>
        <div class="auto-brief-note">${esc(daily.dataNote || '')}</div>
      `;
    };

    const renderWeekly = () => {
      const target = panel.querySelector('[data-brief-view="weekly"]');
      const bullets = Array.isArray(weekly.quickTake) ? weekly.quickTake : [];
      const stats = Array.isArray(weekly.stats) ? weekly.stats : [];
      target.innerHTML = `
        <div class="auto-brief-weekly-status" data-state="${esc(weekly.status || 'collecting')}">
          <strong>${esc(weekly.status === 'ready' ? '自動週報' : '週報資料累積中')}</strong>
          <span>${esc(weekly.headline || '')}</span>
        </div>
        ${stats.length ? `<div class="auto-brief-stats">${stats.map(s => `<div><span>${esc(s.label)}</span><strong>${s.value == null ? 'N/A' : esc(s.value)}</strong></div>`).join('')}</div>` : ''}
        <div class="auto-brief-bullets">${bullets.map(x => `<div><span>•</span><p>${esc(x)}</p></div>`).join('')}</div>
        <div class="auto-brief-note">${esc(weekly.dataNote || '')}</div>
      `;
    };

    renderDaily();
    renderWeekly();

    panel.querySelectorAll('.auto-brief-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.briefMode;
        panel.querySelectorAll('.auto-brief-tab').forEach(x => x.classList.toggle('active', x === btn));
        panel.querySelectorAll('[data-brief-view]').forEach(view => { view.hidden = view.dataset.briefView !== mode; });
      });
    });
  }


  function globalMetricCard(label, row = {}) {
    return `<article class="auto-global-metric" data-state="${esc(row.state || 'missing')}">
      <div><span>${esc(label)}</span><small>${esc(row.source || '')}</small></div>
      <strong>${esc(row.display || 'N/A')}</strong>
      <p>${esc(row.change || '')}</p>
      <em>${esc(row.asOf || 'N/A')}</em>
    </article>`;
  }

  function renderGlobal(globalData) {
    const grid = $("#autoMetricGrid");
    if (!grid) return;
    let panel = $("#autoGlobalPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "autoGlobalPanel";
      panel.className = "auto-global-panel";
      grid.parentNode.insertBefore(panel, grid);
    }

    const macro = globalData?.macro || {};
    const risk = globalData?.risk || {};
    const news = Array.isArray(globalData?.news) ? globalData.news : [];
    const events = Array.isArray(globalData?.events) ? globalData.events : [];
    const reaction = globalData?.reaction || {};
    const errors = Array.isArray(globalData?.errors) ? globalData.errors : [];
    const riskScore = typeof risk.score === 'number' ? risk.score : null;

    panel.innerHTML = `
      <div class="auto-global-head">
        <div>
          <span class="auto-global-kicker">GLOBAL MACRO & OFFICIAL NEWS</span>
          <h3>全球宏觀與官方消息</h3>
        </div>
        <div class="auto-global-risk" data-risk="${esc(riskClass(riskScore))}">
          <span>GLOBAL MACRO</span>
          <strong>${riskScore == null ? 'N/A' : esc(riskScore.toFixed(0))}</strong>
          <em>${esc(risk.label || '資料不足')}</em>
        </div>
      </div>

      <div class="auto-global-drivers">
        ${(Array.isArray(risk.drivers) && risk.drivers.length) ? risk.drivers.map(d => `
          <div data-direction="${esc(d.direction || 'neutral')}"><span>${esc(d.name || '')}</span><strong>${esc(d.reason || '')}</strong></div>
        `).join('') : '<span>全球宏觀資料累積中。</span>'}
      </div>

      <div class="auto-global-section-title"><span>官方宏觀資料</span><em>${esc(globalData?.generatedAt || '')}</em></div>
      <div class="auto-global-grid">
        ${globalMetricCard('美國10Y', macro.us10y)}
        ${globalMetricCard('10Y實質利率', macro.real10y)}
        ${globalMetricCard('2Y–10Y利差', macro.spread2s10s)}
        ${globalMetricCard('Brent', macro.brent)}
        ${globalMetricCard('美國CPI', macro.cpi)}
        ${globalMetricCard('失業率', macro.unemployment)}
      </div>

      <div class="auto-global-section-title"><span>官方跨資產反應</span><em>不使用未授權股價指數</em></div>
      <div class="auto-global-reaction" data-tone="${esc(reaction.tone || 'neutral')}">
        <strong>${esc(reaction.label || '資料累積中')}</strong>
        <p>${esc(reaction.note || '')}</p>
        <div>${(Array.isArray(reaction.bullets) ? reaction.bullets : []).map(x => `<span>${esc(x)}</span>`).join('')}</div>
      </div>

      <div class="auto-global-section-title"><span>未來 1–2 週官方事件</span><em>台北時間</em></div>
      <div class="auto-event-calendar">
        ${events.length ? events.slice(0, 8).map(e => `
          <article>
            <time>${esc(e.scheduledAt || '')}</time>
            <div>
              <div><span>${esc(e.source || '')}</span><em>${'★'.repeat(Math.max(1, Math.min(5, Number(e.impact) || 1)))}</em></div>
              <a href="${esc(e.link || '#')}" target="_blank" rel="noopener noreferrer">${esc(e.title || '')}</a>
              <p>${esc(e.watch || '')}</p>
            </div>
          </article>
        `).join('') : '<div class="auto-news-empty">未來 14 天沒有符合目前篩選條件的高影響官方事件。</div>'}
      </div>

      <div class="auto-global-section-title"><span>官方消息</span><em>只收 Fed / BLS 原始來源</em></div>
      <div class="auto-official-news">
        ${news.length ? news.slice(0, 6).map(n => `
          <article>
            <div class="auto-news-meta">
              <span>${esc(n.source || '')}</span>
              <span>${'★'.repeat(Math.max(1, Math.min(5, Number(n.impact) || 1)))}</span>
              <em>${esc(n.category || '')}</em>
            </div>
            <a href="${esc(n.link || '#')}" target="_blank" rel="noopener noreferrer">${esc(n.title || '')}</a>
            <p>${esc(n.transmission || '')}</p>
            <small>${esc(n.publishedAt || '')}</small>
          </article>
        `).join('') : '<div class="auto-news-empty">目前沒有新的高相關官方事件。</div>'}
      </div>

      ${errors.length ? `<details class="auto-global-errors"><summary>全球資料 ${errors.length} 個 warning</summary>${errors.slice(0, 6).map(e => `<span>${esc(e.source)}：${esc(e.message)}</span>`).join('')}</details>` : ''}
    `;
  }

  async function loadGlobal() {
    try {
      const r = await fetch(`data/global.json?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) return;
      latestGlobal = await r.json();
      renderGlobal(latestGlobal);
      syncDailyLanding();
    } catch (_) {}
  }

  async function loadBrief() {
    try {
      const r = await fetch(`data/auto-brief.json?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) return;
      latestBrief = await r.json();
      renderAutoBrief(latestBrief);
      syncDailyLanding();
    } catch (_) {}
  }

  async function load() {
    try {
      const response = await fetch(`data/live.json?t=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      latestLive = await response.json();
      render(latestLive);
      syncDailyLanding();
      renderTrend();
      loadBrief();
      loadGlobal();
    } catch (error) {
      const badge = $("#autoUpdateBadge");
      if (badge) { badge.textContent = "AUTO · LOAD ERROR"; badge.dataset.state = "warn"; }
      const errors = $("#autoErrors");
      if (errors) { errors.hidden = false; errors.textContent = `自動資料讀取失敗：${error.message}`; }
    }
  }

  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => setTimeout(syncDailyLanding, 20));
  });

  load();
  setInterval(load, 5 * 60 * 1000);
})();
