from __future__ import annotations

import argparse
import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from common import (
    DATA_DIR, append_history, archive_snapshot, atomic_write_json, find_value,
    fmt_number, fmt_pct, http_json, iso_now, metric, now_taipei, read_json,
    row_date, signed_number, to_float, to_int,
)

TWSE = "https://openapi.twse.com.tw/v1"
TWSE_WEB = "https://www.twse.com.tw/rwd/zh"
TPEX = "https://www.tpex.org.tw/openapi/v1"
TAIFEX = "https://openapi.taifex.com.tw/v1"
CBC = "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=BP01D01"


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


def fetch_twse_close(snap):
    try:
        rows = http_json(f"{TWSE}/exchangeReport/MI_INDEX")
        if not isinstance(rows, list):
            raise ValueError("MI_INDEX did not return a list")
        row = next((r for r in rows if "發行量加權" in str(find_value(r, ["指數", "Index"]) or "")), None)
        if not row:
            raise ValueError("TAIEX row not found")
        value = to_float(find_value(row, ["收盤指數", "ClosingIndex", "IndexValue"]))
        pct = signed_number(find_value(row, ["漲跌百分比", "ChangePercent", "ChangePercentage"]), find_value(row, ["漲跌", "Direction"]))
        date = None
        try:
            fmt = http_json(f"{TWSE}/exchangeReport/FMTQIK")
            if isinstance(fmt, list) and fmt:
                date = row_date(fmt[0])
        except Exception:
            pass
        snap["metrics"]["taiex"] = metric(fmt_number(value), fmt_pct(pct), date or "最新官方收盤", "official_close", "TWSE")
        source_ok(snap, "TWSE MI_INDEX", date or "最新官方收盤")
    except Exception as exc:
        source_error(snap, "TWSE MI_INDEX", exc)


def fetch_twse_breadth(snap):
    try:
        rows = http_json(f"{TWSE}/opendata/twtazu_od")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty breadth payload")
        row = rows[0]
        up = to_int(find_value(row, ["上漲家數", "上漲", "Up", "Advance", "Advancers"]))
        down = to_int(find_value(row, ["下跌家數", "下跌", "Down", "Decline", "Decliners"]))
        flat = to_int(find_value(row, ["持平家數", "持平", "Unchanged"]))
        date = row_date(row) or "最新官方收盤"
        if up is None or down is None:
            # Preserve endpoint availability even if a future schema rename needs a map update.
            raise ValueError(f"breadth fields not recognized: {list(row)[:12]}")
        value = f"{up}↑ / {down}↓"
        change = f"平盤 {flat}" if flat is not None else ""
        snap["metrics"]["breadth"] = metric(value, change, date, "official_close", "TWSE")
        source_ok(snap, "TWSE breadth", date)
    except Exception as exc:
        source_error(snap, "TWSE breadth", exc)


def fetch_twse_turnover(snap):
    try:
        rows = http_json(f"{TWSE}/exchangeReport/FMTQIK")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty FMTQIK")
        row = rows[0]
        amount = to_float(find_value(row, ["成交金額", "TradeValue", "成交值"]))
        date = row_date(row) or "最新官方收盤"
        value = f"{amount / 1e8:,.0f} 億" if amount is not None else "N/A"
        snap["metrics"]["turnover"] = metric(value, "", date, "official_close", "TWSE")
        source_ok(snap, "TWSE turnover", date)
    except Exception as exc:
        source_error(snap, "TWSE turnover", exc)


def fetch_tpex_summary(snap):
    try:
        rows = http_json(f"{TPEX}/tpex_mainborad_highlight")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty TPEx highlight")
        # TPEx highlight contains market summary in a small latest-day snapshot.
        row = rows[0]
        date = row_date(row) or "最新官方收盤"
        value = to_float(find_value(row, ["Close", "Index", "IndexValue", "收盤指數", "指數"]))
        pct = signed_number(find_value(row, ["ChangePercent", "ChangePercentage", "漲跌幅", "漲跌百分比"]))
        if value is None:
            # Try dedicated index endpoint; keep flexible because the endpoint can return several indices.
            idx = http_json(f"{TPEX}/tpex_index")
            if isinstance(idx, list):
                candidate = next((r for r in idx if "櫃買" in str(r) or "TPEX" in str(r).upper()), idx[0] if idx else None)
                if candidate:
                    value = to_float(find_value(candidate, ["Close", "Index", "IndexValue", "收盤指數", "指數值"]))
                    pct = signed_number(find_value(candidate, ["ChangePercent", "漲跌幅", "漲跌百分比"]))
                    date = row_date(candidate) or date
        if value is None:
            raise ValueError(f"TPEx index field not recognized: {list(row)[:12]}")
        snap["metrics"]["otc"] = metric(fmt_number(value), fmt_pct(pct), date, "official_close", "TPEx")

        # When the highlight endpoint provides breadth counts, merge them with the already-fetched TWSE counts.
        tpex_up = to_int(find_value(row, ["上漲家數", "UpCount", "Advancers", "RiseCount", "RisingStocks"]))
        tpex_down = to_int(find_value(row, ["下跌家數", "DownCount", "Decliners", "FallCount", "FallingStocks"]))
        tpex_flat = to_int(find_value(row, ["持平家數", "FlatCount", "Unchanged", "UnchangedCount"]))
        if tpex_up is not None and tpex_down is not None:
            current = snap["metrics"].get("breadth", {})
            import re
            m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", str(current.get("value", "")))
            if m:
                twse_up = int(m.group(1).replace(",", "")); twse_down = int(m.group(2).replace(",", ""))
                flat_m = re.search(r"平盤\s*([\d,]+)", str(current.get("change", "")))
                twse_flat = int(flat_m.group(1).replace(",", "")) if flat_m else 0
                flat_total = twse_flat + (tpex_flat or 0)
                snap["metrics"]["breadth"] = metric(
                    f"{twse_up + tpex_up}↑ / {twse_down + tpex_down}↓",
                    f"平盤 {flat_total}",
                    date, "official_close", "TWSE/TPEx"
                )
        source_ok(snap, "TPEx market summary", date)
    except Exception as exc:
        source_error(snap, "TPEx market summary", exc)


def fetch_cbc(snap):
    try:
        payload = http_json(CBC)
        dataset = payload.get("DataSet") if isinstance(payload, dict) else None
        rows = dataset if isinstance(dataset, list) else (dataset.get("Data") if isinstance(dataset, dict) else None)
        if not isinstance(rows, list) or not rows:
            raise ValueError("CBC dataset shape not recognized")
        # BP01D01 has many currencies. Identify USD/TWD row/column flexibly.
        latest = rows[-1]
        if isinstance(latest, dict):
            date = row_date(latest) or str(find_value(latest, ["Period", "時間", "日期"]) or "最新官方資料")
            value = to_float(find_value(latest, ["新臺幣", "新台幣", "NTD", "TWD", "NTD/USD", "USD/TWD"]))
            if value is None:
                nums = [to_float(v) for k, v in latest.items() if k not in {"TIME_PERIOD", "Period", "日期"}]
                nums = [x for x in nums if x is not None and 20 <= x <= 50]
                value = nums[0] if nums else None
        else:
            value = None; date = "最新官方資料"
        if value is None:
            raise ValueError("USD/TWD value not recognized")
        snap["metrics"]["usdTwd"] = metric(fmt_number(value, 3), "", date, "official_daily", "CBC")
        source_ok(snap, "CBC USD/TWD", date)
    except Exception as exc:
        source_error(snap, "CBC USD/TWD", exc)


def fetch_twse_institutional(snap):
    try:
        url = f"{TWSE_WEB}/fund/BFI82U?{urlencode({'response':'json','type':'day'})}"
        payload = http_json(url)
        fields = payload.get("fields", []) if isinstance(payload, dict) else []
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not fields or not data:
            raise ValueError("BFI82U no fields/data")
        rows = [dict(zip(fields, r)) for r in data]
        row = next((r for r in rows if "外資及陸資" in str(find_value(r, ["單位名稱", "名稱"]) or "") and "自營商" not in str(find_value(r, ["單位名稱", "名稱"]) or "")), None)
        if not row:
            raise ValueError("foreign investor row not found")
        net = to_float(find_value(row, ["買賣差額", "買賣超金額", "差額"]))
        date_raw = payload.get("date") or payload.get("title") or "最新官方盤後"
        date = str(date_raw)
        value = f"{net / 1e8:+,.2f} 億" if net is not None else "N/A"
        snap["metrics"]["foreignSpot"] = metric(value, "上市市場", date, "official_afterhours", "TWSE")
        source_ok(snap, "TWSE BFI82U", date)
    except Exception as exc:
        source_error(snap, "TWSE BFI82U", exc)


def fetch_margin(snap):
    """Fetch market-level margin data without mixing incompatible units.

    TWSE's market summary exposes 融資金額 in thousand NTD; that is converted to 億元.
    TPEx's public OpenAPI exposes per-security margin balance in trading units/shares, so it
    is shown separately as a supplemental quantity rather than added to TWSE money balance.
    """
    twse_amount_100m = None
    tpex_units = None
    dates = []

    try:
        payload = http_json("https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&selectType=MS")
        fields = payload.get("creditFields", []) if isinstance(payload, dict) else []
        data = payload.get("creditList", []) if isinstance(payload, dict) else []
        if not fields or not data:
            raise ValueError("TWSE MI_MARGN market summary missing creditFields/creditList")

        rows = [dict(zip(fields, row)) for row in data]
        amount_row = next(
            (r for r in rows if "融資金額" in str(find_value(r, ["項目", "Item", fields[0]]) or "")),
            None,
        )
        if not amount_row:
            raise ValueError("TWSE margin amount row not found")

        today = to_float(find_value(amount_row, ["今日餘額", "TodayBalance", "餘額"]))
        if today is None:
            # Field names have changed before; fall back to the last numeric column in the row.
            nums = [to_float(v) for k, v in amount_row.items() if k != fields[0]]
            nums = [v for v in nums if v is not None]
            today = nums[-1] if nums else None
        if today is None:
            raise ValueError("TWSE margin balance not recognized")

        # Official field is 千元. 1 億元 = 100,000 千元.
        twse_amount_100m = today / 100000.0
        date = str(payload.get("date") or payload.get("stat") or "最新官方盤後")
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
        if twse_amount_100m is not None:
            value = f"上市 {twse_amount_100m:,.2f} 億"
        else:
            value = "上市 N/A"
        change = f"上櫃融資餘額 {tpex_units:,.0f}（來源原始交易單位）" if tpex_units is not None else "上櫃 N/A"
        snap["metrics"]["margin"] = metric(
            value,
            change,
            max(dates) if dates else "最新官方盤後",
            "official_afterhours",
            "TWSE / TPEx",
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
        last = to_float(find_value(row, ["Last", "LastPrice", "最後成交價"]))
        pct = signed_number(find_value(row, ["ChangePercent", "漲跌%", "漲跌幅"]))
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
