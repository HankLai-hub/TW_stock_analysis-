from __future__ import annotations

import argparse
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from common import (
    DATA_DIR, append_history, archive_snapshot, atomic_write_json, find_exact, find_value,
    fmt_number, fmt_pct, http_json, http_text, iso_now, metric, now_taipei, read_json,
    row_date, signed_number, to_float, to_int,
)

TWSE = "https://openapi.twse.com.tw/v1"
TWSE_WEB = "https://www.twse.com.tw/rwd/zh"
TPEX = "https://www.tpex.org.tw/openapi/v1"
TAIFEX = "https://openapi.taifex.com.tw/v1"
CBC = "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=BP01D01"
CBC_CSV = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/BP01D01.csv"


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
    if kind == "intraday":
        return "下一個盤中整點排程約 60 分鐘後"
    if kind == "afterhours":
        return "下一個盤後排程約 3 小時後"
    return "依 GitHub Actions 排程"


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

def fetch_tpex_summary(snap):
    try:
        rows = http_json(f"{TPEX}/tpex_daily_trading_index")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx daily trading index")
        row = _latest_dated_row(rows)
        date = row_date(row) or "最新官方收盤"
        value = to_float(find_exact(row, ["Close", "Index", "IndexValue", "收盤指數", "指數", "ClosingIndex"]))
        change_pts = signed_number(find_exact(row, ["Change", "漲跌", "ChangePoint"]))
        pct = to_float(find_exact(row, ["ChangePercent", "ChangePercentage", "漲跌幅", "漲跌百分比"]))
        if pct is None and value is not None and change_pts is not None and (value - change_pts) != 0:
            pct = change_pts / (value - change_pts) * 100
        if value is None:
            raise ValueError(f"TPEx index field not recognized: {list(row)[:16]}")
        snap["metrics"]["otc"] = metric(fmt_number(value), fmt_pct(pct), date, "official_close", "TPEx")
        source_ok(snap, "TPEx daily trading index", date)
    except Exception as exc:
        source_error(snap, "TPEx daily trading index", exc)

    # Add TPEx stock breadth to the TWSE stock breadth only when the official
    # highlight endpoint exposes unambiguous daily counts for the same date.
    try:
        rows = http_json(f"{TPEX}/tpex_mainborad_highlight")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx highlight")
        row = _latest_dated_row(rows) or rows[0]
        date = row_date(row) or "最新官方收盤"
        up = to_int(find_exact(row, ["UpNum", "RiseNum", "RisingStocks", "上漲家數"]))
        down = to_int(find_exact(row, ["DownNum", "FallNum", "FallingStocks", "下跌家數"]))
        flat = to_int(find_exact(row, ["NoChangeNum", "FlatNum", "Unchanged", "持平家數"]))
        current = snap["metrics"].get("breadth", {})
        if up is not None and down is not None and current.get("value") not in {None, "", "N/A"}:
            import re
            m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", str(current.get("value", "")))
            if m and str(current.get("asOf")) == date:
                twse_up = int(m.group(1).replace(",", "")); twse_down = int(m.group(2).replace(",", ""))
                flat_m = re.search(r"平盤\s*([\d,]+)", str(current.get("change", "")))
                twse_flat = int(flat_m.group(1).replace(",", "")) if flat_m else 0
                snap["metrics"]["breadth"] = metric(
                    f"{twse_up + up}↑ / {twse_down + down}↓",
                    f"平盤 {twse_flat + (flat or 0)}",
                    date, "official_close", "TWSE/TPEx 股票"
                )
        source_ok(snap, "TPEx market highlight", date)
    except Exception as exc:
        source_error(snap, "TPEx market highlight", exc)

def fetch_cbc(snap):
    """Fetch USD/TWD from the CBC official open-data CSV.

    The newer CBC DataAPI wraps observations in a multidimensional structure that
    has changed over time.  The official CSV is simpler, documented by the CBC,
    and contains the same BP01D01 daily series.
    """
    import csv
    import io
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
            if f is not None and iso:
                candidates.append((iso, f))
        if not candidates:
            raise ValueError(f"CBC BP01D01 columns not recognized: {list(rows[0])[:12]}")
        candidates.sort(key=lambda x: x[0])
        date, value = candidates[-1]
        snap["metrics"]["usdTwd"] = metric(fmt_number(value, 3), "", date, "official_daily", "CBC")
        source_ok(snap, "CBC USD/TWD", date, "BP01D01 official CSV")
    except Exception as exc:
        source_error(snap, "CBC USD/TWD", exc)

def _roc_date_from_text(text: str) -> str | None:
    import re
    m = re.search(r"(?:民國)?\s*(\d{3})[年/-](\d{1,2})[月/-](\d{1,2})", str(text or ""))
    if m:
        return f"{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(text or ""))
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def fetch_twse_institutional(snap):
    """Fetch TWSE foreign-investor net trading from the official CSV export.

    Parsing by row text is intentionally tolerant of TWSE's 2026 label changes
    (for example the addition of the Foreign Dealers row).
    """
    import csv
    import io
    try:
        url = f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'csv','type':'day'})}"
        text = http_text(url, accept="text/csv,text/plain,*/*")
        parsed = list(csv.reader(io.StringIO(text)))
        if not parsed:
            raise ValueError("BFI82U CSV empty")

        date = _roc_date_from_text(text) or "最新官方盤後"
        target = None
        for row in parsed:
            joined = " ".join(str(x) for x in row)
            if "外資及陸資" in joined and "外資自營商" not in joined and "合計" not in joined:
                target = row
                break
        if not target:
            raise ValueError("foreign investor row not found in official CSV")

        nums = [to_float(v) for v in target[1:]]
        nums = [v for v in nums if v is not None]
        if not nums:
            raise ValueError(f"foreign investor numeric fields not recognized: {target}")
        net = nums[-1]
        value = f"{net / 1e8:+,.2f} 億"
        snap["metrics"]["foreignSpot"] = metric(value, "上市市場", date, "official_afterhours", "TWSE")
        source_ok(snap, "TWSE BFI82U", date, "official CSV")
    except Exception as exc:
        source_error(snap, "TWSE BFI82U", exc)


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

    try:
        rows = http_json(f"{TPEX}/tpex_mainboard_margin_balance")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx margin payload")
        balances = []
        tpex_dates = []
        for r in rows:
            val = to_float(find_value(r, [
                "MarginPurchaseTodayBalance", "MarginPurchaseBalance",
                "融資今日餘額", "融資餘額", "MarginPurchaseBalanceToday",
            ]))
            if val is not None:
                balances.append(val)
            d = row_date(r)
            if d:
                tpex_dates.append(d)
        if balances:
            tpex_units = sum(balances)
        if tpex_dates:
            dates.extend(tpex_dates)
        source_ok(snap, "TPEx margin", max(tpex_dates) if tpex_dates else "最新官方盤後", "交易單位/股數口徑，不與億元相加")
    except Exception as exc:
        source_error(snap, "TPEx margin", exc)

    if twse_amount_100m is not None or tpex_units is not None:
        value = f"上市 {twse_amount_100m:,.2f} 億" if twse_amount_100m is not None else "上市 N/A"
        change = f"上櫃融資餘額 {tpex_units:,.0f}（來源原始交易單位）" if tpex_units is not None else "上櫃 N/A"
        snap["metrics"]["margin"] = metric(
            value, change, max(dates) if dates else "最新官方盤後",
            "official_afterhours", "TWSE / TPEx",
        )

def fetch_taifex(snap):
    try:
        rows = http_json(f"{TAIFEX}/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")
        if not isinstance(rows, list):
            raise ValueError("TAIFEX institutional endpoint not list")
        row = next((r for r in rows if str(find_value(r, ["ContractCode", "商品名稱", "Contract"]) or "").strip() in {"臺股期貨", "TX"} and "外資" in str(find_value(r, ["Item", "身份別", "Identity"]) or "")), None)
        if not row:
            raise ValueError("TX foreign row not found")
        net = to_int(find_value(row, ["OpenInterest(Net)", "OpenInterestNet", "未平倉多空淨額", "未平倉淨額"]))
        long_oi = to_int(find_value(row, ["OpenInterest(Long)", "OpenInterestLong", "多方未平倉"]))
        short_oi = to_int(find_value(row, ["OpenInterest(Short)", "OpenInterestShort", "空方未平倉"]))
        date = row_date(row) or "最新官方盤後"
        value = f"{net:+,} 口" if net is not None else "N/A"
        detail = f"多 {long_oi:,} / 空 {short_oi:,}" if long_oi is not None and short_oi is not None else ""
        snap["metrics"]["foreignTx"] = metric(value, detail, date, "official_afterhours", "TAIFEX")
        source_ok(snap, "TAIFEX institutional TX", date)
    except Exception as exc:
        source_error(snap, "TAIFEX institutional TX", exc)

    try:
        rows = http_json(f"{TAIFEX}/PutCallRatio")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty PutCallRatio")
        row = rows[0]
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


def fetch_intraday_feed(snap):
    url = os.environ.get("INTRADAY_FEED_URL", "").strip()
    token = os.environ.get("INTRADAY_FEED_TOKEN", "").strip() or None
    if not url:
        return
    try:
        payload = http_json(url, token=token)
        if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
            metrics = payload["metrics"]
        elif isinstance(payload, dict):
            metrics = payload
        else:
            raise ValueError("licensed feed payload must be a JSON object")
        mapping = {
            "taiex": "taiex", "otc": "otc", "tx": "tx", "turnover": "turnover", "breadth": "breadth"
        }
        for src_key, dst_key in mapping.items():
            row = metrics.get(src_key)
            if isinstance(row, dict):
                snap["metrics"][dst_key] = metric(
                    str(row.get("value", "N/A")), str(row.get("change", "")),
                    str(row.get("asOf", snap["generatedAt"])), "licensed_intraday", str(row.get("source", "Licensed feed"))
                )
        snap["intradayFeed"] = {"state": "configured", "label": "已啟用授權盤中資料源", "note": "盤中欄位依你設定的供應商資料與授權範圍顯示。"}
        source_ok(snap, "Licensed intraday feed", snap["generatedAt"])
    except Exception as exc:
        snap["intradayFeed"] = {"state": "error", "label": "授權盤中資料源抓取失敗", "note": str(exc)[:250]}
        source_error(snap, "Licensed intraday feed", exc)


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
    fetch_tpex_summary(snap)
    fetch_cbc(snap)
    fetch_taifex(snap)
    if args.kind in {"afterhours", "manual"}:
        fetch_twse_institutional(snap)
        fetch_margin(snap)
    if args.kind == "intraday":
        fetch_intraday_feed(snap)

    preserve_last_valid(snap)
    atomic_write_json(DATA_DIR / "live.json", snap)
    append_history(snap)
    archive_snapshot(snap)
    print(f"updated {DATA_DIR / 'live.json'} ({args.kind}) with {len(snap['errors'])} source errors")


if __name__ == "__main__":
    main()
