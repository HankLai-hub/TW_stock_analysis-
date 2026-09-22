#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Asia/Taipei")


def read_json(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(name, obj):
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def num(v):
    if v is None:
        return None
    m = re.search(r"[+-]?\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except Exception:
        return None


def metric(live, key):
    return (live.get("metrics") or {}).get(key) or {}


def display_metric(row, fallback="N/A"):
    v = row.get("display") if "display" in row else row.get("value")
    return str(v) if v not in (None, "") else fallback


def current_state(row, benchmark):
    asof = str(row.get("asOf") or "")
    if not asof or asof == "N/A":
        return "missing"
    if benchmark and re.fullmatch(r"\d{4}-\d{2}-\d{2}", benchmark) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof):
        return "latest" if asof >= benchmark else "stale"
    return "latest"


def freshness(live, global_data):
    benchmark = metric(live, "taiex").get("asOf")
    rows = []
    for label, key in [
        ("TAIEX", "taiex"), ("櫃買", "otc"), ("外資現貨", "foreignSpot"), ("外資 TX", "foreignTx"),
        ("Put/Call", "putCall"), ("USD/TWD", "usdTwd"), ("融資", "margin"), ("市場廣度", "breadth"), ("投信", "investmentTrust"), ("自營商", "dealer")
    ]:
        r = metric(live, key)
        rows.append({"name": label, "date": r.get("asOf") or "N/A", "state": current_state(r, benchmark), "source": r.get("source") or "N/A"})
    gm = global_data.get("macro") or {}
    for label, key in [("US 10Y", "us10y"), ("Brent", "brent"), ("美國 CPI", "cpi")]:
        r = gm.get(key) or {}
        rows.append({"name": label, "date": r.get("asOf") or "N/A", "state": "missing" if not r.get("asOf") or r.get("asOf") == "N/A" else "latest", "source": r.get("source") or "N/A"})
    eq = global_data.get("equity") or {}
    for label, key in [("S&P 500", "sp500"), ("Nasdaq", "nasdaq"), ("SOX", "sox")]:
        r = eq.get(key) or {}
        rows.append({"name": label, "date": r.get("asOf") or "N/A", "state": "missing" if r.get("state") == "authorization_required" or r.get("display") == "N/A" else "latest", "source": r.get("source") or "N/A"})
    return rows


def recent_closes(history, live):
    rows = []
    if isinstance(history, list):
        rows.extend(x for x in history if isinstance(x, dict))
    rows.append(live)
    by_day = {}
    for r in rows:
        m = r.get("metrics") or {}
        day = str((m.get("taiex") or {}).get("asOf") or "")
        val = num((m.get("taiex") or {}).get("value"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and val is not None:
            old = by_day.get(day)
            if old is None or str(r.get("generatedAt") or "") > old[0]:
                by_day[day] = (str(r.get("generatedAt") or ""), val)
    return [(d, by_day[d][1]) for d in sorted(by_day)][-20:]


def build_levels(live, history):
    cur = num(metric(live, "taiex").get("value"))
    closes = recent_closes(history, live)
    if cur is None:
        return {"current": None, "resistance": [{"label": "第一壓力", "price": "N/A", "strength": "N/A"}], "support": [{"label": "第一支撐", "price": "N/A", "strength": "N/A"}]}
    prior = [v for d, v in closes[:-1]]
    below = sorted({v for v in prior if v < cur}, reverse=True)
    above = sorted({v for v in prior if v > cur})
    support = []
    resistance = []
    if below:
        support.append({"label": "近20日收盤支撐", "price": f"{below[0]:,.2f}", "strength": "資料型"})
    if len(below) > 1:
        support.append({"label": "次支撐", "price": f"{below[1]:,.2f}", "strength": "資料型"})
    if above:
        resistance.append({"label": "近20日收盤壓力", "price": f"{above[0]:,.2f}", "strength": "資料型"})
    # The round-number line is explicitly analytical, not an observed market datum.
    round500 = math.ceil(cur / 500.0) * 500
    if not resistance or abs(round500 - cur) > 1:
        resistance.append({"label": "整數技術關卡", "price": f"{round500:,.0f}", "strength": "技術參考"})
    round_support = math.floor(cur / 500.0) * 500
    if not support or abs(round_support - cur) > 1:
        support.append({"label": "整數技術關卡", "price": f"{round_support:,.0f}", "strength": "技術參考"})
    return {"current": cur, "resistance": resistance[:3], "support": support[:3]}


def build_why_volume(live, history, intel):
    cur = num(metric(live, "turnover").get("value"))
    day = metric(live, "turnover").get("asOf") or metric(live, "taiex").get("asOf")
    vals = []
    if isinstance(history, list):
        by_day = {}
        for r in history:
            m = r.get("metrics") or {}
            d = str((m.get("turnover") or {}).get("asOf") or (m.get("taiex") or {}).get("asOf") or "")
            v = num((m.get("turnover") or {}).get("value"))
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and v is not None and d != day:
                by_day[d] = v
        vals = [by_day[k] for k in sorted(by_day)][-20:]
    ratio = None
    if cur is not None and len(vals) >= 5 and median(vals):
        ratio = cur / median(vals)
    candidates = []
    for e in intel.get("events") or []:
        sd = str(e.get("scheduledAt") or "")[:10]
        if day and sd and abs((datetime.fromisoformat(sd).date() - datetime.fromisoformat(day).date()).days) <= 1:
            candidates.append(e)
    for n in intel.get("news") or []:
        if n.get("category") == "市場結構" and str(n.get("publishedAt") or "")[:10] in {day, ""}:
            candidates.append({"title": n.get("title"), "source": n.get("source"), "link": n.get("link")})
    abnormal = ratio is not None and ratio >= 1.30
    if abnormal and candidates:
        status = "explained_candidate"
        label = "成交量異常，且有市場結構事件可交叉驗證"
        confidence = "中高"
    elif abnormal:
        status = "unexplained"
        label = "成交量異常；原因尚未取得足夠證據"
        confidence = "N/A"
    elif ratio is not None:
        status = "normal"
        label = "成交量未達 20 日中位數 1.3 倍異常門檻"
        confidence = "資料型"
    else:
        status = "insufficient"
        label = "歷史成交值不足，暫不判定異常"
        confidence = "N/A"
    return {
        "status": status,
        "date": day or "N/A",
        "turnover": metric(live, "turnover").get("value") or "N/A",
        "ratioTo20dMedian": round(ratio, 2) if ratio is not None else None,
        "label": label,
        "confidence": confidence,
        "candidates": candidates[:5],
        "note": "僅在成交值異常且存在可驗證市場結構事件時提供原因候選；無證據時維持 N/A，不把相關性當因果。",
    }


def make_global(live, g):
    eq = g.get("equity") or {}
    macro = g.get("macro") or {}
    cards = []
    for name, key in [("S&P 500", "sp500"), ("Nasdaq", "nasdaq"), ("SOX", "sox")]:
        r = eq.get(key) or {}
        cards.append({"name": name, "value": r.get("display") or "N/A", "change": r.get("change") or ("授權資料源未設定" if r.get("state") == "authorization_required" else ""), "tone": "neutral" if r.get("display") in {None, "N/A"} else ("good" if str(r.get("change", "")).startswith("+") else "bad"), "note": f"資料日 {r.get('asOf') or 'N/A'}"})
    y10 = macro.get("us10y") or {}
    brent = macro.get("brent") or {}
    twd = metric(live, "usdTwd")
    cards += [
        {"name": "US 10Y", "value": y10.get("display") or "N/A", "change": y10.get("change") or "", "tone": "bad" if (num(y10.get("value")) or 0) >= 5 else "neutral", "note": f"{y10.get('source') or 'N/A'} · {y10.get('asOf') or 'N/A'}"},
        {"name": "Brent", "value": brent.get("display") or "N/A", "change": brent.get("change") or "", "tone": "bad" if (num(brent.get("value")) or 0) >= 100 else "neutral", "note": f"{brent.get('source') or 'N/A'} · {brent.get('asOf') or 'N/A'}"},
        {"name": "USD/TWD", "value": twd.get("value") or "N/A", "change": twd.get("change") or "", "tone": "neutral", "note": f"{twd.get('source') or 'N/A'} · {twd.get('asOf') or 'N/A'}"},
    ]
    return cards


def build_focus(live, g):
    macro = g.get("macro") or {}
    rows = [
        ("Brent 原油", macro.get("brent") or {}, "油價影響通膨預期、Fed 路徑與科技估值。", "油價快速突破/跌破近期區間，且 10Y 同向變動。"),
        ("美國 10Y", macro.get("us10y") or {}, "長天期殖利率是高估值科技股的重要折現率變數。", "有效跌回 5% 下或進一步上行，需同步重估估值壓力。"),
        ("外資 TX 淨部位", metric(live, "foreignTx"), "直接觀察外資期貨避險／方向性曝險。", "連續兩日明顯減空或重新擴空，且與現貨同向。"),
        ("外資現貨", metric(live, "foreignSpot"), "現貨方向可確認外資是否真正增加台股曝險。", "連續 3 日同方向且規模擴大。"),
        ("USD/TWD", metric(live, "usdTwd"), "匯率可驗證外資資金流是否伴隨真正資金進出。", "快速升破／跌破近期區間，並與外資現貨同向。"),
    ]
    out = []
    for i, (name, r, why, trigger) in enumerate(rows, 1):
        out.append({"rank": i, "name": name, "value": display_metric(r), "tone": "neutral", "why": why, "trigger": trigger + f"｜資料日 {r.get('asOf') or 'N/A'}"})
    return out


def merge_news(g, intel):
    rows = []
    for x in intel.get("news") or []:
        rows.append({"category": x.get("category") or "背景資訊", "time": str(x.get("publishedAt") or "N/A").replace("T", " ")[:16], "impact": int(x.get("impact") or 3), "title": x.get("title") or "N/A", "fact": x.get("fact") or x.get("title") or "N/A", "reaction": x.get("reaction") or "N/A", "twImpact": x.get("twImpact") or "N/A", "sourceKeys": [], "source": x.get("source") or "N/A", "link": x.get("link") or "", "verification": x.get("verification") or "N/A"})
    for x in g.get("news") or []:
        rows.append({"category": x.get("category") or "官方事件", "time": str(x.get("publishedAt") or "N/A").replace("T", " ")[:16], "impact": int(x.get("impact") or 3), "title": x.get("title") or "N/A", "fact": x.get("title") or "N/A", "reaction": "等待市場價格、殖利率與美元反應驗證。", "twImpact": x.get("transmission") or "N/A", "sourceKeys": [], "source": x.get("source") or "N/A", "link": x.get("link") or "", "verification": "官方來源"})
    seen, out = set(), []
    for x in sorted(rows, key=lambda z: z.get("time", ""), reverse=True):
        k = re.sub(r"\W+", "", x.get("title", "").lower())[:160]
        if not k or k in seen:
            continue
        seen.add(k); out.append(x)
    return out[:30]


def build_flow(live):
    f=metric(live,"foreignSpot"); t=metric(live,"investmentTrust"); d=metric(live,"dealer")
    return {"headers":["法人","最新","資料日","來源"],"rows":[
        ["外資",f.get("value") or "N/A",f.get("asOf") or "N/A",f.get("source") or "N/A"],
        ["投信",t.get("value") or "N/A",t.get("asOf") or "N/A",t.get("source") or "N/A"],
        ["自營商",d.get("value") or "N/A",d.get("asOf") or "N/A",d.get("source") or "N/A"],
    ]}


def build_derivatives(live):
    taiex = metric(live, "taiex"); tx = metric(live, "tx"); ftx = metric(live, "foreignTx"); pc = metric(live, "putCall")
    basis = None
    if taiex.get("asOf") == tx.get("asOf"):
        a, b = num(taiex.get("value")), num(tx.get("value"))
        if a is not None and b is not None:
            basis = b - a
    return [
        {"label": "外資 TX 淨部位", "value": ftx.get("value") or "N/A", "note": f"{ftx.get('change') or ''} · {ftx.get('asOf') or 'N/A'}", "tone": "bad" if (num(ftx.get("value")) or 0) < 0 else "good"},
        {"label": "TX", "value": tx.get("value") or "N/A", "note": f"{tx.get('change') or ''} · {tx.get('asOf') or 'N/A'}", "tone": "neutral"},
        {"label": "期現貨基差", "value": f"{basis:+,.2f} 點" if basis is not None else "N/A", "note": "僅在 TX 與現貨資料日相同時自動計算。", "tone": "neutral"},
        {"label": "Put/Call", "value": pc.get("value") or "N/A", "note": f"{pc.get('change') or ''} · {pc.get('asOf') or 'N/A'}", "tone": "neutral"},
    ]


def build_leverage(live):
    twd = metric(live, "usdTwd"); mar = metric(live, "margin")
    return [
        {"label": "USD/TWD", "value": twd.get("value") or "N/A", "note": f"{twd.get('source') or 'N/A'} · {twd.get('asOf') or 'N/A'}", "tone": "neutral"},
        {"label": "融資", "value": mar.get("value") or "N/A", "note": f"{mar.get('change') or ''} · {mar.get('asOf') or 'N/A'}", "tone": "neutral"},
        {"label": "借券／融券", "value": "N/A", "note": "尚未納入標準化 live schema；不沿用靜態舊值。", "tone": "neutral"},
    ]


def build_breadth(live):
    r = metric(live, "breadth")
    m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", str(r.get("value") or ""))
    up = int(m.group(1).replace(",", "")) if m else 0
    down = int(m.group(2).replace(",", "")) if m else 0
    return {"advancers": up, "decliners": down, "taiexChange": metric(live, "taiex").get("change") or "N/A", "otcChange": metric(live, "otc").get("change") or "N/A", "note": f"最新官方完整交易日 {r.get('asOf') or 'N/A'}。"}


def build_sectors(secdata):
    rows=[]
    for x in secdata.get("sectors") or []:
        p=x.get("priceChangePct"); f=x.get("foreignYi"); t=x.get("trustYi"); d=x.get("dealerYi")
        if all(v is None for v in (p,f,t,d)):
            rows.append({"name":x.get("name"),"direction":"N/A","score":None,"tone":"neutral","priceChange":"N/A","flow":"N/A","desc":"官方資料尚未取得；不以 0/100 冒充弱勢。"}); continue
        direction=(f"{p:+.2f}%" if isinstance(p,(int,float)) else "價格 N/A")
        vals=[v for v in (f,t,d) if isinstance(v,(int,float))]; flow=sum(vals) if vals else None
        tone="good" if (p or 0)>0 else ("bad" if (p or 0)<0 else "neutral")
        desc="；".join([z for z in [f"外資 {f:+.2f} 億" if isinstance(f,(int,float)) else "",f"投信 {t:+.2f} 億" if isinstance(t,(int,float)) else "",f"自營商 {d:+.2f} 億" if isinstance(d,(int,float)) else ""] if z]) or "法人產業資料 N/A"
        rows.append({"name":x.get("name"),"direction":direction,"score":None,"tone":tone,"priceChange":direction,"flow":f"{flow:+.2f} 億" if flow is not None else "N/A","desc":desc})
    return rows

def scenarios(score, live, g):
    s = float(score or 50)
    bull = max(10, min(70, round((s - 35) * 1.1)))
    bear = max(10, min(70, round((65 - s) * 1.1)))
    base = 100 - bull - bear
    if base < 20:
        base = 20
        total = bull + bear
        if total:
            scale = 80 / total
            bull, bear = round(bull * scale), 80 - round(bull * scale)
    return [
        {"type": "BULL", "weight": bull, "title": "風險條件改善", "tone": "good", "conditions": ["外資現貨維持買方", "外資 TX 淨空持續下降", "美10Y／油價未同步惡化"], "result": "條件式風險權重，不是未來報酬機率。"},
        {"type": "BASE", "weight": base, "title": "高檔震盪／訊號分歧", "tone": "warn", "conditions": ["本地資金與全球宏觀訊號分歧", "市場廣度維持中性以上", "重大事件未形成新衝擊"], "result": "優先追蹤資料變化，不用單一新聞預測方向。"},
        {"type": "BEAR", "weight": bear, "title": "風險條件惡化", "tone": "bad", "conditions": ["外資現貨轉賣且 TX 加空", "台幣轉弱", "美10Y／油價同步走高"], "result": "條件成立時提高風險警戒。"},
    ]


def main():
    live = read_json("live.json", {})
    g = read_json("global.json", {})
    auto = read_json("auto-brief.json", {}).get("daily") or {}
    intel = read_json("intelligence.json", {})
    secdata = read_json("sector-v22.json", {})
    hist = read_json("live-history.json", [])

    tw_date = metric(live, "taiex").get("asOf") or "N/A"
    equity_dates = [str((g.get("equity", {}).get(k) or {}).get("asOf") or "") for k in ("sp500", "nasdaq", "sox")]
    equity_dates = [x for x in equity_dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)]
    us_date = max(equity_dates) if equity_dates else (g.get("macro", {}).get("us10y") or {}).get("asOf") or "N/A"
    score = (live.get("risk") or {}).get("score")
    if not isinstance(score, (int, float)):
        score = auto.get("score") if isinstance(auto.get("score"), (int, float)) else 50
    label = (live.get("risk") or {}).get("label") or auto.get("label") or "Neutral"
    global_label = (g.get("risk") or {}).get("label") or "N/A"

    f = freshness(live, g)
    stale = sum(1 for x in f if x["state"] == "stale")
    missing = sum(1 for x in f if x["state"] == "missing")
    status = "自動日報｜Single Source of Truth"
    if stale or missing:
        status += f"｜{stale} stale / {missing} N/A"

    why = build_why_volume(live, hist, intel)
    themes = [
        {"rank": 1, "tone": "bad" if global_label in {"Risk-Off", "偏空"} else "warn", "weight": "高權重", "title": "全球金融條件與能源風險", "chain": ["美債 / 油價", "通膨預期", "折現率", "科技估值"], "thesis": (g.get("reaction") or {}).get("note") or "全球宏觀資料不足時維持 N/A。", "watch": "US 10Y、Brent、美元與重大地緣事件是否同向。"},
        {"rank": 2, "tone": "good" if num(metric(live, "foreignSpot").get("value")) and num(metric(live, "foreignSpot").get("value")) > 0 else "warn", "weight": "高權重", "title": "外資現貨 × 期貨曝險", "chain": ["現貨", "TX 淨部位", "USD/TWD", "市場廣度"], "thesis": f"外資現貨 {metric(live, 'foreignSpot').get('value') or 'N/A'}；外資 TX {metric(live, 'foreignTx').get('value') or 'N/A'}。", "watch": "需觀察現貨與期貨是否連續同向，而不是只看單日。"},
        {"rank": 3, "tone": "warn", "weight": "中權重", "title": "市場結構與異常成交量", "chain": ["成交值", "指數調整 / 結算", "被動資金", "尾盤波動"], "thesis": why.get("label") or "N/A", "watch": "若成交值異常，先檢查 FTSE/MSCI/結算/ETF 再平衡，再判讀主動買賣。"},
    ]

    dashboard = {
        "schemaVersion": "2.2",
        "generatedAt": live.get("generatedAt") or g.get("generatedAt") or datetime.now(TZ).isoformat(timespec="seconds"),
        "meta": {"reportType": "每日盤前分析", "title": f"{datetime.now(TZ).strftime('%Y/%m/%d')} 台股盤前作戰儀表板", "updatedAt": datetime.now(TZ).strftime("%Y/%m/%d %H:%M"), "timezone": "Asia/Taipei", "twDate": tw_date, "usDate": us_date, "dataStatus": status},
        "score": round(float(score), 1), "scoreLabel": label, "confidence": f"{(live.get('risk') or {}).get('confidence', 0)}%", "regime": global_label,
        "headline": auto.get("headline") or "自動資料已更新；缺漏項目維持 N/A，不再沿用舊日報數字。",
        "quickTake": auto.get("quickTake") or ["資料不足項目維持 N/A。"],
        "kpis": [
            {"label": "全球環境", "value": global_label, "tone": "bad" if global_label == "Risk-Off" else "warn", "note": (g.get("reaction") or {}).get("label") or "N/A"},
            {"label": "台股風險分數", "value": f"{float(score):.1f}", "tone": "good" if score >= 55 else ("warn" if score >= 45 else "bad"), "note": label},
            {"label": "外資現貨", "value": metric(live, "foreignSpot").get("value") or "N/A", "tone": "neutral", "note": metric(live, "foreignSpot").get("asOf") or "N/A"},
            {"label": "外資 TX", "value": metric(live, "foreignTx").get("value") or "N/A", "tone": "neutral", "note": metric(live, "foreignTx").get("asOf") or "N/A"},
            {"label": "市場廣度", "value": metric(live, "breadth").get("value") or "N/A", "tone": "neutral", "note": metric(live, "breadth").get("asOf") or "N/A"},
            {"label": "資料稽核", "value": "OK" if stale == 0 else "STALE", "tone": "good" if stale == 0 else "bad", "note": f"N/A {missing} 項"},
        ],
        "marketThemes": themes,
        "global": make_global(live, g),
        "focus": build_focus(live, g),
        "news": merge_news(g, intel),
        "flow": build_flow(live),
        "derivatives": build_derivatives(live),
        "leverage": build_leverage(live),
        "breadth": build_breadth(live),
        "levels": build_levels(live, hist),
        "sectors": build_sectors(secdata),
        "scenarios": scenarios(score, live, g),
        "invalidation": auto.get("invalidation") or ["外資現貨與 TX 同步惡化。", "市場廣度跌破 40%。", "全球利率／能源風險同步升高。"],
        "events": sorted((g.get("events") or []) + (intel.get("events") or []), key=lambda x: x.get("scheduledAt", ""))[:16],
        "freshness": f,
        "whyVolume": why,
        "diagnostics": {"stale": stale, "missing": missing, "globalErrors": g.get("errors") or [], "intelligenceErrors": intel.get("errors") or []},
        "sources": [
            {"key": "TWSE", "name": "臺灣證券交易所", "tier": "官方", "url": "https://www.twse.com.tw/"},
            {"key": "TPEx", "name": "證券櫃檯買賣中心", "tier": "官方", "url": "https://www.tpex.org.tw/"},
            {"key": "TAIFEX", "name": "臺灣期貨交易所", "tier": "官方", "url": "https://www.taifex.com.tw/"},
            {"key": "CBC", "name": "中央銀行", "tier": "官方", "url": "https://www.cbc.gov.tw/"},
            {"key": "FED", "name": "Federal Reserve", "tier": "官方", "url": "https://www.federalreserve.gov/"},
            {"key": "BLS", "name": "U.S. Bureau of Labor Statistics", "tier": "官方", "url": "https://www.bls.gov/"},
            {"key": "EU", "name": "European Council / EU Council", "tier": "官方", "url": "https://www.consilium.europa.eu/"},
            {"key": "ECB", "name": "European Central Bank", "tier": "官方", "url": "https://www.ecb.europa.eu/"},
            {"key": "EIA", "name": "U.S. Energy Information Administration", "tier": "官方", "url": "https://www.eia.gov/"},
        ],
    }
    write_json("daily-dashboard.json", dashboard)
    print("wrote data/daily-dashboard.json")


if __name__ == "__main__":
    main()
