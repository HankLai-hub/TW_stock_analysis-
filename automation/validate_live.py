from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_PATH = ROOT / "data" / "live.json"
VALIDATION_PATH = ROOT / "data" / "live-validation.json"
HISTORY_DIR = ROOT / "history"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 用來推斷「目前市場交易日」的主要市場資料。
# USD/TWD 不納入，因為其交易日與台股不一定完全同步。
MARKET_REFERENCE_KEYS = (
    "taiex",
    "otc",
    "breadth",
    "tx",
)

# 需要進行 freshness 檢查的重要台股資料。
MARKET_FRESHNESS_KEYS = (
    "taiex",
    "otc",
    "turnover",
    "breadth",
    "tx",
    "foreignSpot",
    "foreignTx",
    "putCall",
    "margin",
)


def load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def parse_iso_date(value) -> date | None:
    text = str(value or "").strip()

    if not DATE_RE.fullmatch(text):
        return None

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def pct(text):
    match = re.search(
        r"([+-]?[\d.]+)%",
        str(text or ""),
    )

    return (
        float(match.group(1))
        if match
        else None
    )


def previous_weekday(day: date) -> date:
    """
    Fallback only.

    可以處理週末，但不能完整辨識台灣國定假日。
    若 repo history 有實際交易日，會優先使用 history。
    """
    candidate = day - timedelta(days=1)

    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)

    return candidate


def collect_observed_trading_days() -> set[date]:
    """
    從 history 裡實際出現過的 TAIEX 日期，
    推導曾經確認過的交易日。
    """
    days: set[date] = set()

    if not HISTORY_DIR.exists():
        return days

    for path in HISTORY_DIR.rglob("*.json"):
        try:
            payload = load_json(path)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        metrics = payload.get("metrics")

        if not isinstance(metrics, dict):
            continue

        taiex = metrics.get("taiex")

        if not isinstance(taiex, dict):
            continue

        observed = parse_iso_date(
            taiex.get("asOf")
        )

        if observed is not None:
            days.add(observed)

    return days


def previous_observed_trading_day(
    current_day: date,
    observed_days: set[date],
) -> date:
    candidates = [
        day
        for day in observed_days
        if day < current_day
    ]

    if candidates:
        return max(candidates)

    return previous_weekday(current_day)


def extract_metric_dates(
    metrics: dict,
    keys,
) -> dict[str, date]:
    result: dict[str, date] = {}

    for key in keys:
        row = metrics.get(key)

        if not isinstance(row, dict):
            continue

        parsed = parse_iso_date(
            row.get("asOf")
        )

        if parsed is not None:
            result[key] = parsed

    return result


def infer_market_reference_day(
    metrics: dict,
) -> tuple[date | None, str]:
    """
    從多個市場來源推斷目前已被資料確認的市場日期。

    規則：
    1. 若最新日期至少被兩個主要來源支持，採最新日期。
    2. 否則採主要來源中出現次數最多的日期。
    3. 同票時採較新的日期。

    這樣可以避免單一錯誤來源把整個市場日期往前推。
    """

    dates = extract_metric_dates(
        metrics,
        MARKET_REFERENCE_KEYS,
    )

    if not dates:
        return None, "unavailable"

    counts = Counter(
        dates.values()
    )

    latest_day = max(counts)

    if counts[latest_day] >= 2:
        return latest_day, "confirmed-latest"

    reference_day = max(
        counts,
        key=lambda day: (
            counts[day],
            day,
        ),
    )

    return reference_day, "majority"


def classify_turnover_freshness(
    taiex_day: date,
    turnover_day: date,
    observed_days: set[date],
) -> tuple[str, str]:
    if turnover_day == taiex_day:
        return (
            "fresh",
            "TAIEX 與成交金額為同一交易日。",
        )

    if turnover_day > taiex_day:
        return (
            "error",
            (
                "成交金額日期晚於 TAIEX："
                f"{turnover_day.isoformat()} > "
                f"{taiex_day.isoformat()}"
            ),
        )

    previous_trading_day = (
        previous_observed_trading_day(
            taiex_day,
            observed_days,
        )
    )

    if turnover_day == previous_trading_day:
        return (
            "warning",
            (
                "成交金額資料落後 1 個交易日；"
                f"TAIEX={taiex_day.isoformat()}，"
                f"turnover={turnover_day.isoformat()}。"
                "暫時使用最近可用值。"
            ),
        )

    return (
        "error",
        (
            "成交金額資料超過允許的 T-1 範圍；"
            f"TAIEX={taiex_day.isoformat()}，"
            f"turnover={turnover_day.isoformat()}，"
            "允許的上一交易日="
            f"{previous_trading_day.isoformat()}。"
        ),
    )


def classify_market_metric_freshness(
    *,
    key: str,
    metric_day: date,
    reference_day: date,
    observed_days: set[date],
) -> tuple[str, str | None]:
    """
    將各市場指標與已推斷出的市場 reference day 比較。
    """

    if metric_day == reference_day:
        return "fresh", None

    if metric_day > reference_day:
        return (
            "warning",
            (
                f"{key} 日期 {metric_day.isoformat()} "
                f"晚於市場基準日 {reference_day.isoformat()}。"
            ),
        )

    previous_day = previous_observed_trading_day(
        reference_day,
        observed_days,
    )

    if metric_day == previous_day:
        return (
            "warning",
            (
                f"{key} 資料為 T-1；"
                f"目前={metric_day.isoformat()}，"
                f"市場基準={reference_day.isoformat()}。"
            ),
        )

    return (
        "error",
        (
            f"{key} 資料過舊；"
            f"目前={metric_day.isoformat()}，"
            f"市場基準={reference_day.isoformat()}，"
            f"允許的上一交易日="
            f"{previous_day.isoformat()}。"
        ),
    )


def write_validation_status(
    *,
    status: str,
    warnings: list[str],
    errors: list[str],
    details: dict,
):
    payload = {
        "schemaVersion": 1,
        "generatedAt": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "details": details,
    }

    VALIDATION_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    VALIDATION_PATH.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def validate_live():
    obj = load_json(
        LIVE_PATH
    )

    assert obj.get("schemaVersion") == 1
    assert obj.get("generatedAt")
    assert isinstance(
        obj.get("metrics"),
        dict,
    )

    required = {
        "taiex",
        "otc",
        "turnover",
        "breadth",
        "usdTwd",
        "tx",
        "foreignSpot",
        "foreignTx",
        "putCall",
        "margin",
    }

    missing = (
        required
        - set(obj["metrics"])
    )

    assert not missing, (
        f"missing live metrics: "
        f"{sorted(missing)}"
    )

    metrics = obj["metrics"]

    for key in required:
        row = metrics[key]

        assert isinstance(
            row,
            dict,
        ), f"{key}: metric must be an object"

        for field in (
            "value",
            "asOf",
            "state",
            "source",
        ):
            assert field in row, (
                f"{key}: missing {field}"
            )

    # ---------------------------------------------------------
    # Plausibility guards
    # ---------------------------------------------------------

    for key in (
        "taiex",
        "otc",
        "tx",
    ):
        percentage = pct(
            metrics[key].get(
                "change"
            )
        )

        if percentage is not None:
            assert abs(
                percentage
            ) <= 20, (
                f"{key}: implausible "
                f"daily percentage "
                f"{percentage}% "
                "(possible field mapping error)"
            )

    breadth = str(
        metrics["breadth"].get(
            "value",
            "",
        )
    )

    match = re.search(
        r"([\d,]+)↑\s*/\s*([\d,]+)↓",
        breadth,
    )

    if match:
        up = int(
            match.group(1)
            .replace(",", "")
        )

        down = int(
            match.group(2)
            .replace(",", "")
        )

        assert (
            0 <= up <= 3000
        ), (
            "breadth: implausible "
            f"advance count {up}"
        )

        assert (
            0 <= down <= 3000
        ), (
            "breadth: implausible "
            f"decline count {down}"
        )

    warnings: list[str] = []
    errors: list[str] = []

    observed_days = (
        collect_observed_trading_days()
    )

    # ---------------------------------------------------------
    # TAIEX vs turnover consistency
    # ---------------------------------------------------------

    taiex_as_of = (
        metrics["taiex"]
        .get("asOf")
    )

    turnover_as_of = (
        metrics["turnover"]
        .get("asOf")
    )

    taiex_day = parse_iso_date(
        taiex_as_of
    )

    turnover_day = parse_iso_date(
        turnover_as_of
    )

    turnover_status = "unknown"

    turnover_message = (
        "無法判斷成交金額 freshness。"
    )

    if taiex_day is not None:
        observed_days.add(
            taiex_day
        )

    if (
        taiex_day is not None
        and turnover_day is not None
    ):
        (
            turnover_status,
            turnover_message,
        ) = classify_turnover_freshness(
            taiex_day,
            turnover_day,
            observed_days,
        )

        if (
            turnover_status
            == "warning"
        ):
            warnings.append(
                turnover_message
            )

        elif (
            turnover_status
            == "error"
        ):
            errors.append(
                turnover_message
            )

    # ---------------------------------------------------------
    # Infer current market reference date
    # ---------------------------------------------------------

    (
        market_reference_day,
        market_reference_basis,
    ) = infer_market_reference_day(
        metrics
    )

    stale_market_metrics = []
    severely_stale_market_metrics = []

    metric_dates = extract_metric_dates(
        metrics,
        MARKET_FRESHNESS_KEYS,
    )

    if market_reference_day is not None:
        observed_days.add(
            market_reference_day
        )

        for key, metric_day in (
            metric_dates.items()
        ):
            (
                metric_status,
                metric_message,
            ) = (
                classify_market_metric_freshness(
                    key=key,
                    metric_day=metric_day,
                    reference_day=(
                        market_reference_day
                    ),
                    observed_days=(
                        observed_days
                    ),
                )
            )

            if metric_status == "warning":
                stale_market_metrics.append(
                    key
                )

                if metric_message:
                    warnings.append(
                        metric_message
                    )

            elif metric_status == "error":
                severely_stale_market_metrics.append(
                    key
                )

                if metric_message:
                    errors.append(
                        metric_message
                    )

    # ---------------------------------------------------------
    # Absolute-date caution
    #
    # 不直接 hard fail。
    # 若所有市場資料都停留在生成日期之前，
    # 可能是休市，也可能是資料尚未更新。
    # ---------------------------------------------------------

    generated_day = None

    generated_at = obj.get(
        "generatedAt"
    )

    try:
        generated_day = (
            datetime.fromisoformat(
                str(generated_at)
                .replace(
                    "Z",
                    "+00:00",
                )
            )
            .astimezone()
            .date()
        )
    except Exception:
        pass

    market_date_unconfirmed = False

    if (
        generated_day is not None
        and market_reference_day
        is not None
        and market_reference_day
        < generated_day
    ):
        # 週末不主動警告。
        # 平日則標示資料日期尚未能確認，
        # 但不直接中止 workflow，
        # 避免國定假日/臨時休市誤判。
        if generated_day.weekday() < 5:
            market_date_unconfirmed = True

            warnings.append(
                (
                    "目前資料的市場基準日為 "
                    f"{market_reference_day.isoformat()}，"
                    "早於本次產生日期 "
                    f"{generated_day.isoformat()}。"
                    "可能為休市、官方資料尚未更新，"
                    "或市場資料仍停留在上一交易日。"
                )
            )

    # 去除重複警告。
    warnings = list(
        dict.fromkeys(warnings)
    )

    errors = list(
        dict.fromkeys(errors)
    )

    details = {
        "taiexAsOf": (
            taiex_as_of
        ),
        "turnoverAsOf": (
            turnover_as_of
        ),
        "turnoverFreshness": (
            turnover_status
        ),
        "turnoverFreshnessMessage": (
            turnover_message
        ),
        "marketReferenceDate": (
            market_reference_day.isoformat()
            if market_reference_day
            else None
        ),
        "marketReferenceBasis": (
            market_reference_basis
        ),
        "marketDateUnconfirmed": (
            market_date_unconfirmed
        ),
        "marketMetricDates": {
            key: value.isoformat()
            for key, value
            in metric_dates.items()
        },
        "staleMarketMetrics": (
            sorted(
                set(
                    stale_market_metrics
                )
            )
        ),
        "severelyStaleMarketMetrics": (
            sorted(
                set(
                    severely_stale_market_metrics
                )
            )
        ),
        "observedTradingDays": (
            len(observed_days)
        ),
    }

    if errors:
        write_validation_status(
            status="error",
            warnings=warnings,
            errors=errors,
            details=details,
        )

        raise AssertionError(
            "; ".join(errors)
        )

    if warnings:
        write_validation_status(
            status="degraded",
            warnings=warnings,
            errors=[],
            details=details,
        )

        for warning in warnings:
            print(
                "WARNING: "
                + warning,
                file=sys.stderr,
            )

        print(
            "live.json schema + "
            "plausibility OK "
            "(degraded freshness)"
        )

        return

    write_validation_status(
        status="healthy",
        warnings=[],
        errors=[],
        details=details,
    )

    print(
        "live.json schema + "
        "plausibility OK"
    )


def run_self_tests():
    observed = {
        date(2026, 9, 18),
        date(2026, 9, 21),
        date(2026, 9, 22),
    }

    # 1. 同日
    status, _ = (
        classify_turnover_freshness(
            date(2026, 9, 22),
            date(2026, 9, 22),
            observed,
        )
    )

    assert status == "fresh"

    # 2. T-1
    status, _ = (
        classify_turnover_freshness(
            date(2026, 9, 22),
            date(2026, 9, 21),
            observed,
        )
    )

    assert status == "warning"

    # 3. 跨週末
    status, _ = (
        classify_turnover_freshness(
            date(2026, 9, 21),
            date(2026, 9, 18),
            {
                date(2026, 9, 18),
                date(2026, 9, 21),
            },
        )
    )

    assert status == "warning"

    # 4. 超過一個交易日
    status, _ = (
        classify_turnover_freshness(
            date(2026, 9, 22),
            date(2026, 9, 18),
            observed,
        )
    )

    assert status == "error"

    # 5. 市場 reference：兩個來源支持最新日期
    reference, basis = (
        infer_market_reference_day(
            {
                "taiex": {
                    "asOf": "2026-09-21",
                },
                "otc": {
                    "asOf": "2026-09-21",
                },
                "breadth": {
                    "asOf": "2026-09-22",
                },
                "tx": {
                    "asOf": "2026-09-22",
                },
            }
        )
    )

    assert reference == date(
        2026,
        9,
        22,
    )

    assert basis == (
        "confirmed-latest"
    )

    # 6. 指標相對市場日為 T-1
    status, _ = (
        classify_market_metric_freshness(
            key="taiex",
            metric_day=date(
                2026,
                9,
                21,
            ),
            reference_day=date(
                2026,
                9,
                22,
            ),
            observed_days=observed,
        )
    )

    assert status == "warning"

    print(
        "validate_live self-tests OK"
    )


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_tests()
    else:
        validate_live()