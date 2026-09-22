(() => {
  const DASHBOARD_URL = `data/daily-dashboard.json?v=${Date.now()}`;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v = "") => String(v).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));
  const stars = n => "★".repeat(Math.max(0, Math.min(5, Number(n)||0))) + "☆".repeat(5 - Math.max(0, Math.min(5, Number(n)||0)));

  function setText(sel, value) { const el = $(sel); if (el) el.textContent = value ?? "N/A"; }
  function tone(score) { return Number(score) >= 55 ? "good" : Number(score) >= 45 ? "warn" : "bad"; }

  function renderStatus(d) {
    const stale = (d.freshness || []).filter(x => x.state === "stale").length;
    const missing = (d.freshness || []).filter(x => x.state === "missing").length;
    const el = $("#statusRibbon");
    if (el) el.innerHTML = `<span class="dot"></span><strong>${esc(d.meta?.dataStatus || "AUTO V2")}</strong> · 更新 ${esc(d.meta?.updatedAt || d.generatedAt || "N/A")} · 台股資料 ${esc(d.meta?.twDate || "N/A")}${stale ? ` · <span style="color:var(--bad)">STALE ${stale}</span>` : ""}${missing ? ` · <span style="color:var(--warn)">N/A ${missing}</span>` : ""}`;
  }

  function renderHero(d) {
    setText("#reportType", d.meta?.reportType);
    setText("#dataStatus", d.meta?.dataStatus);
    setText("#reportTitle", d.meta?.title);
    setText("#headline", d.headline);
    const meta = $("#metaLine");
    if (meta) meta.innerHTML = `<span>更新 <strong>${esc(d.meta?.updatedAt || "N/A")}</strong></span><span>台股 <strong>${esc(d.meta?.twDate || "N/A")}</strong></span><span>美股/美債 <strong>${esc(d.meta?.usDate || "N/A")}</strong></span><span>資料層 <strong>V2.2.1</strong></span>`;
    setText("#scoreValue", d.score);
    setText("#scoreLabel", d.scoreLabel);
    setText("#regime", d.regime);
    setText("#confidencePill", `可信度 ${d.confidence || "N/A"}`);
    const ring = $("#scoreRing");
    if (ring) { ring.style.setProperty("--score", Number(d.score)||0); ring.style.setProperty("--ring", `var(--${tone(d.score)})`); }
  }

  function renderKpis(d) {
    const el = $("#kpiGrid"); if (!el) return;
    el.innerHTML = (d.kpis || []).map(k => `<article class="kpi-card" data-tone="${esc(k.tone || "neutral")}"><div class="kpi-label">${esc(k.label)}</div><div class="kpi-value">${esc(k.value)}</div><div class="kpi-note">${esc(k.note)}</div></article>`).join("");
  }

  function renderQuick(d) {
    const el = $("#quickTake"); if (el) el.innerHTML = (d.quickTake || []).map(x => `<li>${esc(x)}</li>`).join("");
  }

  function renderThemes(d) {
    const el = $("#marketThemes"); if (!el) return;
    el.innerHTML = (d.marketThemes || []).map(x => `<article class="theme-card" data-tone="${esc(x.tone || "neutral")}"><div class="theme-meta"><span class="theme-rank">#${esc(x.rank)}</span><span>${esc(x.weight)}</span></div><h3>${esc(x.title)}</h3><div class="chain">${(x.chain||[]).map((s,i)=>`${i?'<span class="chain-arrow">→</span>':''}<span class="chain-step">${esc(s)}</span>`).join("")}</div><div class="theme-thesis">${esc(x.thesis)}</div><div class="watch-box"><strong>轉折觀察：</strong>${esc(x.watch)}</div></article>`).join("");
  }

  function renderGlobal(d) {
    const el = $("#globalGrid"); if (!el) return;
    el.innerHTML = (d.global || []).map(x => `<article class="global-card" data-tone="${esc(x.tone||"neutral")}"><div class="global-name">${esc(x.name)}</div><div class="global-value">${esc(x.value)}</div><div class="global-change">${esc(x.change)}</div><div class="global-note">${esc(x.note)}</div></article>`).join("");
  }

  function renderFocus(d) {
    const el = $("#focusGrid"); if (!el) return;
    el.innerHTML = (d.focus || []).map(x => `<article class="focus-card" data-tone="${esc(x.tone||"neutral")}"><div class="focus-rank">${esc(x.rank)}</div><h3>${esc(x.name)}</h3><div class="focus-value">${esc(x.value)}</div><p class="focus-why">${esc(x.why)}</p><div class="trigger"><strong>改判條件：</strong>${esc(x.trigger)}</div></article>`).join("");
  }

  function renderNews(d) {
    const filters = $("#newsFilters"), list = $("#newsList");
    if (!list) return;
    const cats = ["全部", ...new Set((d.news||[]).map(x=>x.category).filter(Boolean))];
    if (filters) filters.innerHTML = cats.map((c,i)=>`<button class="filter-button ${i===0?'active':''}" data-v2cat="${esc(c)}">${esc(c)}</button>`).join("");
    const draw = cat => {
      const rows = (d.news||[]).filter(x => cat === "全部" || x.category === cat);
      list.innerHTML = rows.length ? rows.map(n => `<article class="news-card"><div class="news-side"><div class="news-category">${esc(n.category)}</div><div class="news-time">${esc(n.time)}</div><div class="stars">${stars(n.impact)}</div></div><div class="news-main"><h3>${n.link?`<a href="${esc(n.link)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>`:esc(n.title)}</h3><div class="news-triad"><div><span>事實</span><p>${esc(n.fact)}</p></div><div><span>市場反應</span><p>${esc(n.reaction)}</p></div><div><span>台股傳導</span><p>${esc(n.twImpact)}</p></div></div><div class="news-sources"><span class="source-chip">${esc(n.source || "N/A")} · ${esc(n.verification || "N/A")}</span></div></div></article>`).join("") : `<div class="empty-state">沒有符合條件的消息。</div>`;
    };
    draw("全部");
    if (filters) $$("[data-v2cat]", filters).forEach(btn => btn.addEventListener("click", () => { $$("[data-v2cat]", filters).forEach(b=>b.classList.remove("active")); btn.classList.add("active"); draw(btn.dataset.v2cat); }));
    const search = $("#newsSearch");
    if (search) search.oninput = () => { const q=(search.value||"").toLowerCase(); const base=(d.news||[]).filter(n=>[n.category,n.title,n.fact,n.twImpact].join(" ").toLowerCase().includes(q)); const clone={...d,news:base}; renderNews(clone); };
  }

  function renderFlow(d) {
    const el = $("#flowTable"); if (!el || !d.flow) return;
    el.innerHTML = `<table><thead><tr>${(d.flow.headers||[]).map(x=>`<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${(d.flow.rows||[]).map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  function renderStats(sel, rows) { const el=$(sel); if(el) el.innerHTML=(rows||[]).map(x=>`<div class="stat-row" data-tone="${esc(x.tone||"neutral")}"><div class="stat-row-top"><span class="stat-label">${esc(x.label)}</span><strong class="stat-value">${esc(x.value)}</strong></div><div class="stat-note">${esc(x.note)}</div></div>`).join(""); }

  function renderBreadth(d) {
    const b=d.breadth||{}, el=$("#breadthPanel"); if(!el)return;
    const hasCounts=b.advancers!=null&&b.decliners!=null&&Number.isFinite(Number(b.advancers))&&Number.isFinite(Number(b.decliners));
    const total=hasCounts?Number(b.advancers)+Number(b.decliners):0;
    const up=(hasCounts&&total>0)?(Number(b.advancers)/total*100).toFixed(1):null;
    const down=up!=null?(100-Number(up)).toFixed(1):null;
    const bar=up!=null?`<div class="ratio-bar"><span class="up" style="width:${up}%"></span><span class="down" style="width:${down}%"></span></div><div class="ratio-legend"><span>上漲 ${up}%</span><span>下跌 ${down}%</span></div>`:`<div class="breadth-note">漲跌家數 N/A；不以 0 家代替缺漏資料。</div>`;
    el.innerHTML=`<div class="breadth-bars"><div class="breadth-header"><div class="mini-stat"><span>上漲家數</span><strong style="color:var(--good)">${esc(b.advancers??"N/A")}</strong></div><div class="mini-stat"><span>下跌家數</span><strong style="color:var(--bad)">${esc(b.decliners??"N/A")}</strong></div><div class="mini-stat"><span>TAIEX</span><strong>${esc(b.taiexChange)}</strong></div><div class="mini-stat"><span>櫃買</span><strong>${esc(b.otcChange)}</strong></div></div>${bar}<div class="breadth-note">${esc(b.note)}</div></div>`;
  }

  function renderLevels(d) {
    const l=d.levels||{}, el=$("#levelsPanel"); if(!el)return;
    const rr=(l.resistance||[]).map(x=>`<div class="level-row"><span>${esc(x.label)}</span><strong style="color:var(--bad)">${esc(x.price)}</strong><span class="strength">${esc(x.strength)}</span></div>`).join("");
    const ss=(l.support||[]).map(x=>`<div class="level-row"><span>${esc(x.label)}</span><strong style="color:var(--good)">${esc(x.price)}</strong><span class="strength">${esc(x.strength)}</span></div>`).join("");
    const cur = Number(l.current); const curText=Number.isFinite(cur)?cur.toLocaleString("zh-TW",{maximumFractionDigits:2}):"N/A";
    el.innerHTML=`<div class="level-board"><div class="level-current"><span>最新完整收盤</span><strong>${curText}</strong></div>${rr}${ss}</div>`;
  }

  function renderSectors(d) {
    const el=$("#sectorGrid"); if(!el)return;
    el.innerHTML=(d.sectors||[]).map(s=>`<article class="sector-card" data-tone="${esc(s.tone||"neutral")}"><div class="sector-top"><h3>${esc(s.name)}</h3><span class="sector-direction">${esc(s.direction||"N/A")}</span></div><div class="sector-score">當日 ${esc(s.change||"N/A")}</div><div class="sector-score">${esc(s.relative||"相對 TAIEX N/A")}</div><p class="sector-desc">${esc(s.desc||"")}</p><div class="global-note">${esc(s.source||"N/A")} · ${esc(s.asOf||"N/A")}</div></article>`).join("");
  }

  function renderScenarios(d) {
    const el=$("#scenarioGrid"); if(el) el.innerHTML=(d.scenarios||[]).map(s=>{const w=s.weight??s.probability??"N/A";return `<article class="scenario-card" data-tone="${esc(s.tone||"neutral")}"><div class="scenario-head"><span class="scenario-type">${esc(s.type)} CASE</span><span class="probability">權重 ${esc(w)}%</span></div><h3>${esc(s.title)}</h3><ul>${(s.conditions||[]).map(c=>`<li>${esc(c)}</li>`).join("")}</ul><div class="scenario-result">${esc(s.result)}</div></article>`}).join("");
    const inv=$("#invalidationList"); if(inv) inv.innerHTML=(d.invalidation||[]).map(x=>`<li>${esc(x)}</li>`).join("");
  }

  function renderEvents(d) { const el=$("#eventTimeline"); if(!el)return; el.innerHTML=(d.events||[]).map(e=>{const t=String(e.scheduledAt||"N/A"); return `<article class="event-row"><div class="event-date">${esc(t.slice(0,10))}</div><div class="event-time">${esc(t.slice(11,16)||"N/A")}</div><div class="event-name">${e.link?`<a href="${esc(e.link)}" target="_blank" rel="noopener noreferrer">${esc(e.title||e.name)}</a>`:esc(e.title||e.name)}</div><div class="importance">${stars(e.impact||e.importance)}</div><div class="event-watch">${esc(e.watch)}</div></article>`}).join(""); }

  function renderAudit(d) {
    const el=$("#freshnessGrid"); if(el) el.innerHTML=(d.freshness||[]).map(f=>`<div class="freshness-item" data-state="${esc(f.state)}"><span>${esc(f.name)}</span><div class="freshness-date"><i class="state-dot"></i>${esc(f.date)} · ${esc(f.source||"")}</div></div>`).join("");
    const sl=$("#sourceList"); if(sl) sl.innerHTML=(d.sources||[]).map(s=>`<a class="source-link" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"><span class="source-name">${esc(s.name)}</span><span class="source-tier">${esc(s.tier)}</span></a>`).join("");
  }

  function renderWhyVolume(d) {
    const w=d.whyVolume; if(!w)return;
    let section=$("#whyVolumeV2");
    if(!section){
      section=document.createElement("section"); section.id="whyVolumeV2"; section.className="section-block";
      const themes=$("#themes"); themes?.parentNode?.insertBefore(section,themes);
    }
    const ratio=w.ratioTo20dMedian!=null?`${Number(w.ratioTo20dMedian).toFixed(2)}×`:"N/A";
    section.innerHTML=`<div class="section-heading"><div><span class="eyebrow">WHY VOLUME?</span><h2>異常成交量解釋器</h2></div><p>有證據才解釋；無證據維持 N/A。</p></div><article class="panel"><div class="panel-head"><h3>${esc(w.label)}</h3><span class="panel-tag">${esc(w.confidence)}</span></div><div class="stat-stack"><div class="stat-row"><div class="stat-row-top"><span class="stat-label">成交值</span><strong class="stat-value">${esc(w.turnover)}</strong></div><div class="stat-note">資料日 ${esc(w.date)}</div></div><div class="stat-row"><div class="stat-row-top"><span class="stat-label">相對 20 日中位數</span><strong class="stat-value">${ratio}</strong></div><div class="stat-note">異常門檻 1.30×；不足 5 個歷史交易日則不判定。</div></div></div>${(w.candidates||[]).length?`<div class="watch-box"><strong>可驗證候選：</strong>${(w.candidates||[]).map(x=>x.link?`<a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>`:esc(x.title)).join("；")}</div>`:`<div class="watch-box"><strong>原因：</strong>N/A</div>`}<div class="breadth-note">${esc(w.note)}</div></article>`;
  }

  function apply(d) {
    if (new URLSearchParams(location.search).get("mode") === "weekly") return;
    window.__MR_V2 = d;
    renderStatus(d); renderHero(d); renderKpis(d); renderQuick(d); renderThemes(d); renderGlobal(d); renderFocus(d); renderNews(d); renderFlow(d); renderStats("#derivativesGrid",d.derivatives); renderStats("#leverageGrid",d.leverage); renderBreadth(d); renderLevels(d); renderSectors(d); renderScenarios(d); renderEvents(d); renderAudit(d); renderWhyVolume(d);
    const footer=$("#footerDisclaimer"); if(footer) footer.textContent="本網站用於市場研究與資訊整理，不構成任何投資建議。V2.2.1 日報只顯示已驗證的新資料；缺漏標示 N/A；情境百分比為條件權重而非預測機率。";
  }

  async function refresh() {
    try {
      const r=await fetch(DASHBOARD_URL,{cache:"no-store"});
      if(!r.ok) throw new Error(`HTTP ${r.status}`);
      const d=await r.json(); apply(d);
    } catch (e) {
      console.error("Market Radar V2 load failed",e);
      const ribbon=$("#statusRibbon"); if(ribbon) ribbon.innerHTML=`<span class="dot"></span><strong>V2 dashboard 尚未成功載入</strong> · ${esc(e.message)} · 目前頁面可能仍含舊靜態資料`;
    }
  }

  const run=()=>{ refresh(); setTimeout(refresh,1800); setTimeout(refresh,4500); };
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",run,{once:true}); else run();
  document.addEventListener("visibilitychange",()=>{ if(!document.hidden) refresh(); });
  setInterval(refresh,5*60*1000);
})();
