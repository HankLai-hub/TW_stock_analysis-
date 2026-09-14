#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "global.json"
TZ = ZoneInfo("Asia/Taipei")

TREASURY_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
EIA_DAILY = "https://www.eia.gov/dnav/pet/PET_PRI_SPT_S1_D.htm"
FED_H10 = "https://www.federalreserve.gov/releases/h10/current/"
BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
FED_MONETARY_RSS = "https://www.federalreserve.gov/feeds/press_monetary.xml"
BLS_LATEST_RSS = "https://www.bls.gov/feed/bls_latest.rss"

USER_AGENT = "TW-Market-Radar/7.0 (+public research dashboard; official sources only)"


def now_taipei() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_taipei().isoformat(timespec="seconds")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def http_text(url: str, *, timeout: int = 30, accept: str = "text/html,application/xml,text/xml,*/*") -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        data = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
        return data.decode(charset, errors="replace")


def http_json(url: str, *, token: str | None = None, timeout: int = 30):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(url: str, payload: dict, *, timeout: int = 30):
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def to_float(value):
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s or s.upper() in {"N/A", "NA", "ND", "-", "--"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def fmt(value, digits=2):
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_treasury_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []
    for node in root.iter():
        if local_name(node.tag) != "properties":
            continue
        row = {}
        for child in list(node):
            row[local_name(child.tag)] = (child.text or "").strip()
        if row.get("NEW_DATE"):
            rows.append(row)
    rows.sort(key=lambda x: x.get("NEW_DATE", ""))
    return rows


def treasury_metric(row: dict, key: str):
    return to_float(row.get(key))


def fetch_treasury(out: dict) -> None:
    year = now_taipei().year
    nominal_url = f"{TREASURY_XML}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    real_url = f"{TREASURY_XML}?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}"
    try:
        rows = parse_treasury_feed(http_text(nominal_url, accept="application/xml,text/xml,*/*"))
        if len(rows) < 2:
            raise ValueError("Treasury nominal yield feed returned fewer than 2 rows")
        latest, prev = rows[-1], rows[-2]
        date = latest["NEW_DATE"][:10]
        for dest, key, label in [
            ("us2y", "BC_2YEAR", "2Y"),
            ("us10y", "BC_10YEAR", "10Y"),
            ("us30y", "BC_30YEAR", "30Y"),
        ]:
            v = treasury_metric(latest, key)
            p = treasury_metric(prev, key)
            if v is None:
                continue
            change_bps = (v - p) * 100 if p is not None else None
            out["macro"][dest] = {
                "value": v,
                "display": f"{v:.2f}%",
                "change": f"{change_bps:+.0f} bp" if change_bps is not None else "",
                "asOf": date,
                "source": "U.S. Treasury",
                "state": "official_daily",
            }
        y2 = treasury_metric(latest, "BC_2YEAR")
        y10 = treasury_metric(latest, "BC_10YEAR")
        if y2 is not None and y10 is not None:
            spread = (y10 - y2) * 100
            out["macro"]["spread2s10s"] = {
                "value": spread,
                "display": f"{spread:+.0f} bp",
                "change": "10Y - 2Y",
                "asOf": date,
                "source": "U.S. Treasury",
                "state": "official_daily",
            }
        out["sources"].append({"name": "U.S. Treasury yield curve", "status": "ok", "asOf": date})
    except Exception as exc:
        out["errors"].append({"source": "U.S. Treasury nominal yields", "message": str(exc)[:300]})

    try:
        rows = parse_treasury_feed(http_text(real_url, accept="application/xml,text/xml,*/*"))
        if not rows:
            raise ValueError("Treasury real yield feed returned no rows")
        latest = rows[-1]
        date = latest["NEW_DATE"][:10]
        v = treasury_metric(latest, "TC_10YEAR")
        if v is not None:
            out["macro"]["real10y"] = {
                "value": v,
                "display": f"{v:.2f}%",
                "change": "10Y real yield",
                "asOf": date,
                "source": "U.S. Treasury",
                "state": "official_daily",
            }
        out["sources"].append({"name": "U.S. Treasury real yields", "status": "ok", "asOf": date})
    except Exception as exc:
        out["errors"].append({"source": "U.S. Treasury real yields", "message": str(exc)[:300]})


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row = None
        self._cell = None
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._in_cell = True

    def handle_data(self, data):
        if self._in_cell and self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self._in_cell and self._row is not None:
            text = " ".join("".join(self._cell or []).split())
            self._row.append(unescape(text))
            self._cell = None
            self._in_cell = False
        elif tag == "tr" and self._row is not None:
            if any(x.strip() for x in self._row):
                self.rows.append(self._row)
            self._row = None


def parse_eia_daily(html: str) -> dict:
    parser = TableParser()
    parser.feed(html)
    rows = parser.rows
    date_re = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")
    header_dates = []
    for row in rows:
        dates = [x for cell in row for x in date_re.findall(cell)]
        if len(dates) >= 2:
            header_dates = dates
            break
    if not header_dates:
        raise ValueError("EIA daily date headers not recognized")

    def find_price(keyword: str):
        target = None
        for row in rows:
            if row and keyword.lower() in row[0].lower():
                target = row
                break
        if not target:
            raise ValueError(f"EIA row not found: {keyword}")
        nums = []
        for cell in target[1:]:
            v = to_float(cell)
            nums.append(v)
        # Keep the alignment from the right because the first cell is the row label.
        if len(nums) < len(header_dates):
            nums = [None] * (len(header_dates) - len(nums)) + nums
        elif len(nums) > len(header_dates):
            nums = nums[-len(header_dates):]
        pairs = [(d, v) for d, v in zip(header_dates, nums) if v is not None]
        if not pairs:
            raise ValueError(f"EIA values not found: {keyword}")
        return pairs[-1], pairs[-2] if len(pairs) >= 2 else (None, None)

    wti = find_price("WTI - Cushing")
    brent = find_price("Brent - Europe")
    return {"wti": wti, "brent": brent}


def fetch_eia(out: dict) -> None:
    try:
        parsed = parse_eia_daily(http_text(EIA_DAILY))
        for key in ("wti", "brent"):
            (date, value), (prev_date, prev) = parsed[key]
            change = (value / prev - 1) * 100 if prev else None
            # Convert EIA MM/DD/YY to ISO.
            dt = datetime.strptime(date, "%m/%d/%y")
            iso = dt.strftime("%Y-%m-%d")
            out["macro"][key] = {
                "value": value,
                "display": f"${value:.2f}",
                "change": f"{change:+.2f}%" if change is not None else "",
                "asOf": iso,
                "source": "U.S. EIA",
                "state": "official_daily",
            }
        latest_date = out["macro"].get("brent", {}).get("asOf") or out["macro"].get("wti", {}).get("asOf")
        out["sources"].append({"name": "U.S. EIA crude spot prices", "status": "ok", "asOf": latest_date})
    except Exception as exc:
        out["errors"].append({"source": "U.S. EIA crude spot prices", "message": str(exc)[:300]})


def fetch_fed_h10(out: dict) -> None:
    try:
        html = http_text(FED_H10)
        parser = TableParser()
        parser.feed(html)
        dates = []
        for row in parser.rows:
            hits = []
            for cell in row:
                hits.extend(re.findall(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2}\b", cell))
            if len(hits) >= 3:
                dates = hits
                break
        broad_row = None
        for row in parser.rows:
            text = " | ".join(row).upper()
            if "BROAD" in text and "JAN06=100" in text:
                broad_row = row
                break
        if not broad_row:
            raise ValueError("Fed H.10 broad dollar row not recognized")
        vals = [to_float(c) for c in broad_row]
        vals = [v for v in vals if v is not None and 50 <= v <= 200]
        if not vals:
            raise ValueError("Fed H.10 broad dollar values not recognized")
        value = vals[-1]
        prev = vals[-2] if len(vals) >= 2 else None
        change = (value / prev - 1) * 100 if prev else None
        out["macro"]["broadDollar"] = {
            "value": value,
            "display": f"{value:.2f}",
            "change": f"{change:+.2f}%" if change is not None else "",
            "asOf": dates[-1] if dates else "latest weekly H.10",
            "source": "Federal Reserve H.10",
            "state": "official_weekly",
        }
        out["sources"].append({"name": "Federal Reserve H.10 broad dollar", "status": "ok", "asOf": out["macro"]["broadDollar"]["asOf"]})
    except Exception as exc:
        out["errors"].append({"source": "Federal Reserve H.10 broad dollar", "message": str(exc)[:300]})


def month_key(item: dict):
    period = str(item.get("period") or "")
    year = str(item.get("year") or "")
    if not re.fullmatch(r"M(?:0[1-9]|1[0-2])", period) or not re.fullmatch(r"20\d{2}", year):
        return None
    return f"{year}-{period[1:]}"


def bls_series_map(series: dict) -> dict[str, float]:
    out = {}
    for item in series.get("data") or []:
        key = month_key(item)
        value = to_float(item.get("value"))
        if key and value is not None:
            out[key] = value
    return out


def prior_year_key(month: str) -> str | None:
    if not re.fullmatch(r"20\d{2}-\d{2}", month or ""):
        return None
    y, m = month.split("-")
    return f"{int(y)-1:04d}-{m}"


def sorted_months(m: dict[str, float]) -> list[str]:
    return sorted(m)


def fetch_bls(out: dict) -> None:
    series_ids = [
        "CUSR0000SA0",       # headline CPI SA
        "CUSR0000SA0L1E",   # core CPI SA
        "CUUR0000SA0",       # headline CPI NSA
        "CUUR0000SA0L1E",   # core CPI NSA
        "LNS14000000",       # unemployment rate
        "CES0000000001",     # total nonfarm payrolls, thousands
        "CES0500000003",     # average hourly earnings, dollars
    ]
    try:
        year = now_taipei().year
        payload = {"seriesid": series_ids, "startyear": str(year - 1), "endyear": str(year)}
        obj = post_json(BLS_API, payload)
        if obj.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(f"BLS API status: {obj.get('status')} {obj.get('message')}")
        series = {s.get("seriesID"): bls_series_map(s) for s in (obj.get("Results") or {}).get("series", [])}

        def latest(series_id):
            m = series.get(series_id) or {}
            keys = sorted_months(m)
            if not keys:
                return None, None, None
            k = keys[-1]
            prev = keys[-2] if len(keys) >= 2 else None
            return k, m[k], m.get(prev) if prev else None

        # CPI MoM from SA, YoY from NSA.
        for prefix, sa_id, nsa_id in [
            ("cpi", "CUSR0000SA0", "CUUR0000SA0"),
            ("coreCpi", "CUSR0000SA0L1E", "CUUR0000SA0L1E"),
        ]:
            month, current_sa, prev_sa = latest(sa_id)
            nsa = series.get(nsa_id) or {}
            current_nsa = nsa.get(month) if month else None
            py = nsa.get(prior_year_key(month)) if month else None
            mom = (current_sa / prev_sa - 1) * 100 if current_sa and prev_sa else None
            yoy = (current_nsa / py - 1) * 100 if current_nsa and py else None
            out["macro"][prefix] = {
                "value": yoy,
                "display": f"{yoy:.1f}% YoY" if yoy is not None else "N/A",
                "change": f"{mom:+.1f}% MoM" if mom is not None else "",
                "asOf": month or "N/A",
                "source": "U.S. BLS",
                "state": "official_monthly",
            }

        month, unemployment, _ = latest("LNS14000000")
        out["macro"]["unemployment"] = {
            "value": unemployment,
            "display": f"{unemployment:.1f}%" if unemployment is not None else "N/A",
            "change": "Unemployment rate",
            "asOf": month or "N/A",
            "source": "U.S. BLS",
            "state": "official_monthly",
        }

        month, payroll, payroll_prev = latest("CES0000000001")
        payroll_change = payroll - payroll_prev if payroll is not None and payroll_prev is not None else None
        out["macro"]["payrolls"] = {
            "value": payroll_change,
            "display": f"{payroll_change:+,.0f}k" if payroll_change is not None else "N/A",
            "change": "Nonfarm payroll monthly change",
            "asOf": month or "N/A",
            "source": "U.S. BLS",
            "state": "official_monthly",
        }

        month, ahe, ahe_prev = latest("CES0500000003")
        ahe_map = series.get("CES0500000003") or {}
        ahe_py = ahe_map.get(prior_year_key(month)) if month else None
        ahe_yoy = (ahe / ahe_py - 1) * 100 if ahe and ahe_py else None
        ahe_mom = (ahe / ahe_prev - 1) * 100 if ahe and ahe_prev else None
        out["macro"]["ahe"] = {
            "value": ahe_yoy,
            "display": f"{ahe_yoy:.1f}% YoY" if ahe_yoy is not None else "N/A",
            "change": f"{ahe_mom:+.1f}% MoM" if ahe_mom is not None else "",
            "asOf": month or "N/A",
            "source": "U.S. BLS",
            "state": "official_monthly",
        }
        out["sources"].append({"name": "U.S. BLS Public Data API", "status": "ok", "asOf": month})
    except Exception as exc:
        out["errors"].append({"source": "U.S. BLS macro data", "message": str(exc)[:300]})


def rss_items(xml_text: str, source: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for node in root.iter():
        if local_name(node.tag).lower() not in {"item", "entry"}:
            continue
        row = {}
        for child in list(node):
            name = local_name(child.tag).lower()
            if name in {"title", "link", "pubdate", "published", "updated", "description", "summary"}:
                if name == "link" and child.attrib.get("href"):
                    row[name] = child.attrib.get("href")
                else:
                    row[name] = " ".join((child.text or "").split())
        title = row.get("title") or ""
        link = row.get("link") or ""
        published = row.get("pubdate") or row.get("published") or row.get("updated") or ""
        if title:
            items.append({"source": source, "title": title, "link": link, "publishedRaw": published})
    return items


def parse_pubdate(value: str):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None


def classify_news(item: dict) -> dict:
    title = item.get("title", "")
    low = title.lower()
    source = item.get("source")
    category = "官方事件"
    impact = 3
    transmission = "先觀察利率、美元與風險偏好的實際反應。"

    if source == "Federal Reserve":
        category = "貨幣政策"
        impact = 5 if any(k in low for k in ["fomc", "federal funds", "monetary policy", "interest rate"]) else 4
        transmission = "主要透過美債殖利率、美元與科技股估值影響台股。"
    elif source == "U.S. BLS":
        if "consumer price" in low or "cpi" in low:
            category, impact = "通膨", 5
            transmission = "高於預期通常提高利率／美元壓力；低於預期則相反。"
        elif "employment situation" in low:
            category, impact = "就業", 5
            transmission = "就業強弱會改變 Fed 路徑與風險偏好，需搭配殖利率反應。"
        elif "producer price" in low:
            category, impact = "通膨", 4
            transmission = "主要影響上游通膨與利率預期，間接影響科技估值。"
        elif "job openings" in low or "jolts" in low:
            category, impact = "就業", 4
            transmission = "反映勞動需求與薪資壓力，需搭配 Fed 定價觀察。"
        else:
            category, impact = "美國景氣", 3
            transmission = "作為景氣與利率預期的背景訊號，不單獨決定台股方向。"

    dt = parse_pubdate(item.get("publishedRaw", ""))
    published = dt.astimezone(TZ).isoformat(timespec="minutes") if dt else item.get("publishedRaw", "")
    return {
        "source": source,
        "title": title,
        "link": item.get("link", ""),
        "publishedAt": published,
        "category": category,
        "impact": impact,
        "transmission": transmission,
        "_sort": dt.timestamp() if dt else 0,
    }


def fetch_official_news(out: dict) -> None:
    items = []
    try:
        fed = rss_items(http_text(FED_MONETARY_RSS, accept="application/rss+xml,application/xml,text/xml,*/*"), "Federal Reserve")
        items.extend(fed[:12])
        out["sources"].append({"name": "Federal Reserve monetary-policy RSS", "status": "ok", "asOf": iso_now()})
    except Exception as exc:
        out["errors"].append({"source": "Federal Reserve monetary-policy RSS", "message": str(exc)[:300]})
    try:
        bls = rss_items(http_text(BLS_LATEST_RSS, accept="application/rss+xml,application/xml,text/xml,*/*"), "U.S. BLS")
        keywords = ["consumer price", "producer price", "employment situation", "job openings", "jolts", "import and export price"]
        bls = [x for x in bls if any(k in x.get("title", "").lower() for k in keywords)]
        items.extend(bls[:12])
        out["sources"].append({"name": "U.S. BLS RSS", "status": "ok", "asOf": iso_now()})
    except Exception as exc:
        out["errors"].append({"source": "U.S. BLS RSS", "message": str(exc)[:300]})

    classified = [classify_news(x) for x in items]
    seen = set()
    unique = []
    for item in sorted(classified, key=lambda x: x.get("_sort", 0), reverse=True):
        key = (item.get("source"), item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        item.pop("_sort", None)
        unique.append(item)
    out["news"] = unique[:8]


def fetch_authorized_equity_feed(out: dict) -> None:
    url = os.environ.get("GLOBAL_EQUITY_FEED_URL", "").strip()
    token = os.environ.get("GLOBAL_EQUITY_FEED_TOKEN", "").strip() or None
    public = os.environ.get("GLOBAL_EQUITY_PUBLIC_DISPLAY", "").strip().upper() == "YES"
    names = {"sp500": "S&P 500", "nasdaq": "Nasdaq Composite", "sox": "SOX", "vix": "VIX"}
    if not url:
        out["equityFeed"] = {
            "state": "not_configured",
            "label": "全球股票指數授權源尚未設定",
            "note": "S&P 500／Nasdaq／SOX／VIX 為授權型指數；公開網站不以未授權來源重新散布。",
        }
        for key, name in names.items():
            out["equity"][key] = {"display": "N/A", "change": "", "asOf": "N/A", "source": name, "state": "authorization_required"}
        return
    if not public:
        out["equityFeed"] = {
            "state": "authorization_required",
            "label": "全球股票指數資料源已設定，但公開展示尚未啟用",
            "note": "確認資料供應商允許公開展示後，再設定 GLOBAL_EQUITY_PUBLIC_DISPLAY=YES。",
        }
        return
    try:
        obj = http_json(url, token=token)
        license_info = obj.get("license") if isinstance(obj, dict) and isinstance(obj.get("license"), dict) else {}
        if license_info.get("publicDisplay") is not True:
            raise ValueError("feed does not declare license.publicDisplay=true")
        metrics = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else {}
        vendor = str(license_info.get("vendor") or obj.get("source") or "Authorized global-market vendor")
        default_asof = str(obj.get("asOf") or obj.get("timestamp") or "N/A")
        for key, name in names.items():
            row = metrics.get(key)
            if not isinstance(row, dict):
                continue
            value = to_float(row.get("value"))
            change = to_float(row.get("changePercent", row.get("changePct")))
            if value is None:
                continue
            out["equity"][key] = {
                "value": value,
                "display": fmt(value, 2),
                "change": f"{change:+.2f}%" if change is not None else "",
                "asOf": str(row.get("asOf") or default_asof),
                "source": vendor,
                "state": "licensed_market_data",
            }
        out["equityFeed"] = {"state": "configured", "label": "已啟用授權全球股票指數", "note": vendor, "vendor": vendor}
        out["sources"].append({"name": "Authorized global equity feed", "status": "ok", "asOf": default_asof})
    except Exception as exc:
        out["equityFeed"] = {"state": "error", "label": "全球股票指數授權源錯誤", "note": str(exc)[:250]}
        out["errors"].append({"source": "Authorized global equity feed", "message": str(exc)[:300]})


def build_global_risk(out: dict) -> None:
    score = 50.0
    drivers = []
    usable = 0

    def m(key):
        return out.get("macro", {}).get(key) or {}

    y10 = to_float(m("us10y").get("value"))
    if y10 is not None:
        usable += 1
        if y10 >= 5.0:
            score -= 16; drivers.append({"name": "美債10Y", "direction": "negative", "reason": f"{y10:.2f}%：高折現率壓力"})
        elif y10 >= 4.7:
            score -= 10; drivers.append({"name": "美債10Y", "direction": "negative", "reason": f"{y10:.2f}%：偏不利科技估值"})
        elif y10 <= 4.0:
            score += 8; drivers.append({"name": "美債10Y", "direction": "positive", "reason": f"{y10:.2f}%：估值壓力較低"})

    real = to_float(m("real10y").get("value"))
    if real is not None:
        usable += 1
        if real >= 2.3:
            score -= 12; drivers.append({"name": "10Y實質利率", "direction": "negative", "reason": f"{real:.2f}%：長久期資產壓力"})
        elif real <= 1.5:
            score += 6; drivers.append({"name": "10Y實質利率", "direction": "positive", "reason": f"{real:.2f}%：估值環境改善"})

    brent = to_float(m("brent").get("value"))
    if brent is not None:
        usable += 1
        if brent >= 110:
            score -= 14; drivers.append({"name": "Brent", "direction": "negative", "reason": f"${brent:.0f}：再通膨風險高"})
        elif brent >= 100:
            score -= 9; drivers.append({"name": "Brent", "direction": "negative", "reason": f"${brent:.0f}：通膨壓力偏高"})
        elif brent <= 80:
            score += 5; drivers.append({"name": "Brent", "direction": "positive", "reason": f"${brent:.0f}：能源通膨壓力低"})

    cpi = to_float(m("cpi").get("value"))
    if cpi is not None:
        usable += 1
        if cpi >= 3.5:
            score -= 10; drivers.append({"name": "美國CPI", "direction": "negative", "reason": f"{cpi:.1f}% YoY：通膨偏高"})
        elif cpi <= 2.5:
            score += 6; drivers.append({"name": "美國CPI", "direction": "positive", "reason": f"{cpi:.1f}% YoY：接近政策目標"})

    score = max(0, min(100, round(score)))
    label = "Risk-On" if score >= 70 else ("偏多" if score >= 55 else ("Neutral" if score >= 45 else ("偏空" if score >= 30 else "Risk-Off")))
    out["risk"] = {
        "score": score if usable else None,
        "label": label if usable else "資料不足",
        "confidence": round(usable / 4 * 100),
        "drivers": drivers[:4],
        "note": "全球宏觀分數只使用美債、實質利率、能源與通膨；未將未授權的股價指數硬塞入模型。",
    }


def main():
    out = {
        "schemaVersion": 1,
        "generatedAt": iso_now(),
        "macro": {},
        "equity": {},
        "equityFeed": {},
        "news": [],
        "risk": {},
        "sources": [],
        "errors": [],
    }
    fetch_treasury(out)
    fetch_eia(out)
    fetch_fed_h10(out)
    fetch_bls(out)
    fetch_official_news(out)
    fetch_authorized_equity_feed(out)
    build_global_risk(out)
    write_json(OUT, out)
    print(f"✓ global.json generated · {len(out['errors'])} warning(s)")


if __name__ == "__main__":
    main()
