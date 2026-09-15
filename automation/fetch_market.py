from __future__ import annotations

import argparse
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from common import (
    DATA_DIR, append_history, archive_snapshot, atomic_write_json, find_exact, find_value,
    fmt_number, fmt_pct, http_json, http_text, iso_now, metric, now_taipei, read_json,
    row_date, roc_to_iso, signed_number, to_float, to_int,
)

TWSE = "https://openapi.twse.com.tw/v1"
TWSE_WEB = "https://www.twse.com.tw/rwd/zh"
TPEX = "https://www.tpex.org.tw/openapi/v1"
TPEX_LEGACY = "https://wwwov.tpex.org.tw/web/stock"
TAIFEX = "https://openapi.taifex.com.tw/v1"
CBC = "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=BP01D01"
CBC_CSV = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/BP01D01.csv"
CBC_LATEST = "https://www.cbc.gov.tw/tw/lp-645-1-1-60.html"


def blank_snapshot(kind: str) -> dict[str, Any]:
    now = now_taipei()
    phase = market_phase(now)
    return {
        "schemaVersion": 1,
        "generatedAt": iso_now(),
        "runKind": kind,
        "marketPhase": phase,
        "nextExpected": next_expected(now, kind),
        "intradayFeed": {
            "state": "not_configured",
            "label": "盤中授權資料源尚未設定",
            "note": "自動排程會每小時執行，但公開網站的盤中即時／延遲行情應使用具有重新散布權限的資料源。未設定前，盤中價位不以非授權抓取方式補值。",
        },
        "metrics": {
            "taiex": metric(source="TWSE"),
            "otc": metric(source="TPEx"),
            "turnover": metric(source="TWSE"),
            "breadth": metric(source="TWSE/TPEx"),
            "usdTwd": metric(source="CBC"),
            "tx": metric(source="TAIFEX"),
            "foreignSpot": metric(source="TWSE"),
            "foreignTx": metric(source="TAIFEX"),
            "putCall": metric(source="TAIFEX"),
            "margin": metric(source="TWSE/TPEx"),
        },
        "errors": [],
        "sourceStatus": [],
    }


def market_phase(now) -> str:
    if now.weekday() >= 5:
        return "週末／休市"
    minute = now.hour * 60 + now.minute
    if 8 * 60 + 30 <= minute < 9 * 60:
        return "盤前"
    if 9 * 60 <= minute <= 13 * 60 + 30:
        return "盤中"
    if 13 * 60 + 30 < minute < 15 * 60:
        return "收盤資料產製中"
    if 15 * 60 <= minute < 24 * 60:
        return "盤後"
    return "海外時段"


def next_expected(now, kind: str) -> str:
    schedule = [(9,7),(10,7),(11,7),(12,7),(13,7),(15,17),(18,17),(21,17)]
    current = now.hour * 60 + now.minute
    future = [h * 60 + m for h, m in schedule if h * 60 + m > current]
    if future:
        diff = future[0] - current
        if diff < 60:
            return f"下一個排程約 {diff} 分鐘後"
        hours = diff // 60
        mins = diff % 60
        return f"下一個排程約 {hours} 小時 {mins} 分鐘後" if mins else f"下一個排程約 {hours} 小時後"
    return "下一個夜間排程依 GitHub Actions 時程"


def source_ok(snap, name, as_of="", detail=""):
    snap["sourceStatus"].append({"name": name, "state": "ok", "asOf": as_of, "detail": detail})


def source_error(snap, name, exc):
    text = str(exc)
    snap["sourceStatus"].append({"name": name, "state": "error", "asOf": "", "detail": text[:260]})
    snap["errors"].append({"source": name, "message": text[:500]})


def _latest_dated_row(rows):
    dated = []
    for r in rows or []:
        if isinstance(r, dict):
            d = row_date(r)
            if d:
                dated.append((d, r))
    if dated:
        dated.sort(key=lambda x: x[0])
        return dated[-1][1]
    return rows[-1] if rows else None


def _same_day_target(kind: str) -> str | None:
    """Return today's Taipei date only when same-day post-close data may exist."""
    now = now_taipei()
    if kind not in {"afterhours", "manual"}:
        return None
    if now.weekday() >= 5:
        return None
    if (now.hour, now.minute) < (13, 40):
        return None
    return now.strftime("%Y-%m-%d")


def _iter_twse_tables(payload):
    """Yield TWSE RWD tables across both modern tables[] and legacy dataN shapes."""
    if not isinstance(payload, dict):
        return
    tables = payload.get("tables") or []
    for t in tables:
        if isinstance(t, dict):
            yield t.get("title", ""), t.get("fields") or [], t.get("data") or []
    # Compatibility with older response shape.
    for i in range(1, 30):
        fields = payload.get(f"fields{i}")
        data = payload.get(f"data{i}")
        if fields and data:
            yield payload.get(f"title{i}", ""), fields, data


def _field_index(fields, candidates):
    from common import compact
    normalized = [compact(x) for x in fields]
    # Exact matches first. Never let a short generic field such as "指數"
    # match the more specific candidate "收盤指數".
    for candidate in candidates:
        c = compact(candidate)
        for i, value in enumerate(normalized):
            if c and c == value:
                return i
    for candidate in candidates:
        c = compact(candidate)
        for i, value in enumerate(normalized):
            if c and c in value:
                return i
    return None


def _parse_twse_same_day_index(payload, target_iso):
    for _title, fields, data in _iter_twse_tables(payload):
        for row in data:
            if not isinstance(row, list) or not row:
                continue
            if not any("發行量加權股價指數" in str(x) for x in row[:2]):
                continue
            close_i = _field_index(fields, ["收盤指數", "收盤"])
            sign_i = _field_index(fields, ["漲跌(+/-)", "漲跌符號", "漲跌"])
            pct_i = _field_index(fields, ["漲跌百分比", "漲跌幅"])
            value = to_float(row[close_i] if close_i is not None and close_i < len(row) else (row[1] if len(row) > 1 else None))
            pct_raw = row[pct_i] if pct_i is not None and pct_i < len(row) else (row[4] if len(row) > 4 else None)
            sign_raw = row[sign_i] if sign_i is not None and sign_i < len(row) else (row[2] if len(row) > 2 else None)
            pct = signed_number(pct_raw, sign_raw)
            if value is None:
                raise ValueError("TWSE targeted TAIEX close field not recognized")
            return value, pct, target_iso
    raise ValueError("TWSE targeted TAIEX row not found")


def _parse_twse_same_day_breadth(payload, target_iso):
    for title, fields, data in _iter_twse_tables(payload):
        if "漲跌證券數合計" not in str(title):
            continue
        stock_col = 2
        if isinstance(fields, list) and "股票" in fields:
            stock_col = fields.index("股票")
        labels = {str(r[0]).strip(): r[stock_col] for r in data if isinstance(r, list) and len(r) > stock_col}
        up = _parse_count_cell(next((v for k, v in labels.items() if k.startswith("上漲")), None))
        down = _parse_count_cell(next((v for k, v in labels.items() if k.startswith("下跌")), None))
        flat = _parse_count_cell(labels.get("持平"))
        if up is None or down is None:
            raise ValueError("TWSE targeted breadth counts not recognized")
        return up, down, flat, target_iso
    raise ValueError("TWSE targeted breadth table not found")


def _parse_twse_same_day_turnover(payload, target_iso):
    if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
        raise ValueError("TWSE targeted FMTQIK unavailable")
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    date_i = _field_index(fields, ["日期", "Date"])
    amount_i = _field_index(fields, ["成交金額", "成交值", "TradeValue"])
    for row in data:
        if not isinstance(row, list):
            continue
        row_iso = roc_to_iso(row[date_i]) if date_i is not None and date_i < len(row) else None
        if row_iso == target_iso:
            amount = to_float(row[amount_i] if amount_i is not None and amount_i < len(row) else (row[2] if len(row) > 2 else None))
            if amount is None:
                raise ValueError("TWSE targeted turnover amount not recognized")
            return amount, target_iso
    raise ValueError(f"TWSE targeted turnover row not found for {target_iso}")


def fetch_twse_same_day_close(snap, kind: str):
    """Override lagging OpenAPI snapshots with date-targeted TWSE official close data.

    TWSE OpenAPI can lag the same-day RWD pages after the close. This function is
    intentionally best-effort: if today's official endpoint is not ready yet, the
    previous verified snapshot remains visible and a pending source status is kept.
    """
    target = _same_day_target(kind)
    if not target:
        return
    ymd = target.replace("-", "")
    try:
        payload = http_json(f"{TWSE_WEB}/afterTrading/MI_INDEX?{urlencode({'date': ymd, 'type': 'ALL', 'response': 'json'})}")
        if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
            raise ValueError(f"TWSE same-day MI_INDEX not ready for {target}")
        value, pct, date = _parse_twse_same_day_index(payload, target)
        snap["metrics"]["taiex"] = metric(fmt_number(value), fmt_pct(pct), date, "official_close", "TWSE")
        source_ok(snap, "TWSE same-day TAIEX", date, "date-targeted official RWD")

        try:
            up, down, flat, bdate = _parse_twse_same_day_breadth(payload, target)
            snap["metrics"]["breadth"] = metric(
                f"{up}↑ / {down}↓", f"平盤 {flat}" if flat is not None else "",
                bdate, "official_close", "TWSE 股票"
            )
            source_ok(snap, "TWSE same-day breadth", bdate, "date-targeted official RWD")
        except Exception as breadth_exc:
            snap["sourceStatus"].append({"name":"TWSE same-day breadth","state":"pending","asOf":"","detail":str(breadth_exc)[:260]})
    except Exception as exc:
        snap["sourceStatus"].append({"name":"TWSE same-day close","state":"pending","asOf":"","detail":str(exc)[:260]})

    try:
        fmt = http_json(f"{TWSE_WEB}/afterTrading/FMTQIK?{urlencode({'date': ymd, 'response': 'json'})}")
        amount, date = _parse_twse_same_day_turnover(fmt, target)
        snap["metrics"]["turnover"] = metric(f"{amount / 1e8:,.0f} 億", "", date, "official_close", "TWSE")
        source_ok(snap, "TWSE same-day turnover", date, "date-targeted official RWD")
    except Exception as exc:
        snap["sourceStatus"].append({"name":"TWSE same-day turnover","state":"pending","asOf":"","detail":str(exc)[:260]})


def _parse_bfi82u_payload(payload, target_iso=None):
    if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
        raise ValueError("BFI82U official JSON unavailable")
    fields = payload.get("fields") or []
    data = payload.get("data") or []
    date = roc_to_iso(payload.get("date")) or _roc_date_from_text(payload.get("title", "")) or target_iso or "最新官方盤後"
    target = None
    for row in data:
        if isinstance(row, list) and row and str(row[0]).strip().startswith("外資及陸資"):
            target = row
            break
    if not target:
        raise ValueError("foreign investor row not found in BFI82U JSON")
    net = None
    if fields and "買賣差額" in fields:
        idx = fields.index("買賣差額")
        if idx < len(target):
            net = to_float(target[idx])
    if net is None and len(target) >= 4:
        net = to_float(target[-1])
    if net is None:
        raise ValueError("foreign investor net field not recognized")
    return net, date


def fetch_twse_same_day_afterhours(snap, kind: str):
    target = _same_day_target(kind)
    if not target:
        return
    ymd = target.replace("-", "")

    # Foreign spot: explicit dayDate prevents a lagging latest endpoint from
    # silently carrying Friday's value into Monday evening.
    try:
        payload = http_json(f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'json','type':'day','dayDate':ymd})}")
        net, date = _parse_bfi82u_payload(payload, target)
        if date != target:
            raise ValueError(f"BFI82U returned {date}, expected {target}")
        snap["metrics"]["foreignSpot"] = metric(f"{net / 1e8:+,.2f} 億", "上市市場", date, "official_afterhours", "TWSE")
        source_ok(snap, "TWSE same-day BFI82U", date, "date-targeted official RWD")
    except Exception as exc:
        snap["sourceStatus"].append({"name":"TWSE same-day BFI82U","state":"pending","asOf":"","detail":str(exc)[:260]})

    # Margin: it is often published later than cash-market close. Override only
    # when the returned document explicitly contains today's date.
    try:
        import csv, io
        url = f"{TWSE_WEB}/marginTrading/MI_MARGN?{urlencode({'response':'csv','selectType':'MS','date':ymd})}"
        raw = http_text(url, accept="text/csv,text/plain,*/*")
        date = _roc_date_from_text(raw)
        if date != target:
            raise ValueError(f"MI_MARGN returned {date or 'unknown'}, expected {target}")
        rows = list(csv.reader(io.StringIO(raw)))
        row = next((r for r in rows if r and "融資金額" in str(r[0])), None)
        if not row:
            raise ValueError("same-day TWSE margin amount row not found")
        nums = [to_float(v) for v in row[1:]]
        nums = [v for v in nums if v is not None]
        if not nums:
            raise ValueError("same-day TWSE margin balance not recognized")
        amount_100m = nums[-1] / 100000.0
        old = snap["metrics"].get("margin", {})
        tpex_text = str(old.get("change") or "")
        snap["metrics"]["margin"] = metric(
            f"上市 {amount_100m:,.2f} 億", tpex_text,
            target, "official_afterhours", "TWSE / TPEx（不同單位）"
        )
        source_ok(snap, "TWSE same-day margin", target, "date-targeted official CSV")
    except Exception as exc:
        snap["sourceStatus"].append({"name":"TWSE same-day margin","state":"pending","asOf":"","detail":str(exc)[:260]})


def _latest_rows_for_date(rows, predicate):
    candidates = [r for r in rows or [] if isinstance(r, dict) and predicate(r)]
    if not candidates:
        return []
    dates = [row_date(r) for r in candidates if row_date(r)]
    if dates:
        latest = max(dates)
        same = [r for r in candidates if row_date(r) == latest]
        if same:
            return same
    return candidates


def fetch_twse_close(snap):
    try:
        rows = http_json(f"{TWSE}/exchangeReport/MI_INDEX")
        if not isinstance(rows, list):
            raise ValueError("MI_INDEX did not return a list")
        row = next((r for r in rows if "發行量加權" in str(find_value(r, ["指數", "Index"]) or "")), None)
        if not row:
            raise ValueError("TAIEX row not found")
        value = to_float(find_exact(row, ["收盤指數", "ClosingIndex", "IndexValue"]))
        pct = signed_number(find_exact(row, ["漲跌百分比", "ChangePercent", "ChangePercentage"]), find_exact(row, ["漲跌", "Direction"]))
        date = row_date(row) or "最新官方收盤"
        snap["metrics"]["taiex"] = metric(fmt_number(value), fmt_pct(pct), date, "official_close", "TWSE")
        source_ok(snap, "TWSE MI_INDEX", date)
    except Exception as exc:
        source_error(snap, "TWSE MI_INDEX", exc)


def _parse_count_cell(value):
    import re
    m = re.search(r"[\d,]+", str(value or ""))
    return int(m.group(0).replace(",", "")) if m else None


def fetch_twse_breadth(snap):
    """Fetch listed-stock breadth for the same official close date as TAIEX.

    Do not use twtazu_od here: that dataset is not a daily breadth snapshot and
    can legitimately carry an older publication date, which previously caused
    stale counts to be shown as current market breadth.
    """
    try:
        date = str(snap["metrics"].get("taiex", {}).get("asOf", ""))
        if not (len(date) == 10 and date[4] == "-" and date[7] == "-"):
            raise ValueError("TAIEX official date unavailable; breadth not attributable")
        ymd = date.replace("-", "")
        payload = http_json(f"{TWSE_WEB}/afterTrading/MI_INDEX?{urlencode({'date':ymd,'type':'MS','response':'json'})}")
        if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
            raise ValueError(f"TWSE market-stat payload unavailable for {date}")

        fields = None
        data = None
        for table in payload.get("tables", []) or []:
            if "漲跌證券數合計" in str(table.get("title", "")):
                fields = table.get("fields")
                data = table.get("data")
                break
        if not data and payload.get("data8"):
            fields = payload.get("fields8")
            data = payload.get("data8")
        if not data:
            raise ValueError("TWSE breadth table not found")

        # Layout is [類型, 整體市場, 股票]; use 股票 only, excluding warrants.
        stock_col = 2
        if isinstance(fields, list) and "股票" in fields:
            stock_col = fields.index("股票")
        labels = {str(r[0]).strip(): r[stock_col] for r in data if isinstance(r, list) and len(r) > stock_col}
        up = _parse_count_cell(next((v for k,v in labels.items() if k.startswith("上漲")), None))
        down = _parse_count_cell(next((v for k,v in labels.items() if k.startswith("下跌")), None))
        flat = _parse_count_cell(labels.get("持平"))
        if up is None or down is None:
            raise ValueError("TWSE stock breadth counts not recognized")
        snap["metrics"]["breadth"] = metric(
            f"{up}↑ / {down}↓",
            f"平盤 {flat}" if flat is not None else "",
            date, "official_close", "TWSE 股票"
        )
        source_ok(snap, "TWSE stock breadth", date)
    except Exception as exc:
        source_error(snap, "TWSE stock breadth", exc)


def fetch_twse_turnover(snap):
    try:
        rows = http_json(f"{TWSE}/exchangeReport/FMTQIK")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty FMTQIK")
        row = _latest_dated_row(rows)
        amount = to_float(find_exact(row, ["成交金額", "TradeValue", "成交值"]))
        date = row_date(row) or "最新官方收盤"
        value = f"{amount / 1e8:,.0f} 億" if amount is not None else "N/A"
        snap["metrics"]["turnover"] = metric(value, "", date, "official_close", "TWSE")
        source_ok(snap, "TWSE turnover", date)
    except Exception as exc:
        source_error(snap, "TWSE turnover", exc)

def _iso_to_roc_date(value: str, month_only: bool = False) -> str | None:
    import re
    m = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", str(value or ""))
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    roc = y - 1911
    return f"{roc:03d}/{mo:02d}" if month_only else f"{roc:03d}/{mo:02d}/{d:02d}"


def _tpex_target_date(snap) -> str | None:
    # Taiwan markets share the same trading calendar; use the already verified
    # TWSE official date rather than guessing a date during holidays/weekends.
    date = str(snap.get("metrics", {}).get("taiex", {}).get("asOf", ""))
    if len(date) == 10 and date[4] == "-" and date[7] == "-":
        return date
    return None


def _fetch_tpex_legacy_market(target_date: str) -> dict[str, Any]:
    """Official TPEx legacy post-close endpoints on the wwwov host.

    These endpoints expose the same post-close data published by TPEx and are
    used only if the modern OpenAPI host cannot be TLS-verified by the runner.
    SSL verification remains enabled.
    """
    roc_day = _iso_to_roc_date(target_date)
    roc_month = _iso_to_roc_date(target_date, month_only=True)
    if not roc_day or not roc_month:
        raise ValueError("TPEx fallback target date unavailable")

    # Daily trading amount/index: [date, volume, amount, transactions, index, change]
    idx_url = (
        f"{TPEX_LEGACY}/aftertrading/daily_trading_index/st41_result.php?"
        + urlencode({"l": "zh-tw", "d": roc_month, "o": "json"})
    )
    idx_payload = http_json(idx_url)
    idx_row = None
    for row in (idx_payload.get("aaData", []) if isinstance(idx_payload, dict) else []):
        if isinstance(row, list) and row:
            if roc_to_iso(row[0]) == target_date:
                idx_row = row
                break
    if not idx_row:
        raise ValueError(f"TPEx legacy index row not found for {target_date}")

    value = to_float(idx_row[4] if len(idx_row) > 4 else None)
    change = signed_number(idx_row[5] if len(idx_row) > 5 else None)
    amount = to_float(idx_row[2] if len(idx_row) > 2 else None)
    pct = None
    if value is not None and change is not None and (value - change) != 0:
        pct = change / (value - change) * 100

    # Market highlight: breadth and a second independent index/turnover check.
    hi_url = (
        f"{TPEX_LEGACY}/aftertrading/market_highlight/highlight_result.php?"
        + urlencode({"l": "zh-tw", "o": "json", "d": roc_day})
    )
    hi = http_json(hi_url)
    if not isinstance(hi, dict) or to_int(hi.get("iTotalRecords")) in {None, 0}:
        raise ValueError(f"TPEx legacy highlight unavailable for {target_date}")

    return {
        "date": roc_to_iso(hi.get("reportDate")) or target_date,
        "index": value if value is not None else to_float(hi.get("close")),
        "change": change if change is not None else signed_number(hi.get("change")),
        "pct": pct,
        "trade_amount": amount,
        "up": to_int(hi.get("upNum")),
        "down": to_int(hi.get("downNum")),
        "flat": to_int(hi.get("noChangeNum")),
        "limit_up": to_int(hi.get("upStopNum")),
        "limit_down": to_int(hi.get("downStopNum")),
    }

def fetch_tpex_summary(snap):
    target_date = _tpex_target_date(snap)
    modern_exc = None
    legacy = None

    # 1) Preferred modern official OpenAPI.
    try:
        rows = http_json(f"{TPEX}/tpex_daily_trading_index")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx daily trading index")
        row = _latest_dated_row(rows)
        date = row_date(row) or "最新官方收盤"
        if target_date and date != target_date:
            raise ValueError(f"TPEx OpenAPI latest date {date} is not same-day target {target_date}")
        value = to_float(find_exact(row, ["TPEXIndex", "Close", "Index", "IndexValue", "收盤指數", "指數", "ClosingIndex"]))
        change_pts = signed_number(find_exact(row, ["Change", "漲跌", "ChangePoint"]))
        pct = to_float(find_exact(row, ["ChangePercent", "ChangePercentage", "漲跌幅", "漲跌百分比"]))
        if pct is None and value is not None and change_pts is not None and (value - change_pts) != 0:
            pct = change_pts / (value - change_pts) * 100
        if value is None:
            raise ValueError(f"TPEx index field not recognized: {list(row)[:16]}")
        snap["metrics"]["otc"] = metric(fmt_number(value), fmt_pct(pct), date, "official_close", "TPEx")
        source_ok(snap, "TPEx daily trading index", date, "OpenAPI")
    except Exception as exc:
        modern_exc = exc
        try:
            if not target_date:
                raise ValueError("verified Taiwan trading date unavailable for TPEx fallback")
            legacy = _fetch_tpex_legacy_market(target_date)
            value = legacy["index"]
            pct = legacy["pct"]
            if pct is None and value is not None and legacy["change"] is not None and (value - legacy["change"]) != 0:
                pct = legacy["change"] / (value - legacy["change"]) * 100
            if value is None:
                raise ValueError("TPEx legacy index value missing")
            snap["metrics"]["otc"] = metric(
                fmt_number(value), fmt_pct(pct), legacy["date"], "official_close", "TPEx"
            )
            source_ok(snap, "TPEx daily trading index", legacy["date"], "official wwwov fallback")
        except Exception as fallback_exc:
            source_error(snap, "TPEx daily trading index", f"OpenAPI: {modern_exc}; fallback: {fallback_exc}")

    # 2) Breadth. Prefer official market-highlight fields. If TPEx changes
    # schema naming, derive breadth from official daily close quotes instead of
    # treating a schema-label change as a source failure.
    try:
        rows = http_json(f"{TPEX}/tpex_mainborad_highlight")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx highlight")
        row = _latest_dated_row(rows) or rows[0]
        date = row_date(row) or target_date or "最新官方收盤"

        up = to_int(find_value(row, [
            "UpNum", "RiseNum", "RisingStocks", "Advances", "Advance",
            "AdvanceCount", "UpCount", "上漲家數"
        ]))
        down = to_int(find_value(row, [
            "DownNum", "FallNum", "FallingStocks", "Declines", "Decline",
            "DeclineCount", "DownCount", "下跌家數"
        ]))
        flat = to_int(find_value(row, [
            "NoChangeNum", "FlatNum", "Unchanged", "UnchangedCount",
            "NoChangeCount", "平盤家數", "持平家數"
        ]))

        if up is None or down is None:
            # Official dataset "上櫃股票行情" contains close/change for every
            # listed security. For breadth use 4-digit stock codes only, which
            # excludes ETFs/ETNs/bonds from the count.
            quotes = http_json(f"{TPEX}/tpex_mainboard_daily_close_quotes")
            if not isinstance(quotes, list) or not quotes:
                raise ValueError("TPEx close quotes unavailable for breadth fallback")

            q_date = None
            up = down = flat = 0
            seen = 0
            import re as _re
            for q in quotes:
                if not isinstance(q, dict):
                    continue
                code = str(find_value(q, ["SecuritiesCompanyCode", "Code", "代號", "證券代號"]) or "").strip()
                if not _re.fullmatch(r"\d{4}", code):
                    continue
                change = signed_number(find_value(q, ["Change", "漲跌", "ChangeAmount"]))
                if change is None:
                    continue
                seen += 1
                if change > 0:
                    up += 1
                elif change < 0:
                    down += 1
                else:
                    flat += 1
                d = row_date(q)
                if d and (q_date is None or d > q_date):
                    q_date = d
            if seen == 0:
                raise ValueError("TPEx official close quotes contained no stock breadth rows")
            date = q_date or date
            detail = "OpenAPI close-quotes derived stock breadth"
        else:
            detail = "OpenAPI market-highlight breadth"

        tpex_breadth = (date, up, down, flat)
        source_ok(snap, "TPEx market highlight", date, detail)
    except Exception as exc:
        # Do not depend on the retired wwwov host. If official current OpenAPI
        # cannot supply breadth, keep listed-market breadth only and surface
        # this as a genuine source warning.
        tpex_breadth = None
        source_error(snap, "TPEx market highlight", exc)

    current = snap["metrics"].get("breadth", {})
    if tpex_breadth and current.get("value") not in {None, "", "N/A"}:
        import re
        date, up, down, flat = tpex_breadth
        m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", str(current.get("value", "")))
        if m and str(current.get("asOf")) == date:
            twse_up = int(m.group(1).replace(",", ""))
            twse_down = int(m.group(2).replace(",", ""))
            flat_m = re.search(r"平盤\s*([\d,]+)", str(current.get("change", "")))
            twse_flat = int(flat_m.group(1).replace(",", "")) if flat_m else 0
            snap["metrics"]["breadth"] = metric(
                f"{twse_up + up}↑ / {twse_down + down}↓",
                f"平盤 {twse_flat + (flat or 0)}",
                date, "official_close", "TWSE/TPEx 股票"
            )

def fetch_cbc(snap):
    """Fetch the latest official USD/TWD closing rate from CBC.

    Prefer the CBC "latest daily data" HTML because it is explicitly the
    bank's current daily closing-rate publication and is newest-first.
    Keep BP01D01 CSV as a fallback only.
    """
    import re
    import csv
    import io

    try:
        html = http_text(CBC_LATEST, accept="text/html,text/plain,*/*")
        # The official page contains rows such as:
        # 2026/09/11 | 31.638
        pairs = re.findall(
            r"(?<!\d)(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?!\d)"
            r"[\s\S]{0,180}?"
            r"(?<![\d.])(\d{2}\.\d{3})(?!\d)",
            html,
        )
        candidates = []
        for y, m, d, rate in pairs:
            iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            f = to_float(rate)
            if f is not None and 20 <= f <= 50:
                candidates.append((iso, f))
        if not candidates:
            raise ValueError("CBC latest-day page rows not recognized")
        # Deduplicate, then select the newest official day.
        candidates = sorted(set(candidates), key=lambda x: x[0])
        date, value = candidates[-1]
        snap["metrics"]["usdTwd"] = metric(
            fmt_number(value, 3), "", date, "official_daily", "CBC"
        )
        source_ok(snap, "CBC USD/TWD", date, "CBC latest daily closing-rate page")
        return
    except Exception as html_exc:
        try:
            text = http_text(CBC_CSV, accept="text/csv,text/plain,*/*")
            rows = list(csv.DictReader(io.StringIO(text)))
            if not rows:
                raise ValueError("CBC BP01D01 CSV empty")

            candidates = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                date_raw = find_exact(r, ["期間", "日期", "Date", "Period"])
                value = find_exact(r, ["新台幣NTD/USD", "新臺幣NTD/USD", "NTD/USD", "NTDUSD"])
                f = to_float(value)
                iso = roc_to_iso(date_raw)
                if f is not None and iso and 20 <= f <= 50:
                    candidates.append((iso, f))
            if not candidates:
                raise ValueError(f"CBC BP01D01 columns not recognized: {list(rows[0])[:12]}")
            candidates.sort(key=lambda x: x[0])
            date, value = candidates[-1]
            snap["metrics"]["usdTwd"] = metric(
                fmt_number(value, 3), "", date, "official_daily", "CBC"
            )
            source_ok(snap, "CBC USD/TWD", date, "BP01D01 official CSV fallback")
        except Exception as csv_exc:
            source_error(snap, "CBC USD/TWD", f"HTML: {html_exc}; CSV: {csv_exc}")

def _roc_date_from_text(text: str) -> str | None:
    import re
    s = str(text or "")
    # Gregorian first. Otherwise "2026/09/11" can be accidentally read as ROC 026/09/11.
    m = re.search(r"(?<!\d)(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?!\d)", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(?:民國\s*)?(?<!\d)(\d{3})[年/-](\d{1,2})[月/-](\d{1,2})(?:日)?(?!\d)", s)
    if m:
        return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def fetch_twse_institutional(snap):
    """Fetch TWSE foreign-investor net trading.

    Prefer the official JSON response because it keeps row labels and numeric
    columns separate. Fall back to the CSV export for compatibility.
    """
    try:
        payload = http_json(f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'json','type':'day'})}")
        if not isinstance(payload, dict) or str(payload.get("stat", "")).upper() != "OK":
            raise ValueError("BFI82U official JSON unavailable")
        fields = payload.get("fields") or []
        data = payload.get("data") or []
        date = roc_to_iso(payload.get("date")) or _roc_date_from_text(payload.get("title", "")) or "最新官方盤後"

        target = None
        for row in data:
            if not isinstance(row, list) or not row:
                continue
            label = str(row[0]).strip()
            if label.startswith("外資及陸資"):
                target = row
                break
        if not target:
            raise ValueError("foreign investor row not found in BFI82U JSON")

        net = None
        if fields and "買賣差額" in fields:
            idx = fields.index("買賣差額")
            if idx < len(target):
                net = to_float(target[idx])
        if net is None and len(target) >= 4:
            net = to_float(target[-1])
        if net is None:
            raise ValueError(f"foreign investor net field not recognized: {target[:8]}")

        value = f"{net / 1e8:+,.2f} 億"
        snap["metrics"]["foreignSpot"] = metric(value, "上市市場", date, "official_afterhours", "TWSE")
        source_ok(snap, "TWSE BFI82U", date, "official JSON")
        return
    except Exception as json_exc:
        import csv
        import io
        try:
            url = f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'csv','type':'day'})}"
            raw = http_text(url, accept="text/csv,text/plain,*/*")
            parsed = list(csv.reader(io.StringIO(raw)))
            date = _roc_date_from_text(raw) or "最新官方盤後"
            target = None
            for row in parsed:
                if len(row) < 4:
                    continue
                label = str(row[0]).strip()
                if label.startswith("外資及陸資"):
                    target = row
                    break
            if not target:
                raise ValueError("foreign investor row not found in BFI82U CSV")
            net = to_float(target[-1])
            if net is None:
                raise ValueError(f"foreign investor net field not recognized: {target[:8]}")
            value = f"{net / 1e8:+,.2f} 億"
            snap["metrics"]["foreignSpot"] = metric(value, "上市市場", date, "official_afterhours", "TWSE")
            source_ok(snap, "TWSE BFI82U", date, "official CSV fallback")
        except Exception as csv_exc:
            source_error(snap, "TWSE BFI82U", f"JSON: {json_exc}; CSV: {csv_exc}")


def fetch_margin(snap):
    """Fetch TWSE market-level margin amount from the official CSV export.

    TPEx remains a separate quantity because its OpenAPI balance is not in NTD
    and must not be added to the TWSE monetary balance.
    """
    import csv
    import io
    twse_amount_100m = None
    tpex_units = None
    dates = []

    try:
        url = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=csv&selectType=MS"
        text = http_text(url, accept="text/csv,text/plain,*/*")
        rows = list(csv.reader(io.StringIO(text)))
        date = _roc_date_from_text(text) or "最新官方盤後"
        target = next((r for r in rows if r and "融資金額" in str(r[0])), None)
        if not target:
            raise ValueError("TWSE margin amount row not found in official CSV")
        nums = [to_float(v) for v in target[1:]]
        nums = [v for v in nums if v is not None]
        if not nums:
            raise ValueError("TWSE margin balance not recognized")
        today = nums[-1]  # 今日餘額，官方單位為仟元
        twse_amount_100m = today / 100000.0
        dates.append(date)
        source_ok(snap, "TWSE margin market total", date, "融資金額(仟元)→億元")
    except Exception as exc:
        source_error(snap, "TWSE margin market total", exc)

    # TPEx OpenAPI provides a per-security financing balance in 張.
    # This is not the same unit as TWSE's market-wide financing amount (NTD),
    # so keep the two official measures side-by-side instead of fabricating a
    # cross-market monetary total.
    tpex_qty = None
    tpex_date = None
    try:
        rows = http_json(f"{TPEX}/tpex_mainboard_margin_balance")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx margin payload")

        qty_values = []
        tpex_dates = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            qty = to_int(find_value(r, [
                "MarginPurchaseTodayBalance", "MarginPurchaseBalance",
                "MarginBalance", "資餘額", "融資餘額"
            ]))
            if qty is not None:
                qty_values.append(qty)
            d = row_date(r)
            if d:
                tpex_dates.append(d)

        if not qty_values:
            raise ValueError("TPEx financing balance quantity fields not recognized")

        tpex_qty = sum(qty_values)
        tpex_date = max(tpex_dates) if tpex_dates else "最新官方盤後"
        dates.append(tpex_date)
        source_ok(
            snap, "TPEx margin", tpex_date,
            "OpenAPI per-security financing balance; official unit 張"
        )
    except Exception as exc:
        # A missing same-unit TPEx monetary total is not a market-data failure.
        # Keep the listed-market monetary balance and explicitly show TPEx N/A.
        snap["sourceStatus"].append({
            "name": "TPEx margin",
            "state": "not_comparable",
            "asOf": "",
            "detail": str(exc)[:260],
        })

    if twse_amount_100m is not None or tpex_qty is not None:
        value = f"上市 {twse_amount_100m:,.2f} 億" if twse_amount_100m is not None else "上市 N/A"
        change = f"上櫃 {tpex_qty:,} 張" if tpex_qty is not None else "上櫃 N/A（不同口徑）"
        snap["metrics"]["margin"] = metric(
            value, change, max(dates) if dates else "最新官方盤後",
            "official_afterhours", "TWSE / TPEx（不同單位）",
        )

def _parse_taifex_institutional_html(html: str):
    """Parse the official TAIFEX futContractsDateExcel page.

    The page uses rowspan cells, so the foreign row may not repeat the product
    name. First try a table-aware parser; if the markup changes, fall back to a
    bounded text extraction inside the 臺股期貨 section.
    """
    from html.parser import HTMLParser
    from html import unescape
    import re

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []
            self._row = None
            self._cell = None
        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row = []
            elif tag in {"td", "th"} and self._row is not None:
                self._cell = []
        def handle_data(self, data):
            if self._cell is not None:
                self._cell.append(data)
        def handle_endtag(self, tag):
            if tag in {"td", "th"} and self._cell is not None:
                self._row.append(" ".join(self._cell).strip())
                self._cell = None
            elif tag == "tr" and self._row is not None:
                self.rows.append(self._row)
                self._row = None

    parser = TableParser()
    parser.feed(html)

    current_product = ""
    for cells in parser.rows:
        clean = [" ".join(str(c).split()) for c in cells if str(c).strip()]
        if not clean:
            continue

        if any("臺股期貨" in c for c in clean):
            current_product = "臺股期貨"
        elif any("電子期貨" in c for c in clean):
            current_product = "電子期貨"
        elif any("金融期貨" in c for c in clean):
            current_product = "金融期貨"

        if current_product == "臺股期貨" and any(c == "外資" or c.startswith("外資") for c in clean):
            idx = next(i for i, c in enumerate(clean) if c == "外資" or c.startswith("外資"))
            nums = [to_int(v) for v in clean[idx + 1:]]
            nums = [v for v in nums if v is not None]
            if len(nums) >= 12:
                return {
                    "long_oi": nums[6],
                    "short_oi": nums[8],
                    "net": nums[10],
                    "date": _roc_date_from_text(html) or "最新官方盤後",
                }

    # Defensive fallback: strip markup, isolate the 臺股期貨 block, then read
    # the first 12 numeric fields after 外資. Official columns are:
    # trade long(amount), trade short(amount), trade net(amount),
    # OI long(amount), OI short(amount), OI net(amount).
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = " ".join(text.split())
    start = text.find("臺股期貨")
    if start >= 0:
        end_candidates = [
            p for p in (
                text.find("電子期貨", start + 4),
                text.find("金融期貨", start + 4),
                text.find("小型臺指期貨", start + 4),
            )
            if p > start
        ]
        end = min(end_candidates) if end_candidates else min(len(text), start + 12000)
        block = text[start:end]
        fpos = block.find("外資")
        if fpos >= 0:
            tail = block[fpos + len("外資"):]
            tokens = re.findall(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?", tail)
            nums = []
            for token in tokens:
                n = to_int(token)
                if n is not None:
                    nums.append(n)
                if len(nums) >= 12:
                    break
            if len(nums) >= 12:
                return {
                    "long_oi": nums[6],
                    "short_oi": nums[8],
                    "net": nums[10],
                    "date": _roc_date_from_text(html) or "最新官方盤後",
                }

    raise ValueError("TX foreign row not found in TAIFEX official page")


def fetch_taifex(snap):
    try:
        api_exc = None
        try:
            rows = http_json(f"{TAIFEX}/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")
            if not isinstance(rows, list):
                raise ValueError("TAIFEX institutional endpoint not list")
            candidates = _latest_rows_for_date(
                rows,
                lambda r: str(find_value(r, ["ContractCode", "商品名稱", "Contract"]) or "").strip() in {"臺股期貨", "TX"}
                and "外資" in str(find_value(r, ["Item", "身份別", "Identity"]) or "")
            )
            row = candidates[0] if candidates else None
            if not row:
                raise ValueError("TX foreign row not found")
            net = to_int(find_value(row, ["OpenInterest(Net)", "OpenInterestNet", "未平倉多空淨額", "未平倉淨額"]))
            long_oi = to_int(find_value(row, ["OpenInterest(Long)", "OpenInterestLong", "多方未平倉"]))
            short_oi = to_int(find_value(row, ["OpenInterest(Short)", "OpenInterestShort", "空方未平倉"]))
            date = row_date(row) or "最新官方盤後"
        except Exception as exc:
            api_exc = exc
            html = http_text(
                "https://www.taifex.com.tw/cht/3/futContractsDateExcel",
                accept="text/html,text/plain,*/*",
            )
            parsed = _parse_taifex_institutional_html(html)
            net = parsed["net"]
            long_oi = parsed["long_oi"]
            short_oi = parsed["short_oi"]
            date = parsed["date"]

        if net is None:
            raise ValueError("TAIFEX foreign TX net OI missing")
        value = f"{net:+,} 口"
        detail = f"多 {long_oi:,} / 空 {short_oi:,}" if long_oi is not None and short_oi is not None else ""
        snap["metrics"]["foreignTx"] = metric(value, detail, date, "official_afterhours", "TAIFEX")
        source_ok(snap, "TAIFEX institutional TX", date, "OpenAPI" if api_exc is None else "official HTML fallback")
    except Exception as exc:
        source_error(snap, "TAIFEX institutional TX", exc)

    try:
        rows = http_json(f"{TAIFEX}/PutCallRatio")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty PutCallRatio")
        row = _latest_dated_row(rows) or rows[0]
        vol = to_float(find_value(row, ["PutCallVolumeRatio", "Put/Call Volume Ratio", "買賣權成交量比率", "成交量比率"]))
        oi = to_float(find_value(row, ["PutCallOpenInterestRatio", "Put/Call OI Ratio", "買賣權未平倉量比率", "未平倉量比率"]))
        date = row_date(row) or "最新官方盤後"
        value = f"成交 {vol:.2f}%" if vol is not None else "N/A"
        change = f"OI {oi:.2f}%" if oi is not None else ""
        snap["metrics"]["putCall"] = metric(value, change, date, "official_afterhours", "TAIFEX")
        source_ok(snap, "TAIFEX Put/Call", date)
    except Exception as exc:
        source_error(snap, "TAIFEX Put/Call", exc)

    try:
        rows = http_json(f"{TAIFEX}/DailyMarketReportFut")
        if not isinstance(rows, list):
            raise ValueError("DailyMarketReportFut not list")
        tx_rows = [r for r in rows if str(find_value(r, ["Contract", "契約"]) or "").strip() == "TX"]
        if not tx_rows:
            raise ValueError("TX daily market row not found")
        dated = [row_date(r) for r in tx_rows if row_date(r)]
        if dated:
            latest_date = max(dated)
            tx_rows = [r for r in tx_rows if row_date(r) == latest_date]
        # Prefer day session and nearest YYYYMM contract.
        tx_rows.sort(key=lambda r: str(find_value(r, ["ContractMonth(Week)", "到期月份(週別)"]) or ""))
        row = next((r for r in tx_rows if "一般" in str(find_value(r, ["TradingSession", "交易時段"]) or "")), tx_rows[0])
        last = to_float(find_exact(row, ["Last", "LastPrice", "最後成交價"]))
        pct = signed_number(find_exact(row, ["ChangePercent", "漲跌%", "漲跌幅", "漲跌百分比"]))
        change_pts = signed_number(find_exact(row, ["Change", "漲跌", "ChangePoint"]))
        if pct is None and last is not None and change_pts is not None and (last - change_pts) != 0:
            pct = change_pts / (last - change_pts) * 100
        date = row_date(row) or "最新官方行情"
        snap["metrics"]["tx"] = metric(fmt_number(last, 0), fmt_pct(pct), date, "official_close", "TAIFEX")
        source_ok(snap, "TAIFEX TX daily", date)
    except Exception as exc:
        source_error(snap, "TAIFEX TX daily", exc)


def _parse_iso_timestamp(value: str):
    from datetime import datetime
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _intraday_change(row):
    pct = row.get("changePercent", row.get("changePct"))
    if pct is not None:
        f = to_float(pct)
        return fmt_pct(f) if f is not None else str(pct)
    change = row.get("change")
    if change is not None:
        if isinstance(change, (int, float)):
            return fmt_number(change, 2)
        return str(change)
    return ""


def fetch_intraday_feed(snap):
    """Overlay an explicitly authorized public-display intraday feed.

    This adapter deliberately requires BOTH:
    1) the repository owner to opt in via INTRADAY_PUBLIC_DISPLAY=YES, and
    2) the feed payload to state license.publicDisplay=true.

    It does not attempt to infer legal redistribution rights from a broker login
    or a raw quote API. The public website remains on official-close data unless
    these conditions are met.
    """
    from datetime import datetime, timezone

    url = os.environ.get("INTRADAY_FEED_URL", "").strip()
    token = os.environ.get("INTRADAY_FEED_TOKEN", "").strip() or None
    public_opt_in = os.environ.get("INTRADAY_PUBLIC_DISPLAY", "").strip().upper() == "YES"

    if not url:
        snap["intradayFeed"] = {
            "state": "not_configured",
            "label": "授權盤中資料源尚未設定",
            "note": "目前公開網站只顯示可驗證的官方盤後／日資料。"
        }
        return

    if not public_opt_in:
        snap["intradayFeed"] = {
            "state": "authorization_required",
            "label": "盤中資料源已填入，但公開展示尚未啟用",
            "note": "確認供應商／交易所授權允許公開重新散布後，才將 GitHub Secret INTRADAY_PUBLIC_DISPLAY 設為 YES。"
        }
        return

    try:
        payload = http_json(url, token=token)
        if not isinstance(payload, dict):
            raise ValueError("licensed feed payload must be a JSON object")

        license_info = payload.get("license") if isinstance(payload.get("license"), dict) else {}
        if license_info.get("publicDisplay") is not True:
            raise ValueError("feed does not declare license.publicDisplay=true")

        vendor = str(license_info.get("vendor") or payload.get("source") or "Authorized market-data vendor")
        mode = str(license_info.get("mode") or "authorized").strip().lower()
        if mode not in {"real_time", "realtime", "delayed", "authorized"}:
            raise ValueError(f"unsupported authorized feed mode: {mode}")

        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("feed.metrics must be an object")

        feed_asof = str(payload.get("asOf") or payload.get("timestamp") or "")
        feed_dt = _parse_iso_timestamp(feed_asof)
        if feed_dt is None:
            raise ValueError("feed must provide an ISO-8601 asOf/timestamp")

        now = now_taipei()
        if feed_dt.tzinfo is None:
            raise ValueError("feed timestamp must include timezone offset")
        age_minutes = (now.astimezone(timezone.utc) - feed_dt.astimezone(timezone.utc)).total_seconds() / 60
        if age_minutes < -10:
            raise ValueError("feed timestamp is unexpectedly in the future")
        if snap.get("marketPhase") == "盤中" and age_minutes > 90:
            raise ValueError(f"authorized intraday feed is stale ({age_minutes:.0f} minutes old)")

        def row_asof(row):
            return str(row.get("asOf") or feed_asof)

        def row_source(row):
            return str(row.get("source") or vendor)

        # Index / futures prices
        bounds = {
            "taiex": (5000, 100000),
            "otc": (50, 2000),
            "tx": (5000, 100000),
        }
        for key, (lo, hi) in bounds.items():
            row = metrics.get(key)
            if not isinstance(row, dict):
                continue
            value = to_float(row.get("value"))
            if value is None or not (lo <= value <= hi):
                raise ValueError(f"{key}.value out of plausible range")
            snap["metrics"][key] = metric(
                fmt_number(value, 2 if key != "tx" else 0),
                _intraday_change(row),
                row_asof(row),
                "licensed_intraday",
                row_source(row),
            )

        # Turnover: accept TWD amount or already formatted text.
        row = metrics.get("turnover")
        if isinstance(row, dict):
            raw = row.get("value")
            unit = str(row.get("unit") or "TWD").upper()
            if isinstance(raw, (int, float)) and unit == "TWD":
                display = f"{float(raw) / 1e8:,.0f} 億"
            else:
                display = str(raw or "N/A")
            snap["metrics"]["turnover"] = metric(
                display, _intraday_change(row), row_asof(row),
                "licensed_intraday", row_source(row)
            )

        # Breadth: prefer explicit counts, otherwise accept a display string.
        row = metrics.get("breadth")
        if isinstance(row, dict):
            up = to_int(row.get("up"))
            down = to_int(row.get("down"))
            flat = to_int(row.get("flat"))
            if up is not None and down is not None:
                if up < 0 or down < 0 or up + down > 10000:
                    raise ValueError("breadth counts out of plausible range")
                value = f"{up}↑ / {down}↓"
                change = f"平盤 {flat}" if flat is not None else ""
            else:
                value = str(row.get("value") or "N/A")
                change = str(row.get("change") or "")
            snap["metrics"]["breadth"] = metric(
                value, change, row_asof(row),
                "licensed_intraday", row_source(row)
            )

        mode_label = "即時" if mode in {"real_time", "realtime"} else ("延遲" if mode == "delayed" else "授權")
        snap["intradayFeed"] = {
            "state": "configured",
            "label": f"已啟用{mode_label}盤中資料源",
            "note": f"{vendor} · 資料時間 {feed_asof} · 公開展示依你的授權設定啟用。",
            "vendor": vendor,
            "mode": mode,
            "asOf": feed_asof,
        }
        source_ok(snap, "Licensed intraday feed", feed_asof, f"{vendor} / {mode}")
    except Exception as exc:
        snap["intradayFeed"] = {
            "state": "error",
            "label": "授權盤中資料源未通過安全檢查",
            "note": str(exc)[:250]
        }
        source_error(snap, "Licensed intraday feed", exc)



def _metric_float(text):
    import re
    s = str(text or "")
    m = re.search(r"[+-]?\d[\d,]*(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))



def _iso_day(value):
    import re
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", str(value or ""))
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def _current_directional_metric(metrics, key, benchmark_date):
    row = metrics.get(key, {}) or {}
    if row.get("state") == "stale":
        return None
    row_day = _iso_day(row.get("asOf"))
    if benchmark_date and row_day and row_day < benchmark_date:
        return None
    return _metric_float(row.get("value"))

def calculate_risk(snap):
    """Build a transparent 0-100 risk-appetite score from available data.

    50 = neutral; higher = more risk-on; lower = more risk-off.
    Only comparable directional indicators are scored. Put/Call and absolute
    USD/TWD levels are intentionally excluded from the numeric score because
    they require context and should not be interpreted mechanically.
    """
    metrics = snap.get("metrics", {})
    components = []

    def add(name, score, weight, reason):
        if score is None:
            return
        components.append({
            "name": name,
            "score": round(_clamp(score), 1),
            "weight": weight,
            "reason": reason,
        })

    benchmark_date = _iso_day(metrics.get("taiex", {}).get("asOf"))
    taiex_pct = _metric_float(metrics.get("taiex", {}).get("change"))
    if taiex_pct is not None:
        add("TAIEX", 50 + taiex_pct * 12, 18, f"收盤 {taiex_pct:+.2f}%")

    otc_pct = _metric_float(metrics.get("otc", {}).get("change")) if _current_directional_metric(metrics, "otc", benchmark_date) is not None else None
    if otc_pct is not None:
        add("櫃買", 50 + otc_pct * 10, 12, f"收盤 {otc_pct:+.2f}%")

    tx_pct = _metric_float(metrics.get("tx", {}).get("change")) if _current_directional_metric(metrics, "tx", benchmark_date) is not None else None
    if tx_pct is not None:
        add("臺指期", 50 + tx_pct * 10, 10, f"TX {tx_pct:+.2f}%")

    breadth = str(metrics.get("breadth", {}).get("value", ""))
    import re
    m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", breadth)
    if m:
        up = int(m.group(1).replace(",", ""))
        down = int(m.group(2).replace(",", ""))
        total = up + down
        if total > 0:
            ratio = up / total
            add("市場廣度", ratio * 100, 20, f"上漲比 {ratio*100:.1f}%")

    foreign_spot = _current_directional_metric(metrics, "foreignSpot", benchmark_date)
    if foreign_spot is not None:
        add("外資現貨", 50 + foreign_spot / 20, 22, f"{foreign_spot:+.0f} 億")

    foreign_tx = _current_directional_metric(metrics, "foreignTx", benchmark_date)
    if foreign_tx is not None:
        add("外資TX", 50 + foreign_tx / 2500, 18, f"{foreign_tx:+,.0f} 口")

    if not components:
        snap["risk"] = {
            "score": None,
            "label": "資料不足",
            "confidence": 0,
            "components": [],
            "drivers": [],
            "note": "目前沒有足夠可比較的方向性資料。",
        }
        return

    total_weight = sum(c["weight"] for c in components)
    score = sum(c["score"] * c["weight"] for c in components) / total_weight
    score = round(_clamp(score), 1)

    if score >= 70:
        label = "Risk-On"
    elif score >= 55:
        label = "偏多"
    elif score >= 45:
        label = "Neutral"
    elif score >= 30:
        label = "偏空"
    else:
        label = "Risk-Off"

    # Confidence reflects how much of the intended 100-point model is populated.
    confidence = round(min(100, total_weight), 0)

    ranked = sorted(
        components,
        key=lambda c: abs(c["score"] - 50) * c["weight"],
        reverse=True,
    )
    drivers = [
        {
            "name": c["name"],
            "direction": "positive" if c["score"] > 55 else ("negative" if c["score"] < 45 else "neutral"),
            "reason": c["reason"],
            "score": c["score"],
        }
        for c in ranked[:4]
    ]

    snap["risk"] = {
        "score": score,
        "label": label,
        "confidence": confidence,
        "components": components,
        "drivers": drivers,
        "note": "研究用綜合分數；Put/Call、匯率與槓桿不以單一絕對值機械計分。",
    }

def preserve_last_valid(snap):
    old = read_json(DATA_DIR / "live.json", {})
    old_metrics = old.get("metrics", {}) if isinstance(old, dict) else {}
    for key, row in snap["metrics"].items():
        if row.get("value") == "N/A":
            previous = old_metrics.get(key)
            if isinstance(previous, dict) and previous.get("value") not in {None, "", "N/A"}:
                saved = dict(previous)
                saved["state"] = "stale"
                saved["change"] = (saved.get("change", "") + " · 本次抓取未更新").strip(" ·")
                snap["metrics"][key] = saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["intraday", "afterhours", "manual"], default="manual")
    args = parser.parse_args()

    snap = blank_snapshot(args.kind)
    # Official open data is always checked. During trading hours it usually remains the previous official snapshot.
    fetch_twse_close(snap)
    fetch_twse_turnover(snap)
    fetch_twse_breadth(snap)
    # After the close, prefer TWSE's explicit date-targeted RWD endpoints.
    # This prevents a lagging OpenAPI snapshot from leaving Friday data on Monday night.
    fetch_twse_same_day_close(snap, args.kind)
    fetch_tpex_summary(snap)
    fetch_cbc(snap)
    fetch_taifex(snap)
    if args.kind in {"afterhours", "manual"}:
        fetch_twse_institutional(snap)
        fetch_margin(snap)
        fetch_twse_same_day_afterhours(snap, args.kind)
    if args.kind == "intraday":
        fetch_intraday_feed(snap)

    preserve_last_valid(snap)
    calculate_risk(snap)
    atomic_write_json(DATA_DIR / "live.json", snap)
    append_history(snap)
    archive_snapshot(snap)
    print(f"updated {DATA_DIR / 'live.json'} ({args.kind}) with {len(snap['errors'])} source errors")


if __name__ == "__main__":
    main()
