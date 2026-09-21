#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import ssl
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "intelligence.json"
TZ = ZoneInfo("Asia/Taipei")
UA = "TW-Market-Radar/8.0 (+public research dashboard; headline aggregation)"

OFFICIAL_FEEDS = [
    ("TWSE", "https://www.twse.com.tw/rwd/zh/news/feed?type=rss", "台股市場"),
    ("EU Council", "https://www.consilium.europa.eu/en/rss/pressreleases.ashx", "地緣政治"),
    ("ECB", "https://www.ecb.europa.eu/rss/press.html", "貨幣政策"),
    ("EIA Today in Energy", "https://www.eia.gov/rss/todayinenergy.xml", "能源"),
    ("EIA Press", "https://www.eia.gov/rss/press_rss.xml", "能源"),
]

DISCOVERY_QUERIES = [
    ("歐洲安全", 'NATO Europe defense readiness Russia Ukraine when:4d'),
    ("能源航運", 'oil shipping Strait Red Sea Middle East energy when:4d'),
    ("市場結構", 'Taiwan stock FTSE MSCI index rebalance closing volume when:7d'),
    ("半導體", 'Taiwan semiconductor AI export controls TSMC when:4d'),
    ("總體市場", 'Federal Reserve Treasury yields inflation stocks when:3d'),
]

KEYWORDS = {
    "地緣政治": ["nato", "defen", "military", "war", "ukraine", "russia", "missile", "drone", "sanction", "security", "兵", "軍", "戰", "防務"],
    "能源": ["oil", "brent", "wti", "energy", "opec", "lng", "shipping", "tanker", "strait", "crude", "天然氣", "油"],
    "市場結構": ["ftse", "msci", "rebalance", "rebalancing", "index review", "expiry", "expiration", "quadruple", "settlement", "結算", "換股", "調整"],
    "半導體": ["semiconductor", "chip", "tsmc", "nvidia", "ai", "export control", "foundry", "memory", "dram", "hbm", "半導體", "晶片"],
    "貨幣政策": ["central bank", "ecb", "boj", "federal reserve", "fomc", "interest rate", "monetary policy", "央行", "利率"],
    "台股市場": ["twse", "taiwan stock", "taiwan index", "台股", "證交所"],
}

HIGH_IMPACT = [
    "war", "attack", "missile", "drone", "nato", "interest rate", "fomc", "cpi", "employment",
    "export control", "sanction", "ftse", "msci", "rebalance", "settlement", "oil", "brent",
    "戰", "軍", "升息", "降息", "換股", "結算",
]


def now_local() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_local().isoformat(timespec="seconds")


def http_text(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,text/html,*/*"})
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None


def strip_html(s: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", s or "", flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(unescape(s).split())


def rss_items(xml: str, source: str, default_category: str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    # RSS
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc = strip_html(item.findtext("description") or "")
        pub = item.findtext("pubDate") or item.findtext("date") or ""
        dt = parse_dt(pub)
        if title:
            out.append({"source": source, "title": title, "link": link, "summary": desc, "publishedAt": dt.isoformat(timespec="minutes") if dt else pub, "category": default_category})
    # Atom
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns):
        title = strip_html(entry.findtext("a:title", default="", namespaces=ns))
        link_el = entry.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = strip_html(entry.findtext("a:summary", default="", namespaces=ns) or entry.findtext("a:content", default="", namespaces=ns))
        pub = entry.findtext("a:published", default="", namespaces=ns) or entry.findtext("a:updated", default="", namespaces=ns)
        dt = parse_dt(pub)
        if title:
            out.append({"source": source, "title": title, "link": link, "summary": summary, "publishedAt": dt.isoformat(timespec="minutes") if dt else pub, "category": default_category})
    return out


def classify(title: str, initial: str) -> tuple[str, int, str]:
    low = title.lower()
    category = initial
    for cat, words in KEYWORDS.items():
        if any(w in low for w in words):
            category = cat
            break
    impact = 5 if any(k in low for k in HIGH_IMPACT) else 3
    if category in {"地緣政治", "市場結構", "貨幣政策"}:
        impact = max(impact, 4)
    if category == "地緣政治":
        transmission = "觀察能源、航運、國防支出與全球風險溢酬，並追蹤美債與美元是否同步升溫。"
    elif category == "能源":
        transmission = "主要透過油價、通膨預期與美債殖利率影響高估值科技股。"
    elif category == "市場結構":
        transmission = "可能造成收盤集合競價、被動資金與權值股成交量異常；應與主動外資流向分開解讀。"
    elif category == "半導體":
        transmission = "影響台灣電子權值、AI 供應鏈與半導體風險偏好。"
    elif category == "貨幣政策":
        transmission = "主要透過利率、美元、殖利率曲線與科技股估值傳導至台股。"
    else:
        transmission = "先觀察市場價格、外資與匯率反應，不以單一新聞直接推導台股方向。"
    return category, impact, transmission


def normalize_item(item: dict, *, discovery: bool = False) -> dict:
    category, impact, transmission = classify(item.get("title", ""), item.get("category", "官方事件"))
    dt = parse_dt(item.get("publishedAt", ""))
    title = item.get("title", "").strip()
    return {
        "source": item.get("source") or "Unknown",
        "title": title,
        "link": item.get("link") or "",
        "publishedAt": dt.isoformat(timespec="minutes") if dt else item.get("publishedAt", ""),
        "category": category,
        "impact": impact,
        "fact": title,
        "reaction": "等待價格、殖利率、匯率或成交量驗證；系統不以標題自行推估已發生的市場反應。",
        "twImpact": transmission,
        "discovery": discovery,
        "verification": "背景資訊／需查核原始來源" if discovery else "官方來源",
        "_sort": dt.timestamp() if dt else 0,
    }


def fetch_google_discovery(query: str, label: str) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
    items = rss_items(http_text(url), f"Google News discovery · {label}", label)
    return items[:8]


def parse_extra_feeds() -> list[tuple[str, str, str]]:
    raw = os.environ.get("NEWS_EXTRA_RSS", "").strip()
    out = []
    if not raw:
        return out
    for part in raw.split(";"):
        bits = [x.strip() for x in part.split("|")]
        if len(bits) >= 2 and bits[0] and bits[1].startswith("http"):
            out.append((bits[0], bits[1], bits[2] if len(bits) >= 3 and bits[2] else "背景資訊"))
    return out


def build_calendar_events() -> list[dict]:
    now = now_local()
    events = []
    # TAIFEX monthly settlement: third Wednesday, factual calendar rule.
    for offset in range(0, 45):
        d = (now + timedelta(days=offset)).date()
        if d.weekday() == 2 and 15 <= d.day <= 21:
            events.append({
                "source": "TAIFEX",
                "title": "臺指期月契約結算週",
                "scheduledAt": f"{d.isoformat()}T13:30:00+08:00",
                "category": "市場結構",
                "impact": 4,
                "watch": "結算、轉倉與基差可能放大盤中／尾盤成交；請與方向性買賣分開解讀。",
                "link": "https://www.taifex.com.tw/",
            })
            break
    # U.S. quarterly index/futures expiry: third Friday of Mar/Jun/Sep/Dec.
    for offset in range(0, 60):
        d = (now + timedelta(days=offset)).date()
        if d.month in {3, 6, 9, 12} and d.weekday() == 4 and 15 <= d.day <= 21:
            events.append({
                "source": "CME / U.S. exchanges",
                "title": "美國季度股指衍生品到期週",
                "scheduledAt": f"{d.isoformat()}T16:00:00-04:00",
                "category": "市場結構",
                "impact": 4,
                "watch": "季度到期可能提高美股收盤附近成交與再平衡流量。",
                "link": "https://www.cmegroup.com/",
            })
            break
    return events


def main() -> None:
    out = {"schemaVersion": 2, "generatedAt": iso_now(), "news": [], "events": [], "sources": [], "errors": []}
    items = []

    for source, url, cat in OFFICIAL_FEEDS + parse_extra_feeds():
        try:
            rows = rss_items(http_text(url), source, cat)
            items.extend(normalize_item(x, discovery=False) for x in rows[:15])
            out["sources"].append({"name": source, "url": url, "status": "ok", "asOf": iso_now()})
        except Exception as exc:
            out["errors"].append({"source": source, "message": str(exc)[:300]})

    # Broad discovery is intentionally separated from official feeds. It is useful for
    # catching cross-border/geopolitical stories, but remains marked as needing source verification.
    if os.environ.get("NEWS_DISCOVERY_ENABLED", "YES").strip().upper() not in {"NO", "FALSE", "0"}:
        for label, query in DISCOVERY_QUERIES:
            try:
                rows = fetch_google_discovery(query, label)
                items.extend(normalize_item(x, discovery=True) for x in rows)
                out["sources"].append({"name": f"Google News discovery · {label}", "status": "ok", "asOf": iso_now()})
            except Exception as exc:
                out["errors"].append({"source": f"Google News discovery · {label}", "message": str(exc)[:300]})

    # Keep only recent headlines, deduplicate by normalized title.
    cutoff = now_local() - timedelta(days=10)
    seen = set()
    clean = []
    for row in sorted(items, key=lambda x: x.get("_sort", 0), reverse=True):
        dt = parse_dt(row.get("publishedAt", ""))
        if dt and dt < cutoff:
            continue
        key = re.sub(r"\W+", "", row.get("title", "").lower())[:180]
        if not key or key in seen:
            continue
        seen.add(key)
        row.pop("_sort", None)
        clean.append(row)
    out["news"] = clean[:36]
    out["events"] = build_calendar_events()
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} with {len(out['news'])} headlines, {len(out['errors'])} warnings")


if __name__ == "__main__":
    main()
