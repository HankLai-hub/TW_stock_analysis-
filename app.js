(() => {
  const DATA = window.MARKET_DASHBOARD_DATA;
  if (!DATA) throw new Error("MARKET_DASHBOARD_DATA is missing");

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const sourceMap = Object.fromEntries(DATA.sources.map(s => [s.key, s]));

  let mode = new URLSearchParams(location.search).get("mode") === "weekly" ? "weekly" : "daily";
  let activeCategory = "全部";
  let newsQuery = "";

  const toneColor = (tone) => ({ good: "var(--good)", bad: "var(--bad)", warn: "var(--warn)", neutral: "var(--neutral)" }[tone] || "var(--neutral)");
  const escapeHTML = (value = "") => String(value).replace(/[&<>'"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[ch]));
  const stars = (n) => "★".repeat(Math.max(0, Math.min(5, n))) + "☆".repeat(5 - Math.max(0, Math.min(5, n)));

  function getReport() { return DATA[mode]; }

  function renderAll() {
    const d = getReport();
    document.title = `${d.meta.title}｜TW Market Radar`;
    renderModeButtons();
    renderStatus(d);
    renderHero(d);
    renderKPIs(d);
    renderExecutive(d);
    renderThemes(d);
    renderGlobal(d);
    renderFocus(d);
    renderNewsFilters(d);
    renderNews(d);
    renderFlow(d);
    renderStats("#derivativesGrid", d.derivatives);
    renderStats("#leverageGrid", d.leverage);
    renderBreadth(d);
    renderLevels(d);
    renderSectors(d);
    renderScenarios(d);
    renderEvents(d);
    renderAudit(d);
    renderTrend(d.scoreTrend);
    $("#footerDisclaimer").textContent = DATA.product.disclaimer;
    syncURL();
  }

  function renderModeButtons() {
    $$(".mode-btn").forEach(btn => btn.classList.toggle("active", btn.dataset.mode === mode));
  }

  function renderStatus(d) {
    const latest = d.freshness.filter(x => x.state === "latest").length;
    const missing = d.freshness.filter(x => x.state === "missing").length;
    $("#statusRibbon").innerHTML = `<span class="dot"></span><strong>${escapeHTML(d.meta.dataStatus)}</strong> · 更新 ${escapeHTML(d.meta.updatedAt)} · ${latest} 項資料為最新完整交易日${missing ? ` · <span style="color:var(--warn)">${missing} 項缺漏已標示 N/A</span>` : ""}`;
  }

  function renderHero(d) {
    $("#reportType").textContent = d.meta.reportType;
    $("#dataStatus").textContent = d.meta.dataStatus;
    $("#reportTitle").textContent = d.meta.title;
    $("#headline").textContent = d.headline;
    $("#metaLine").innerHTML = `
      <span>更新 <strong>${escapeHTML(d.meta.updatedAt)}</strong></span>
      <span>台股 <strong>${escapeHTML(d.meta.twDate)}</strong></span>
      <span>美股 <strong>${escapeHTML(d.meta.usDate)}</strong></span>
      <span>時區 <strong>${escapeHTML(d.meta.timezone)}</strong></span>`;
    $("#scoreValue").textContent = d.score;
    $("#scoreLabel").textContent = d.scoreLabel;
    $("#regime").textContent = d.regime;
    $("#confidencePill").textContent = `可信度 ${d.confidence}`;
    const ring = $("#scoreRing");
    ring.style.setProperty("--score", d.score);
    ring.style.setProperty("--ring", d.score >= 60 ? "var(--good)" : d.score >= 45 ? "var(--warn)" : "var(--bad)");
    ring.setAttribute("aria-label", `大盤綜合分數 ${d.score} 分，${d.scoreLabel}`);
  }

  function renderKPIs(d) {
    $("#kpiGrid").innerHTML = d.kpis.map(k => `
      <article class="kpi-card" data-tone="${escapeHTML(k.tone)}">
        <div class="kpi-label">${escapeHTML(k.label)}</div>
        <div class="kpi-value">${escapeHTML(k.value)}</div>
        <div class="kpi-note">${escapeHTML(k.note)}</div>
      </article>`).join("");
  }

  function renderExecutive(d) {
    $("#quickTake").innerHTML = d.quickTake.map(item => `<li>${escapeHTML(item)}</li>`).join("");
  }

  function renderThemes(d) {
    $("#marketThemes").innerHTML = d.marketThemes.map(theme => `
      <article class="theme-card" data-tone="${escapeHTML(theme.tone)}">
        <div class="theme-meta"><span class="theme-rank">#${theme.rank}</span><span>${escapeHTML(theme.weight)}</span></div>
        <h3>${escapeHTML(theme.title)}</h3>
        <div class="chain">${theme.chain.map((step, i) => `${i ? '<span class="chain-arrow">→</span>' : ''}<span class="chain-step">${escapeHTML(step)}</span>`).join("")}</div>
        <div class="theme-thesis">${escapeHTML(theme.thesis)}</div>
        <div class="watch-box"><strong>轉折觀察：</strong>${escapeHTML(theme.watch)}</div>
      </article>`).join("");
  }

  function renderGlobal(d) {
    $("#globalGrid").innerHTML = d.global.map(g => `
      <article class="global-card" data-tone="${escapeHTML(g.tone)}">
        <div class="global-name">${escapeHTML(g.name)}</div>
        <div class="global-value">${escapeHTML(g.value)}</div>
        <div class="global-change">${escapeHTML(g.change)}</div>
        <div class="global-note">${escapeHTML(g.note)}</div>
      </article>`).join("");
  }

  function renderFocus(d) {
    $("#focusGrid").innerHTML = d.focus.map(f => `
      <article class="focus-card" data-tone="${escapeHTML(f.tone)}">
        <div class="focus-rank">${f.rank}</div>
        <h3>${escapeHTML(f.name)}</h3>
        <div class="focus-value">${escapeHTML(f.value)}</div>
        <p class="focus-why">${escapeHTML(f.why)}</p>
        <div class="trigger"><strong>改判條件：</strong>${escapeHTML(f.trigger)}</div>
      </article>`).join("");
  }

  function renderNewsFilters(d) {
    const cats = ["全部", ...new Set(d.news.map(n => n.category))];
    if (!cats.includes(activeCategory)) activeCategory = "全部";
    $("#newsFilters").innerHTML = cats.map(cat => `<button class="filter-button ${cat === activeCategory ? "active" : ""}" data-category="${escapeHTML(cat)}">${escapeHTML(cat)}</button>`).join("");
    $$(".filter-button").forEach(btn => btn.addEventListener("click", () => {
      activeCategory = btn.dataset.category;
      renderNewsFilters(getReport());
      renderNews(getReport());
    }));
  }

  function renderNews(d) {
    const q = newsQuery.trim().toLowerCase();
    const rows = d.news.filter(n => {
      const matchCat = activeCategory === "全部" || n.category === activeCategory;
      const hay = [n.category, n.title, n.fact, n.reaction, n.twImpact].join(" ").toLowerCase();
      return matchCat && (!q || hay.includes(q));
    });
    $("#newsList").innerHTML = rows.length ? rows.map(n => {
      const links = (n.sourceKeys || []).map(key => sourceMap[key]).filter(Boolean).map(s => `<a class="source-chip" href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(s.key)} · ${escapeHTML(s.tier)}</a>`).join("");
      return `<article class="news-card">
        <div class="news-side">
          <div class="news-category">${escapeHTML(n.category)}</div>
          <div class="news-time">${escapeHTML(n.time)}</div>
          <div class="stars" aria-label="影響程度 ${n.impact} 星">${stars(n.impact)}</div>
        </div>
        <div class="news-main">
          <h3>${escapeHTML(n.title)}</h3>
          <div class="news-triad">
            <div><span>事實</span><p>${escapeHTML(n.fact)}</p></div>
            <div><span>市場反應</span><p>${escapeHTML(n.reaction)}</p></div>
            <div><span>台股傳導</span><p>${escapeHTML(n.twImpact)}</p></div>
          </div>
          <div class="news-sources">${links || '<span class="source-chip">來源待補</span>'}</div>
        </div>
      </article>`;
    }).join("") : `<div class="empty-state">找不到符合條件的消息。換一個分類或關鍵字試試。</div>`;
  }

  function renderFlow(d) {
    const head = `<thead><tr>${d.flow.headers.map(h => `<th>${escapeHTML(h)}</th>`).join("")}</tr></thead>`;
    const body = `<tbody>${d.flow.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHTML(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
    $("#flowTable").innerHTML = `<table>${head}${body}</table>`;
  }

  function renderStats(target, stats) {
    $(target).innerHTML = stats.map(s => `
      <div class="stat-row" data-tone="${escapeHTML(s.tone || "neutral")}">
        <div class="stat-row-top"><span class="stat-label">${escapeHTML(s.label)}</span><strong class="stat-value">${escapeHTML(s.value)}</strong></div>
        <div class="stat-note">${escapeHTML(s.note)}</div>
      </div>`).join("");
  }

  function renderBreadth(d) {
    const b = d.breadth;
    const total = Math.max(1, b.advancers + b.decliners);
    const upPct = (b.advancers / total * 100).toFixed(1);
    const downPct = (b.decliners / total * 100).toFixed(1);
    $("#breadthPanel").innerHTML = `
      <div class="breadth-bars">
        <div class="breadth-header">
          <div class="mini-stat"><span>上漲家數</span><strong style="color:var(--good)">${b.advancers}</strong></div>
          <div class="mini-stat"><span>下跌家數</span><strong style="color:var(--bad)">${b.decliners}</strong></div>
          <div class="mini-stat"><span>TAIEX</span><strong>${escapeHTML(b.taiexChange)}</strong></div>
          <div class="mini-stat"><span>櫃買</span><strong>${escapeHTML(b.otcChange)}</strong></div>
        </div>
        <div class="ratio-bar" aria-label="上漲家數 ${upPct}%，下跌家數 ${downPct}%"><span class="up" style="width:${upPct}%"></span><span class="down" style="width:${downPct}%"></span></div>
        <div class="ratio-legend"><span>上漲 ${upPct}%</span><span>下跌 ${downPct}%</span></div>
        <div class="breadth-note">${escapeHTML(b.note)}</div>
      </div>`;
  }

  function renderLevels(d) {
    const l = d.levels;
    const supports = l.support.map(x => `<div class="level-row"><span>${escapeHTML(x.label)}</span><strong style="color:var(--good)">${escapeHTML(x.price)}</strong><span class="strength">強度 ${escapeHTML(x.strength)}</span></div>`).join("");
    const resistance = l.resistance.map(x => `<div class="level-row"><span>${escapeHTML(x.label)}</span><strong style="color:var(--bad)">${escapeHTML(x.price)}</strong><span class="strength">強度 ${escapeHTML(x.strength)}</span></div>`).join("");
    $("#levelsPanel").innerHTML = `<div class="level-board"><div class="level-current"><span>最新完整收盤</span><strong>${Number(l.current).toLocaleString("zh-TW", { maximumFractionDigits: 2 })}</strong></div>${resistance}${supports}</div>`;
  }

  function renderSectors(d) {
    $("#sectorGrid").innerHTML = d.sectors.map(s => `
      <article class="sector-card" data-tone="${escapeHTML(s.tone)}">
        <div class="sector-top"><h3>${escapeHTML(s.name)}</h3><span class="sector-direction">${escapeHTML(s.direction)}</span></div>
        <div class="sector-meter"><span style="width:${Math.max(0, Math.min(100, s.score))}%"></span></div>
        <div class="sector-score">相對強度 ${s.score}/100</div>
        <p class="sector-desc">${escapeHTML(s.desc)}</p>
      </article>`).join("");
  }

  function renderScenarios(d) {
    $("#scenarioGrid").innerHTML = d.scenarios.map(s => `
      <article class="scenario-card" data-tone="${escapeHTML(s.tone)}">
        <div class="scenario-head"><span class="scenario-type">${escapeHTML(s.type)} CASE</span><span class="probability">${s.probability}%</span></div>
        <h3>${escapeHTML(s.title)}</h3>
        <ul>${s.conditions.map(c => `<li>${escapeHTML(c)}</li>`).join("")}</ul>
        <div class="scenario-result">${escapeHTML(s.result)}</div>
      </article>`).join("");
    $("#invalidationList").innerHTML = d.invalidation.map(x => `<li>${escapeHTML(x)}</li>`).join("");
  }

  function renderEvents(d) {
    $("#eventTimeline").innerHTML = d.events.map(e => `
      <article class="event-row">
        <div class="event-date">${escapeHTML(e.date)}</div>
        <div class="event-time">${escapeHTML(e.time)}</div>
        <div class="event-name">${escapeHTML(e.name)}</div>
        <div class="importance" aria-label="重要度 ${e.importance} 星">${stars(e.importance)}</div>
        <div class="event-watch">${escapeHTML(e.watch)}</div>
      </article>`).join("");
  }

  function renderAudit(d) {
    $("#freshnessGrid").innerHTML = d.freshness.map(f => `
      <div class="freshness-item" data-state="${escapeHTML(f.state)}">
        <span>${escapeHTML(f.name)}</span>
        <div class="freshness-date"><i class="state-dot"></i>${escapeHTML(f.date)}</div>
      </div>`).join("");
    $("#sourceList").innerHTML = DATA.sources.map(s => `
      <a class="source-link" href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">
        <span class="source-name">${escapeHTML(s.name)}</span><span class="source-tier">${escapeHTML(s.tier)}</span>
      </a>`).join("");
  }

  function renderTrend(values) {
    const svg = $("#scoreTrend");
    const w = 220, h = 64, pad = 5;
    const min = Math.min(...values) - 3, max = Math.max(...values) + 3;
    const pts = values.map((v, i) => {
      const x = pad + i * ((w - pad * 2) / Math.max(1, values.length - 1));
      const y = h - pad - ((v - min) / Math.max(1, max - min)) * (h - pad * 2);
      return [x, y];
    });
    const line = pts.map(p => p.join(",")).join(" ");
    const last = pts[pts.length - 1];
    svg.innerHTML = `
      <line x1="5" y1="58" x2="215" y2="58" stroke="var(--line)" stroke-width="1"/>
      <polyline points="${line}" fill="none" stroke="var(--accent)" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="${toneColor(values[values.length - 1] >= 45 ? "warn" : "bad")}" stroke="var(--surface)" stroke-width="2"/>`;
  }

  function syncURL() {
    const url = new URL(location.href);
    url.searchParams.set("mode", mode);
    history.replaceState(null, "", url);
  }

  function summaryText() {
    const d = getReport();
    return `${d.meta.title}\n綜合分數：${d.score}/100（${d.scoreLabel}）｜全球：${d.regime}\n\n${d.quickTake.map((x, i) => `${i + 1}. ${x}`).join("\n")}\n\n${location.href}`;
  }

  async function copyText(text, success = "已複製") {
    try {
      await navigator.clipboard.writeText(text);
      showToast(success);
    } catch {
      const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); showToast(success);
    }
  }

  function showToast(message) {
    const toast = $("#toast"); toast.textContent = message; toast.classList.add("show");
    clearTimeout(showToast._timer); showToast._timer = setTimeout(() => toast.classList.remove("show"), 1700);
  }

  function applyTheme(theme) {
    document.documentElement.classList.toggle("light", theme === "light");
    localStorage.setItem("tmr-theme", theme);
  }

  function bindEvents() {
    $$(".mode-btn").forEach(btn => btn.addEventListener("click", () => {
      mode = btn.dataset.mode; activeCategory = "全部"; newsQuery = ""; $("#newsSearch").value = ""; renderAll();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }));
    $("#newsSearch").addEventListener("input", (e) => { newsQuery = e.target.value; renderNews(getReport()); });
    $("#themeButton").addEventListener("click", () => applyTheme(document.documentElement.classList.contains("light") ? "dark" : "light"));
    $("#copySummaryButton").addEventListener("click", () => copyText(summaryText(), "30 秒摘要已複製"));
    $("#shareButton").addEventListener("click", async () => {
      const d = getReport();
      if (navigator.share) {
        try { await navigator.share({ title: d.meta.title, text: d.headline, url: location.href }); return; } catch {}
      }
      copyText(location.href, "網址已複製");
    });
    $("#printButton").addEventListener("click", () => window.print());

    const sections = $$(".section-anchor");
    const links = $$(".desktop-nav a");
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      links.forEach(a => a.classList.toggle("active", a.getAttribute("href") === `#${visible.target.id}`));
    }, { rootMargin: "-30% 0px -60% 0px", threshold: [0, .1, .5] });
    sections.forEach(s => observer.observe(s));
  }

  const savedTheme = localStorage.getItem("tmr-theme");
  if (savedTheme) applyTheme(savedTheme);
  else if (matchMedia("(prefers-color-scheme: light)").matches) applyTheme("light");

  bindEvents();
  renderAll();
})();
