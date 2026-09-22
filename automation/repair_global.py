#!/usr/bin/env python3
from __future__ import annotations

"""TW Market Radar V2.2.1 global-data repair hotfix.

Fixes
- FRED requests are single-series, recent-window, retry/backoff requests.
- Brent/WTI fallback remains dated and explicit.
- S&P 500 / Nasdaq fallback can use FRED with an opt-out switch.
- SOX uses Nasdaq Global Indexes official page.
- FOMC parsing is constrained to the *actual current-year section* and fails
  closed: if the official current-year section cannot be validated, synthetic
  FOMC events are removed instead of leaving false dates on the dashboard.
"""

import csv
import io
import json
import os
import re
import ssl
import time
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "global.json"
TZ = ZoneInfo("Asia/Taipei")
ET = ZoneInfo("America/New_York")
UA = "TW-Market-Radar/2.2.1 global-repair"
FRED_GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SOX_URL = "https://indexes.nasdaq.com/Index/Overview/SOX"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


def load():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(obj):
    PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def add_error(out, source, message):
    rows = out.setdefault("errors", [])
    rows[:] = [e for e in rows if e.get("source") != source]
    rows.append({"source": source, "message": str(message)[:400]})


def clear_error(out, *sources):
    out["errors"] = [e for e in out.get("errors", []) if e.get("source") not in set(sources)]


def upsert_source(out, name, status, as_of="N/A", detail=""):
    rows = out.setdefault("sources", [])
    rows[:] = [x for x in rows if x.get("name") != name]
    rows.append({"name": name, "status": status, "asOf": as_of, "detail": str(detail)[:320]})


def http_text(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,text/html,application/json,*/*"})
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def retry_text(url: str, attempts=3) -> str:
    last = None
    timeouts = [15, 25, 40]
    for i in range(attempts):
        try:
            return http_text(url, timeout=timeouts[min(i, len(timeouts) - 1)])
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(2 + i * 2)
    raise last or RuntimeError("request failed")


def to_float(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("−", "-").strip()
    if s in {"", ".", "N/A", "--", "---"}:
        return None
    try:
        return float(s)
    except Exception:
        m = re.search(r"[+-]?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None


def fred_latest(series: str, lookback_days: int = 75):
    end = datetime.now(TZ).date()
    start = end - timedelta(days=lookback_days)
    url = FRED_GRAPH + "?" + urlencode({"id": series, "cosd": start.isoformat(), "coed": end.isoformat()})
    text = retry_text(url)
    rows = list(csv.DictReader(io.StringIO(text)))
    vals = []
    for row in rows:
        d = str(row.get("DATE") or row.get("observation_date") or "")
        v = to_float(row.get(series))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and v is not None:
            vals.append((d, v))
    if not vals:
        raise ValueError(f"FRED {series}: no numeric observations in recent window")
    return vals[-1], (vals[-2] if len(vals) >= 2 else None)


def fred_metric(series: str, source: str):
    (date, value), prev = fred_latest(series)
    change = ""
    if prev and prev[1] not in (None, 0):
        change = f"{(value / prev[1] - 1) * 100:+.2f}%"
    return {
        "value": value,
        "display": f"{value:,.2f}",
        "change": change,
        "asOf": date,
        "source": source,
        "state": "official_secondary",
    }


def fallback_oil(out):
    macro = out.setdefault("macro", {})
    successes = []
    for key, series, label in (
        ("brent", "DCOILBRENTEU", "Brent"),
        ("wti", "DCOILWTICO", "WTI"),
    ):
        try:
            row = fred_metric(series, f"U.S. EIA via FRED {series}")
            row["display"] = f"${row['value']:.2f}"
            existing = macro.get(key) or {}
            old_date = str(existing.get("asOf") or "")
            if not old_date or row["asOf"] >= old_date or existing.get("value") in (None, "", "N/A"):
                macro[key] = row
            successes.append(f"{label} {row['asOf']}")
        except Exception as exc:
            add_error(out, f"FRED {label} fallback", exc)

    if successes:
        upsert_source(out, "FRED EIA crude-oil fallback V2.2.1", "ok", max((macro.get("brent") or {}).get("asOf", ""), (macro.get("wti") or {}).get("asOf", "")), "; ".join(successes))
        clear_error(out, "U.S. EIA crude spot prices", "FRED EIA crude-oil fallback")


def clean_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def fallback_equity(out):
    eq = out.setdefault("equity", {})
    enabled = os.environ.get("FRED_EQUITY_FALLBACK", "YES").strip().upper() not in {"NO", "FALSE", "0", "OFF"}
    out["fredEquityFallback"] = {
        "enabled": enabled,
        "note": "V2.2.1 single-series recent-window fallback. Set FRED_EQUITY_FALLBACK=NO to keep S&P/Nasdaq as N/A.",
    }

    if enabled:
        for key, series, source in (
            ("sp500", "SP500", "FRED SP500"),
            ("nasdaq", "NASDAQCOM", "FRED NASDAQCOM"),
        ):
            try:
                eq[key] = fred_metric(series, source)
                clear_error(out, f"FRED {key} fallback", "FRED equity fallback")
            except Exception as exc:
                add_error(out, f"FRED {key} fallback", exc)

    # Nasdaq official SOX page. Only accept a dated observation.
    try:
        html = retry_text(SOX_URL)
        txt = clean_text(html)
        m = re.search(r"DATA AS OF\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+(?:\.\d+)?)\s+([+-]?[\d,]+(?:\.\d+)?)\s+([+-]?[\d.]+)%", txt, re.I)
        if m:
            dt = datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat()
            v = float(m.group(2).replace(",", ""))
            pct = float(m.group(4))
        else:
            mdate = re.search(r"SOX\s+(\d{1,2}/\d{1,2}/\d{4})", txt, re.I)
            ml = re.search(r"Last\s+([\d,]+(?:\.\d+)?)\s+Net Change\s+([+-]?[\d,]+(?:\.\d+)?)", txt, re.I)
            if not (mdate and ml):
                raise ValueError("Nasdaq SOX dated value not found")
            dt = datetime.strptime(mdate.group(1), "%m/%d/%Y").date().isoformat()
            v = float(ml.group(1).replace(",", ""))
            net = float(ml.group(2).replace(",", ""))
            prev = v - net
            pct = (net / prev * 100) if prev else None
        eq["sox"] = {
            "value": v,
            "display": f"{v:,.2f}",
            "change": f"{pct:+.2f}%" if pct is not None else "",
            "asOf": dt,
            "source": "Nasdaq Global Indexes (SOX)",
            "state": "official",
        }
        clear_error(out, "Nasdaq SOX official fallback")
    except Exception as exc:
        add_error(out, "Nasdaq SOX official fallback", exc)


def purge_fomc(out):
    out["events"] = [
        e for e in out.get("events", [])
        if not (e.get("source") == "Federal Reserve" and "FOMC" in str(e.get("title") or e.get("name") or ""))
    ]


def _parse_meetings(segment: str, year: int):
    months = {m: i for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ], 1)}
    pattern = re.compile(
        r"\b(" + "|".join(months) + r")\b\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\*?",
        re.I,
    )
    meetings = []
    seen = set()
    for mm in pattern.finditer(segment):
        mname = mm.group(1).title()
        mnum = months[mname]
        d1 = int(mm.group(2))
        d2 = int(mm.group(3) or d1)
        try:
            datetime(year, mnum, d1)
            datetime(year, mnum, d2)
        except ValueError:
            continue
        key = (mnum, d1, d2)
        if key in seen:
            continue
        seen.add(key)
        meetings.append((mnum, mname, d1, d2))
    meetings.sort()
    return meetings


def _current_year_segment(text: str, year: int):
    heading = re.compile(rf"\b{year}\s+FOMC\s+Meetings?\b", re.I)
    starts = [m.start() for m in heading.finditer(text)]
    if not starts:
        raise ValueError(f"current-year FOMC heading not found for {year}")

    all_year_headings = list(re.finditer(r"\b(20\d{2})\s+FOMC\s+Meetings?\b", text, re.I))
    candidates = []
    for start in starts:
        later = [m.start() for m in all_year_headings if m.start() > start and int(m.group(1)) != year]
        end = min(later) if later else min(len(text), start + 6000)
        seg = text[start:end]
        meetings = _parse_meetings(seg, year)
        # A normal annual calendar has roughly eight meetings. Require a sane
        # count to avoid accidentally parsing a nav/menu or another year's list.
        if 6 <= len(meetings) <= 10:
            candidates.append((len(meetings), seg, meetings))

    if not candidates:
        raise ValueError("no validated current-year FOMC section (expected 6-10 meetings)")
    # Prefer the candidate with the most recognized unique meetings.
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def repair_fomc(out):
    now = datetime.now(TZ)
    horizon = now + timedelta(days=240)
    text = clean_text(retry_text(FOMC_URL))
    year = now.year
    _, meetings = _current_year_segment(text, year)

    fed_events = []
    for mnum, mname, d1, d2 in meetings:
        et = datetime(year, mnum, d2, 14, 0, tzinfo=ET)
        local = et.astimezone(TZ)
        if now <= local <= horizon:
            date_label = f"{mname} {d1}" + (f"–{d2}" if d2 != d1 else "")
            fed_events.append({
                "source": "Federal Reserve",
                "title": f"FOMC 利率決策（{date_label}）",
                "scheduledAt": local.isoformat(timespec="minutes"),
                "category": "貨幣政策",
                "impact": 5,
                "watch": "政策利率、SEP／Dot Plot（若有）、記者會語氣與美債殖利率。",
                "link": FOMC_URL,
                "verification": "Federal Reserve official calendar / current-year section",
            })

    # Replace *all* old Fed FOMC items with the verified current-year list.
    purge_fomc(out)
    uniq = {}
    for e in (out.get("events") or []) + fed_events:
        uniq[(e.get("source"), e.get("title"), e.get("scheduledAt"))] = e
    out["events"] = sorted(uniq.values(), key=lambda x: x.get("scheduledAt", ""))[:30]
    upsert_source(out, "Federal Reserve FOMC calendar V2.2.1", "ok", now.date().isoformat(), f"validated {len(meetings)} meetings in {year} section")
    clear_error(out, "Federal Reserve FOMC calendar repair")


def main():
    out = load()
    if not isinstance(out, dict):
        out = {}

    try:
        fallback_oil(out)
    except Exception as exc:
        add_error(out, "FRED oil fallback V2.2.1", exc)

    try:
        fallback_equity(out)
    except Exception as exc:
        add_error(out, "Equity fallback V2.2.1", exc)

    try:
        repair_fomc(out)
    except Exception as exc:
        # False calendar dates are worse than N/A. Fail closed.
        purge_fomc(out)
        add_error(out, "Federal Reserve FOMC calendar repair", exc)
        upsert_source(out, "Federal Reserve FOMC calendar V2.2.1", "error", datetime.now(TZ).date().isoformat(), "FOMC events removed because the official current-year section could not be validated")

    out["v221"] = {"repairedAt": datetime.now(TZ).isoformat(timespec="seconds"), "version": "2.2.1"}
    save(out)
    print("V2.2.1 repaired", PATH)


if __name__ == "__main__":
    main()
