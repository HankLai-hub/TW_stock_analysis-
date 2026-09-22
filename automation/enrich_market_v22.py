#!/usr/bin/env python3
from __future__ import annotations

"""TW Market Radar V2.2.1 Taiwan-market enrichment hotfix.

Goals
- Keep official-source-first behavior.
- Never relabel old data as current.
- Add TWSE three-institution totals, short / securities-lending balances.
- Build industry *price strength* from the dated TWSE MI_INDEX industry report.
- Do NOT treat TWT38U / TWT43U / TWT44U individual-security files as industry fund flow.
- Maintain backward-compatible metric aliases used by older V2.2 dashboard builders.
"""

import csv
import io
import json
import re
import ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LIVE_P = DATA / "live.json"
SECTOR_P = DATA / "sector-v22.json"
TZ = ZoneInfo("Asia/Taipei")
UA = "TW-Market-Radar/2.2.1 (+official-source-hotfix)"
TWSE_WEB = "https://www.twse.com.tw/rwd/zh"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/csv,text/plain,*/*"})
    with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def http_json(url: str):
    return json.loads(http_text(url))


def to_float(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "").replace("−", "-")
    if s in {"", "--", "---", "N/A", "."}:
        return None
    m = re.search(r"[+-]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def roc_to_iso(v: str | None) -> str | None:
    if not v:
        return None
    s = re.sub(r"[^0-9]", "", str(v))
    if len(s) == 7:
        y, m, d = int(s[:3]) + 1911, int(s[3:5]), int(s[5:7])
    elif len(s) == 8:
        y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    else:
        return None
    try:
        datetime(y, m, d)
    except ValueError:
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def metric(value="N/A", change="", as_of="N/A", state="missing", source="N/A", **extra):
    out = {"value": value, "change": change, "asOf": as_of, "state": state, "source": source}
    out.update(extra)
    return out


def source_status(live: dict, name: str, state: str, as_of="", detail=""):
    rows = live.setdefault("sourceStatus", [])
    rows[:] = [x for x in rows if x.get("name") != name]
    rows.append({"name": name, "state": state, "asOf": as_of, "detail": str(detail)[:320]})


def latest_tw_date(live: dict) -> str | None:
    d = str(((live.get("metrics") or {}).get("taiex") or {}).get("asOf") or "")
    return d if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) else None


def fmt_100m(v: float | None) -> str:
    return f"{v / 1e8:+,.2f} 億" if v is not None else "N/A"


def _find_field(fields, predicates):
    for i, f in enumerate(fields):
        s = str(f)
        if all(p in s for p in predicates):
            return i
    return None


def enrich_institutional_flow(live: dict):
    target = latest_tw_date(live)
    if not target:
        source_status(live, "TWSE V2.2.1 institutional totals", "missing", detail="TAIEX date unavailable")
        return

    ymd = target.replace("-", "")
    # BFI82U is the official daily three-institution amount summary.
    url = f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'json','type':'day','dayDate':ymd})}"
    try:
        payload = http_json(url)
        if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
            raise ValueError("BFI82U official JSON unavailable")

        date = roc_to_iso(payload.get("date")) or target
        if date != target:
            raise ValueError(f"BFI82U returned {date}, expected {target}")

        fields = payload.get("fields") or []
        data = payload.get("data") or []
        net_i = _find_field(fields, ["買賣", "差額"])
        if net_i is None:
            net_i = _find_field(fields, ["買賣超"])

        values = {
            "foreign": None,
            "trust": None,
            "dealer_self": None,
            "dealer_hedge": None,
            "dealer_total": None,
        }

        for row in data:
            if not isinstance(row, list) or not row:
                continue
            label = re.sub(r"\s+", "", str(row[0]))
            raw = row[net_i] if net_i is not None and net_i < len(row) else (row[-1] if len(row) >= 2 else None)
            v = to_float(raw)
            if v is None:
                continue
            if label.startswith("外資及陸資"):
                values["foreign"] = v
            elif label.startswith("投信"):
                values["trust"] = v
            elif "自營商" in label and "自行買賣" in label:
                values["dealer_self"] = v
            elif "自營商" in label and "避險" in label:
                values["dealer_hedge"] = v
            elif label == "自營商" or label.startswith("自營商(合計"):
                values["dealer_total"] = v

        if values["dealer_total"] is None:
            parts = [x for x in (values["dealer_self"], values["dealer_hedge"]) if x is not None]
            values["dealer_total"] = sum(parts) if parts else None

        metrics = live.setdefault("metrics", {})

        if values["foreign"] is not None:
            r = metric(fmt_100m(values["foreign"]), "上市市場", date, "official_afterhours", "TWSE BFI82U", rawValueYi=round(values["foreign"] / 1e8, 4))
            metrics["foreignSpot"] = r
            metrics["foreignSpotOfficial"] = dict(r)

        if values["trust"] is not None:
            r = metric(fmt_100m(values["trust"]), "上市市場", date, "official_afterhours", "TWSE BFI82U", rawValueYi=round(values["trust"] / 1e8, 4))
            # New canonical key + old V2.2 alias.
            metrics["trustSpot"] = r
            metrics["investmentTrust"] = dict(r)

        if values["dealer_total"] is not None:
            structure = []
            if values["dealer_self"] is not None:
                structure.append(f"自行 {values['dealer_self']/1e8:+,.2f} 億")
            if values["dealer_hedge"] is not None:
                structure.append(f"避險 {values['dealer_hedge']/1e8:+,.2f} 億")
            r = metric(fmt_100m(values["dealer_total"]), " / ".join(structure), date, "official_afterhours", "TWSE BFI82U", rawValueYi=round(values["dealer_total"] / 1e8, 4))
            metrics["dealerSpot"] = r
            metrics["dealer"] = dict(r)

        if values["dealer_self"] is not None:
            metrics["dealerSelfSpot"] = metric(fmt_100m(values["dealer_self"]), "自行買賣", date, "official_afterhours", "TWSE BFI82U")
        if values["dealer_hedge"] is not None:
            metrics["dealerHedgeSpot"] = metric(fmt_100m(values["dealer_hedge"]), "避險", date, "official_afterhours", "TWSE BFI82U")

        live["institutionalFlow"] = {"asOf": date, "source": "TWSE BFI82U", **values}
        source_status(live, "TWSE V2.2.1 institutional totals", "ok", date, "BFI82U foreign / trust / dealer self+hedge")
    except Exception as exc:
        source_status(live, "TWSE V2.2.1 institutional totals", "error", target, exc)
        live.setdefault("errors", []).append({"source": "TWSE V2.2.1 institutional totals", "message": str(exc)[:500]})


def _csv_report_date(text: str) -> str | None:
    m = re.search(r"(\d{2,3})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if not m:
        return None
    return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def enrich_short_balance(live: dict):
    target = latest_tw_date(live)
    if not target:
        return
    ymd = target.replace("-", "")
    try:
        url = f"{TWSE_WEB}/marginTrading/MI_MARGN?{urlencode({'response':'csv','selectType':'MS','date':ymd})}"
        text = http_text(url)
        date = _csv_report_date(text) or target
        if date != target:
            raise ValueError(f"MI_MARGN returned {date}, expected {target}")
        rows = list(csv.reader(io.StringIO(text)))
        short_row = next((r for r in rows if r and str(r[0]).replace(" ", "").startswith("融券(交易單位)")), None)
        if not short_row:
            short_row = next((r for r in rows if r and str(r[0]).strip().startswith("融券") and "金額" not in str(r[0])), None)
        if not short_row:
            raise ValueError("TWSE market short-balance row not found")
        nums = [to_float(v) for v in short_row[1:]]
        nums = [x for x in nums if x is not None]
        if not nums:
            raise ValueError("TWSE short balance not recognized")
        today = int(round(nums[-1]))
        previous = int(round(nums[-2])) if len(nums) >= 2 else None
        change = f"較前日 {today-previous:+,} 張" if previous is not None else "上市市場"
        live.setdefault("metrics", {})["shortBalance"] = metric(f"{today:,} 張", change, date, "official_afterhours", "TWSE MI_MARGN")
        source_status(live, "TWSE V2.2.1 short balance", "ok", date, "MI_MARGN market total")
    except Exception as exc:
        source_status(live, "TWSE V2.2.1 short balance", "error", target, exc)


def enrich_borrow_short_balance(live: dict):
    """Best-effort sum of official TWT93U per-security 借券賣出當日餘額.

    Unit stays in shares. It is not added to margin short balance because the
    mechanisms and units differ.
    """
    target = latest_tw_date(live)
    if not target:
        return
    ymd = target.replace("-", "")
    urls = [
        f"{TWSE_WEB}/marginTrading/TWT93U?{urlencode({'response':'csv','date':ymd})}",
        f"https://www.twse.com.tw/exchangeReport/TWT93U?{urlencode({'response':'csv','date':ymd})}",
    ]
    last_exc = None
    for url in urls:
        try:
            text = http_text(url)
            date = _csv_report_date(text) or target
            if date != target:
                raise ValueError(f"TWT93U returned {date}, expected {target}")
            total = 0.0
            count = 0
            for row in csv.reader(io.StringIO(text)):
                if not row or len(row) < 13:
                    continue
                code = str(row[0]).strip()
                if not re.fullmatch(r"[0-9A-Z]{4,10}", code):
                    continue
                v = to_float(row[12])
                if v is None:
                    continue
                total += v
                count += 1
            if not count:
                raise ValueError("TWT93U rows/columns not recognized")
            display = f"{total/1e8:,.2f} 億股" if total >= 1e8 else (f"{total/1e4:,.2f} 萬股" if total >= 1e4 else f"{total:,.0f} 股")
            live.setdefault("metrics", {})["borrowShortBalance"] = metric(display, f"{count} 檔加總；單位為股", date, "official_afterhours", "TWSE TWT93U")
            source_status(live, "TWSE V2.2.1 securities-lending short balance", "ok", date, "TWT93U per-security balances summed in shares")
            return
        except Exception as exc:
            last_exc = exc
    source_status(live, "TWSE V2.2.1 securities-lending short balance", "error", target, last_exc or "unknown error")


def _industry_payload(target: str):
    ymd = target.replace("-", "")
    # Explicit dated industry report. This avoids latest-only OpenAPI ambiguity.
    url = f"{TWSE_WEB}/afterTrading/MI_INDEX?{urlencode({'response':'json','date':ymd,'type':'IND'})}"
    return http_json(url)


def _rows_from_tables(obj):
    for table in (obj.get("tables") or []):
        fields = table.get("fields") or []
        data = table.get("data") or []
        if fields and data:
            for row in data:
                if isinstance(row, list):
                    yield fields, row


def enrich_sector_strength(live: dict):
    target = latest_tw_date(live)
    if not target:
        return

    wanted = {
        "半導體": "半導體類指數",
        "電子零組件": "電子零組件類指數",
        "金融": "金融保險類指數",
        "航運": "航運類指數",
        "資訊服務": "資訊服務類指數",
        "電子工業": "電子工業類指數",
    }

    try:
        obj = _industry_payload(target)
        if not isinstance(obj, dict):
            raise ValueError("MI_INDEX industry report did not return JSON object")
        stat = str(obj.get("stat") or "").upper()
        if stat and stat != "OK":
            raise ValueError(f"MI_INDEX stat={stat}")
        report_date = roc_to_iso(obj.get("date")) or target
        if report_date != target:
            raise ValueError(f"MI_INDEX returned {report_date}, expected {target}")

        found = {}
        for fields, row in _rows_from_tables(obj):
            if not row:
                continue
            name = str(row[0]).strip()
            if not name or "報酬指數" in name:
                continue
            pct_i = _find_field(fields, ["漲跌百分比"])
            if pct_i is None:
                pct_i = _find_field(fields, ["漲跌幅"])
            close_i = _find_field(fields, ["收盤指數"])
            if pct_i is None:
                continue
            found[name] = {
                "pct": to_float(row[pct_i] if pct_i < len(row) else None),
                "close": to_float(row[close_i] if close_i is not None and close_i < len(row) else None),
            }

        taiex_pct = to_float(((live.get("metrics") or {}).get("taiex") or {}).get("change"))
        out = []
        for label, official_name in wanted.items():
            r = found.get(official_name)
            if not r:
                continue
            pct = r.get("pct")
            rel = pct - taiex_pct if pct is not None and taiex_pct is not None else None
            out.append({
                "name": label,
                "officialName": official_name,
                "changePct": pct,
                "relativePctPoint": rel,
                "indexValue": r.get("close"),
                "asOf": target,
                "source": "TWSE MI_INDEX (type=IND)",
            })

        # TPEx index as a separate market proxy, not a TWSE industry.
        otc = ((live.get("metrics") or {}).get("otc") or {})
        if otc.get("asOf") == target:
            pct = to_float(otc.get("change"))
            rel = pct - taiex_pct if pct is not None and taiex_pct is not None else None
            out.append({
                "name": "櫃買（中小型代理）",
                "officialName": "櫃買指數",
                "changePct": pct,
                "relativePctPoint": rel,
                "indexValue": to_float(otc.get("value")),
                "asOf": target,
                "source": otc.get("source") or "TPEx",
                "proxy": True,
            })

        live["sectorPerformance"] = out

        # Compatibility output for any V2.2 builder still reading sector-v22.json.
        # Institutional industry flow is intentionally N/A until per-security data
        # is joined to an official issuer-industry classification and aggregated.
        compat = []
        for row in out:
            compat.append({
                "name": row["name"],
                "priceChangePct": row.get("changePct"),
                "relativePctPoint": row.get("relativePctPoint"),
                "foreignYi": None,
                "trustYi": None,
                "dealerYi": None,
                "institutionalFlowState": "N/A_not_aggregated",
                "asOf": row.get("asOf"),
                "source": row.get("source"),
            })
        write_json(SECTOR_P, {
            "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
            "asOf": target,
            "sectors": compat,
            "note": "V2.2.1: industry cards are official price strength. TWT38U/TWT43U/TWT44U are not treated as industry fund-flow tables.",
        })

        source_status(live, "TWSE V2.2.1 sector strength", "ok" if out else "missing", target, f"{len(out)} verified price-strength series; no fabricated industry fund-flow")
    except Exception as exc:
        source_status(live, "TWSE V2.2.1 sector strength", "error", target, exc)
        live["sectorPerformance"] = []
        write_json(SECTOR_P, {
            "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
            "asOf": target,
            "sectors": [],
            "errors": [str(exc)[:500]],
            "note": "Price strength unavailable; no stale or synthetic sector values emitted.",
        })


def main():
    live = read_json(LIVE_P, {})
    if not isinstance(live, dict):
        live = {}

    enrich_institutional_flow(live)
    enrich_short_balance(live)
    enrich_borrow_short_balance(live)
    enrich_sector_strength(live)

    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    live["v22"] = {"enrichedAt": stamp, "version": "2.2.1"}
    write_json(LIVE_P, live)
    print("V2.2.1 Taiwan enrichment complete")


if __name__ == "__main__":
    main()
