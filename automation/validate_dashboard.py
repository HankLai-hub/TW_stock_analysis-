#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

DASHBOARD_PATH = DATA / "daily-dashboard.json"
LIVE_VALIDATION_PATH = DATA / "live-validation.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# Dashboard 顯示名稱 → live.json metric key
CRITICAL_METRIC_MAP = {
    "TAIEX": "taiex",
    "櫃買": "otc",
    "外資現貨": "foreignSpot",
    "外資 TX": "foreignTx",
    "Put/Call": "putCall",
    "USD/TWD": "usdTwd",
    "市場廣度": "breadth",
}

OPTIONAL_FIELDS = {
    "投信",
    "自營商",
    "融券",
    "借券賣出",
}


def load_json(path: Path, default):
    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return default


def parse_date(value) -> date | None:
    text = str(value or "").strip()

    if not DATE_RE.fullmatch(text):
        return None

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def previous_weekday(day: date) -> date:
    candidate = day - timedelta(days=1)

    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)

    return candidate


def stale_description(row: dict) -> str:
    return (
        f"{row.get('name')}"
        f"({row.get('date')})"
    )


def classify_critical_stale(
    *,
    row: dict,
    validation_status: str,
    validation_details: dict,
) -> tuple[str, str]:
    """
    Returns:
        ("warning", message)
        ("error", message)

    Dashboard 不自行重新發明完整交易日規則，
    優先沿用 validate_live.py 已產生的 freshness policy。
    """

    name = str(
        row.get("name") or ""
    ).strip()

    metric_key = CRITICAL_METRIC_MAP.get(
        name
    )

    metric_day = parse_date(
        row.get("date")
    )

    market_reference_day = parse_date(
        validation_details.get(
            "marketReferenceDate"
        )
    )

    market_date_unconfirmed = bool(
        validation_details.get(
            "marketDateUnconfirmed"
        )
    )

    stale_market_metrics = set(
        validation_details.get(
            "staleMarketMetrics"
        )
        or []
    )

    severely_stale_market_metrics = set(
        validation_details.get(
            "severelyStaleMarketMetrics"
        )
        or []
    )

    # -----------------------------------------------------
    # Hard-fail conditions
    # -----------------------------------------------------

    if validation_status == "error":
        return (
            "error",
            (
                f"{name} 為 stale，且 live validation "
                "目前為 error。"
            ),
        )

    if (
        metric_key
        and metric_key
        in severely_stale_market_metrics
    ):
        return (
            "error",
            (
                f"{name} 資料已超過允許的 freshness "
                f"範圍：{row.get('date')}"
            ),
        )

    # -----------------------------------------------------
    # Degraded / tolerated conditions
    # -----------------------------------------------------

    if validation_status == "degraded":

        # validate_live 已明確判定此 metric 為 T-1。
        if (
            metric_key
            and metric_key
            in stale_market_metrics
        ):
            return (
                "warning",
                (
                    f"{name} 使用 T-1 / 延遲資料 "
                    f"({row.get('date')})，"
                    "live validation 已判定仍可使用。"
                ),
            )

        # 市場最新交易日目前尚無法確認。
        # 常見於官方資料尚未全部刷新、休市日、
        # 假日或資料源更新時間差。
        if market_date_unconfirmed:

            if (
                metric_day is not None
                and market_reference_day
                is not None
            ):
                if metric_day == market_reference_day:
                    return (
                        "warning",
                        (
                            f"{name} 標記為 stale，"
                            f"資料日期={metric_day.isoformat()}；"
                            "目前最新市場交易日尚未確認，"
                            "暫時保留最近可用值。"
                        ),
                    )

                previous_day = (
                    previous_weekday(
                        market_reference_day
                    )
                )

                if metric_day == previous_day:
                    return (
                        "warning",
                        (
                            f"{name} 為上一個平日資料 "
                            f"({metric_day.isoformat()})；"
                            "目前市場交易日尚未確認，"
                            "暫時保留最近可用值。"
                        ),
                    )

            # 沒有可解析日期時，不直接放行。
            return (
                "error",
                (
                    f"{name} 為 stale，"
                    "且無法確認其日期是否仍在"
                    "允許 freshness 範圍內。"
                ),
            )

        # validation 已 degraded，
        # 且資料日期等於市場 reference date。
        if (
            metric_day is not None
            and market_reference_day
            is not None
            and metric_day
            == market_reference_day
        ):
            return (
                "warning",
                (
                    f"{name} 被 dashboard 標記為 stale，"
                    f"但資料日期 "
                    f"{metric_day.isoformat()} "
                    "仍等於目前市場基準日；"
                    "以 degraded 狀態繼續發布。"
                ),
            )

        # USD/TWD 不屬於台股交易日 reference，
        # 可容忍相對市場基準日 T-1。
        if (
            name == "USD/TWD"
            and metric_day is not None
            and market_reference_day
            is not None
        ):
            previous_day = (
                previous_weekday(
                    market_reference_day
                )
            )

            if metric_day == previous_day:
                return (
                    "warning",
                    (
                        "USD/TWD 為最近可用 T-1 "
                        f"資料 ({metric_day.isoformat()})；"
                        "以 degraded 狀態繼續發布。"
                    ),
                )

    # -----------------------------------------------------
    # Fail closed
    # -----------------------------------------------------

    return (
        "error",
        (
            f"{name} critical stale field "
            f"無法由 live freshness policy 放行："
            f"{row.get('date')}"
        ),
    )


def main():
    if not DASHBOARD_PATH.exists():
        raise SystemExit(
            "daily-dashboard.json missing"
        )

    dashboard = load_json(
        DASHBOARD_PATH,
        {},
    )

    validation = load_json(
        LIVE_VALIDATION_PATH,
        {},
    )

    errors: list[str] = []
    warnings: list[str] = []

    # ---------------------------------------------------------
    # Basic schema
    # ---------------------------------------------------------

    required_root_keys = (
        "meta",
        "global",
        "focus",
        "news",
        "flow",
        "freshness",
        "whyVolume",
        "sectors",
        "scenarios",
    )

    for key in required_root_keys:
        if key not in dashboard:
            errors.append(
                f"missing root key: {key}"
            )

    tw = str(
        (dashboard.get("meta") or {})
        .get("twDate")
        or ""
    )

    if not DATE_RE.fullmatch(tw):
        errors.append(
            f"invalid twDate: {tw!r}"
        )

    # ---------------------------------------------------------
    # Load live-validation freshness policy
    # ---------------------------------------------------------

    if not isinstance(validation, dict):
        validation = {}

    validation_status = str(
        validation.get("status")
        or "missing"
    ).strip().lower()

    validation_details = (
        validation.get("details")
        or {}
    )

    if not isinstance(
        validation_details,
        dict,
    ):
        validation_details = {}

    if validation_status == "missing":
        warnings.append(
            "live-validation.json missing; "
            "dashboard freshness will fail closed."
        )

    # ---------------------------------------------------------
    # Critical freshness
    # ---------------------------------------------------------

    freshness_rows = (
        dashboard.get("freshness")
        or []
    )

    if not isinstance(
        freshness_rows,
        list,
    ):
        freshness_rows = []

    critical_stale = [
        row
        for row in freshness_rows
        if (
            isinstance(row, dict)
            and row.get("name")
            in CRITICAL_METRIC_MAP
            and row.get("state")
            == "stale"
        )
    ]

    for row in critical_stale:
        level, message = (
            classify_critical_stale(
                row=row,
                validation_status=(
                    validation_status
                ),
                validation_details=(
                    validation_details
                ),
            )
        )

        if level == "warning":
            warnings.append(
                message
            )
        else:
            errors.append(
                message
            )

    # ---------------------------------------------------------
    # Optional stale data
    #
    # 這條規則維持原本 fail-closed：
    # optional 資料如果 stale，就應顯示 N/A，
    # 不應把舊值當成有效值繼續展示。
    # ---------------------------------------------------------

    optional_stale = [
        row
        for row in freshness_rows
        if (
            isinstance(row, dict)
            and row.get("name")
            in OPTIONAL_FIELDS
            and row.get("state")
            == "stale"
        )
    ]

    if optional_stale:
        errors.append(
            (
                "optional fields are stale; "
                "use N/A instead: "
            )
            + ", ".join(
                stale_description(row)
                for row
                in optional_stale
            )
        )

    # ---------------------------------------------------------
    # Legacy-value guard
    # ---------------------------------------------------------

    if (
        DATE_RE.fullmatch(tw)
        and tw > "2026-09-11"
    ):
        text = json.dumps(
            dashboard,
            ensure_ascii=False,
        )

        suspicious = [
            "-85,067",
            "31.638",
            "-892.70",
        ]

        hit = [
            value
            for value in suspicious
            if value in text
        ]

        if hit:
            errors.append(
                (
                    "legacy 9/11 values leaked "
                    "into V2.2.1 dashboard: "
                )
                + ", ".join(hit)
            )

    # ---------------------------------------------------------
    # Sector integrity
    # ---------------------------------------------------------

    for sector in (
        dashboard.get("sectors")
        or []
    ):
        if not isinstance(
            sector,
            dict,
        ):
            continue

        if (
            sector.get("direction")
            == "N/A"
            and sector.get("score")
            in (
                0,
                "0",
                "0/100",
            )
        ):
            errors.append(
                (
                    f"sector "
                    f"{sector.get('name')} "
                    "uses fake 0/100 "
                    "for missing data"
                )
            )

        desc = str(
            sector.get("desc")
            or ""
        )

        if (
            "法人產業" in desc
            and "N/A" not in desc
        ):
            warnings.append(
                (
                    f"sector "
                    f"{sector.get('name')} "
                    "may still be presenting "
                    "unverified industry "
                    "institutional flow"
                )
            )

    # ---------------------------------------------------------
    # Scenario schema
    # ---------------------------------------------------------

    for scenario in (
        dashboard.get("scenarios")
        or []
    ):
        if not isinstance(
            scenario,
            dict,
        ):
            continue

        if "weight" not in scenario:
            errors.append(
                (
                    f"scenario "
                    f"{scenario.get('type')} "
                    "missing weight field"
                )
            )

        if "probability" in scenario:
            warnings.append(
                (
                    f"scenario "
                    f"{scenario.get('type')} "
                    "still carries legacy "
                    "probability field"
                )
            )

    # ---------------------------------------------------------
    # FOMC integrity
    # ---------------------------------------------------------

    for event in (
        dashboard.get("events")
        or []
    ):
        if not isinstance(
            event,
            dict,
        ):
            continue

        title = str(
            event.get("title")
            or event.get("name")
            or ""
        )

        if "FOMC" not in title:
            continue

        verification = str(
            event.get("verification")
            or ""
        )

        if (
            event.get("source")
            != "Federal Reserve"
        ):
            errors.append(
                (
                    "FOMC event has "
                    "non-Fed source: "
                    f"{title}"
                )
            )

        if (
            "current-year"
            not in verification
        ):
            errors.append(
                (
                    "unverified FOMC event "
                    "leaked into dashboard: "
                    f"{title}"
                )
            )

    # ---------------------------------------------------------
    # Remove duplicate messages
    # ---------------------------------------------------------

    errors = list(
        dict.fromkeys(errors)
    )

    warnings = list(
        dict.fromkeys(warnings)
    )

    # ---------------------------------------------------------
    # Result
    # ---------------------------------------------------------

    if errors:
        print(
            "DASHBOARD V2.2.1 "
            "VALIDATION FAILED"
        )

        for error in errors:
            print(
                " -",
                error,
            )

        for warning in warnings:
            print(
                "::warning::"
                + warning
            )

        return 1

    for warning in warnings:
        print(
            "::warning::"
            + warning
        )

    if warnings:
        print(
            (
                "dashboard V2.2.1 "
                "validation ok "
                "(degraded freshness)"
                f" · twDate={tw}"
                f" · news="
                f"{len(dashboard.get('news', []))}"
                f" · sectors="
                f"{len(dashboard.get('sectors', []))}"
            )
        )
    else:
        print(
            (
                "dashboard V2.2.1 "
                "validation ok"
                f" · twDate={tw}"
                f" · news="
                f"{len(dashboard.get('news', []))}"
                f" · sectors="
                f"{len(dashboard.get('sectors', []))}"
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )