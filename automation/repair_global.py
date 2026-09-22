#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import ssl
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "global.json"
TZ = ZoneInfo("Asia/Taipei")
UA = "TW-Market-Radar/8.0 global repair"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU,DCOILWTICO"
FRED_EQ = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500,NASDAQCOM"
SOX_URL = "https://indexes.nasdaq.com/Index/Overview/SOX"
FOMC = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


def http_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def load():
    return json.loads(PATH.read_text(encoding="utf-8"))


def save(obj):
    PATH.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def add_error(out, source, message):
    out.setdefault("errors", []).append({"source": source, "message": str(message)[:300]})


def fallback_oil(out):
    macro = out.setdefault("macro", {})
    if (macro.get("brent") or {}).get("value") is not None and (macro.get("wti") or {}).get("value") is not None:
        return
    text = http_text(FRED_CSV)
    rows = list(csv.DictReader(io.StringIO(text)))
    valid = []
    for row in rows:
        try:
            b = float(row.get("DCOILBRENTEU") or "")
        except Exception:
            b = None
        try:
            w = float(row.get("DCOILWTICO") or "")
        except Exception:
            w = None
        if b is not None or w is not None:
            valid.append((row.get("DATE") or row.get("observation_date"), b, w))
    if not valid:
        raise ValueError("FRED EIA-series CSV returned no usable oil observations")
    latest = valid[-1]
    prev = valid[-2] if len(valid) > 1 else (None, None, None)
    for key, idx, label in (("brent", 1, "Brent"), ("wti", 2, "WTI")):
        value = latest[idx]
        previous = prev[idx]
        if value is None:
            continue
        change = (value / previous - 1) * 100 if previous else None
        macro[key] = {
            "value": value,
            "display": f"${value:.2f}",
            "change": f"{change:+.2f}%" if change is not None else "",
            "asOf": latest[0],
            "source": "FRED (EIA crude-oil series)",
            "state": "official_secondary",
        }
    out.setdefault("sources", []).append({"name": "FRED EIA crude-oil series fallback", "status": "ok", "asOf": latest[0]})
    # Remove obsolete EIA parse warning once a verified fallback is available.
    out["errors"] = [e for e in out.get("errors", []) if e.get("source") != "U.S. EIA crude spot prices"]



def fallback_equity(out):
    """Public fallback for broad U.S. indexes; SOX uses Nasdaq's official index page."""
    eq=out.setdefault("equity", {})
    # FRED publishes S&P 500 and Nasdaq Composite daily observations.
    try:
        text=http_text(FRED_EQ); rows=list(csv.DictReader(io.StringIO(text))); valid=[]
        for row in rows:
            vals={}
            for k in ("SP500","NASDAQCOM"):
                try: vals[k]=float(row.get(k) or "")
                except Exception: vals[k]=None
            if any(v is not None for v in vals.values()): valid.append((row.get("DATE") or row.get("observation_date"),vals))
        if valid:
            latest=valid[-1]; prev=valid[-2] if len(valid)>1 else (None,{})
            for key,series,label in (("sp500","SP500","S&P 500"),("nasdaq","NASDAQCOM","Nasdaq Composite")):
                v=latest[1].get(series); pv=prev[1].get(series)
                if v is None: continue
                ch=(v/pv-1)*100 if pv else None
                eq[key]={"value":v,"display":f"{v:,.2f}","change":f"{ch:+.2f}%" if ch is not None else "","asOf":latest[0],"source":f"FRED {series}","state":"official_secondary"}
    except Exception as exc: add_error(out,"FRED equity fallback",exc)
    # Nasdaq official SOX page. Only accept a dated DATA AS OF observation.
    try:
        html=http_text(SOX_URL); txt=clean_text(html)
        m=re.search(r"DATA AS OF\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+(?:\.\d+)?)\s+([+-]?[\d,]+(?:\.\d+)?)\s+([+-]?[\d.]+)%",txt,re.I)
        if not m:
            # alternate page text: SOX date then Summary Details Last / Net Change
            mdate=re.search(r"SOX\s+(\d{1,2}/\d{1,2}/\d{4})",txt,re.I); ml=re.search(r"Last\s+([\d,]+(?:\.\d+)?)\s+Net Change\s+([+-]?[\d,]+(?:\.\d+)?)",txt,re.I)
            if mdate and ml:
                dt=datetime.strptime(mdate.group(1),"%m/%d/%Y").date().isoformat(); v=float(ml.group(1).replace(',','')); net=float(ml.group(2).replace(',','')); prev=v-net; pct=(net/prev*100) if prev else None
            else: raise ValueError("Nasdaq SOX dated value not found")
        else:
            dt=datetime.strptime(m.group(1),"%m/%d/%Y").date().isoformat(); v=float(m.group(2).replace(',','')); net=float(m.group(3).replace(',','')); pct=float(m.group(4))
        eq["sox"]={"value":v,"display":f"{v:,.2f}","change":f"{pct:+.2f}%" if pct is not None else "","asOf":dt,"source":"Nasdaq Global Indexes (SOX)","state":"official"}
    except Exception as exc: add_error(out,"Nasdaq SOX official fallback",exc)

def clean_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def repair_fomc(out):
    now = datetime.now(TZ)
    horizon = now + timedelta(days=180)
    text = clean_text(http_text(FOMC))
    year = now.year
    start_markers = [f"{year} FOMC Meetings", f"{year} FOMC meeting"]
    start = -1
    for marker in start_markers:
        start = text.lower().find(marker.lower())
        if start >= 0:
            break
    if start < 0:
        raise ValueError(f"current-year FOMC section not found for {year}")
    next_year_pos = text.lower().find(f"{year + 1} fomc meetings".lower(), start + 1)
    segment = text[start: next_year_pos if next_year_pos > start else start + 5000]

    months = {m: i for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"], 1)}
    fed_events = []
    for mname, mnum in months.items():
        for mm in re.finditer(rf"\b{mname}\b\s+(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?\*?", segment):
            d2 = int(mm.group(2) or mm.group(1))
            try:
                # Standard FOMC statement time = 14:00 ET. Sep is EDT; zoneinfo handles DST.
                from zoneinfo import ZoneInfo
                et = datetime(year, mnum, d2, 14, 0, tzinfo=ZoneInfo("America/New_York"))
                local = et.astimezone(TZ)
            except Exception:
                continue
            if now <= local <= horizon:
                fed_events.append({
                    "source": "Federal Reserve",
                    "title": f"FOMC 利率決策（{mname} {mm.group(1)}" + (f"–{mm.group(2)}" if mm.group(2) else "") + "）",
                    "scheduledAt": local.isoformat(timespec="minutes"),
                    "category": "貨幣政策",
                    "impact": 5,
                    "watch": "政策利率、SEP／Dot Plot（若有）、記者會語氣與美債殖利率。",
                    "link": FOMC,
                })

    # Replace only Fed FOMC calendar items; keep BLS and other events.
    keep = [e for e in out.get("events", []) if not (e.get("source") == "Federal Reserve" and "FOMC" in e.get("title", ""))]
    uniq = {}
    for e in keep + fed_events:
        uniq[(e.get("source"), e.get("title"), e.get("scheduledAt"))] = e
    out["events"] = sorted(uniq.values(), key=lambda x: x.get("scheduledAt", ""))[:20]


def main():
    out = load()
    try:
        fallback_oil(out)
    except Exception as exc:
        add_error(out, "FRED EIA crude-oil fallback", exc)
    try:
        fallback_equity(out)
    except Exception as exc:
        add_error(out, "Equity fallback", exc)
    try:
        repair_fomc(out)
        out.setdefault("sources", []).append({"name": "Federal Reserve FOMC calendar (sanitized)", "status": "ok", "asOf": datetime.now(TZ).isoformat(timespec="seconds")})
    except Exception as exc:
        add_error(out, "Federal Reserve FOMC calendar repair", exc)
    save(out)
    print("repaired", PATH)


if __name__ == "__main__":
    main()
