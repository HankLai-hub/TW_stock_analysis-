from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# 台灣固定 UTC+8，不需要依賴系統 tzdata。
TAIPEI_TZ = timezone(
    timedelta(hours=8),
    name="Asia/Taipei",
)


def read(name: str, default):
    """
    Read a JSON file from /data.

    If the file does not exist or cannot be decoded,
    return the provided default value.
    """
    path = DATA / name

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        return default


def write(name: str, payload: dict):
    """
    Write JSON using UTF-8 without escaping Chinese characters.
    """
    path = DATA / name

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def normalize_messages(values) -> list[str]:
    """
    Normalize warning/error values into clean strings.
    """
    if not isinstance(values, list):
        return []

    result: list[str] = []

    for value in values:
        text = str(value or "").strip()

        if text:
            result.append(text)

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        default="unknown",
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # Load source files
    # ---------------------------------------------------------

    live = read(
        "live.json",
        {},
    )

    global_data = read(
        "global.json",
        {},
    )

    brief = read(
        "auto-brief.json",
        {},
    )

    validation = read(
        "live-validation.json",
        {},
    )

    if not isinstance(live, dict):
        live = {}

    if not isinstance(global_data, dict):
        global_data = {}

    if not isinstance(brief, dict):
        brief = {}

    if not isinstance(validation, dict):
        validation = {}

    # ---------------------------------------------------------
    # Source errors
    # ---------------------------------------------------------

    live_errors = normalize_messages(
        live.get("errors")
    )

    global_errors = normalize_messages(
        global_data.get("errors")
    )

    metrics = live.get("metrics")

    if not isinstance(metrics, dict):
        metrics = {}

    # ---------------------------------------------------------
    # Detect stale / missing metrics
    # ---------------------------------------------------------

    stale: list[str] = []
    missing: list[str] = []

    for key, row in metrics.items():
        if not isinstance(row, dict):
            continue

        state = str(
            row.get("state") or ""
        ).strip().lower()

        value = row.get("value")

        if state == "stale":
            stale.append(key)

        if (
            value in (None, "", "N/A")
            or state == "missing"
        ):
            missing.append(key)

    # ---------------------------------------------------------
    # Live validation / freshness
    # ---------------------------------------------------------

    validation_status = str(
        validation.get("status")
        or "unknown"
    ).strip().lower()

    validation_warnings = normalize_messages(
        validation.get("warnings")
    )

    validation_errors = normalize_messages(
        validation.get("errors")
    )

    validation_details = validation.get(
        "details"
    )

    if not isinstance(
        validation_details,
        dict,
    ):
        validation_details = {}

    freshness = validation_details.get(
        "turnoverFreshness"
    )

    freshness_message = (
        validation_details.get(
            "turnoverFreshnessMessage"
        )
    )

    taiex_as_of = validation_details.get(
        "taiexAsOf"
    )

    turnover_as_of = (
        validation_details.get(
            "turnoverAsOf"
        )
    )

    # ---------------------------------------------------------
    # Aggregate warning/error counts
    # ---------------------------------------------------------

    source_error_count = (
        len(live_errors)
        + len(global_errors)
    )

    validation_error_count = len(
        validation_errors
    )

    validation_warning_count = len(
        validation_warnings
    )

    warning_count = (
        source_error_count
        + validation_error_count
        + validation_warning_count
    )

    # ---------------------------------------------------------
    # Determine system health
    #
    # healthy
    #   Major sources OK and freshness OK.
    #
    # degraded
    #   Data is usable, but one or more warnings / stale
    #   indicators exist.
    #
    # partial
    #   Validation errors, missing critical data, or many
    #   source failures.
    # ---------------------------------------------------------

    if validation_status == "error":
        status = "partial"

    elif validation_errors:
        status = "partial"

    elif (
        validation_status == "degraded"
        or freshness == "warning"
    ):
        status = "degraded"

    elif missing:
        status = "degraded"

    elif (
        source_error_count == 0
        and len(stale) <= 1
    ):
        status = "healthy"

    elif source_error_count <= 3:
        status = "degraded"

    else:
        status = "partial"

    # ---------------------------------------------------------
    # Build human-readable warnings
    # ---------------------------------------------------------

    health_warnings: list[str] = []

    for warning in validation_warnings:
        if warning not in health_warnings:
            health_warnings.append(
                warning
            )

    if (
        freshness_message
        and freshness in (
            "warning",
            "error",
        )
        and freshness_message
        not in health_warnings
    ):
        health_warnings.append(
            str(freshness_message)
        )

    if stale:
        health_warnings.append(
            "資料延遲指標："
            + ", ".join(stale)
        )

    if missing:
        health_warnings.append(
            "缺少資料指標："
            + ", ".join(missing)
        )

    if live_errors:
        health_warnings.append(
            "台股資料來源警告："
            + "；".join(
                live_errors
            )
        )

    if global_errors:
        health_warnings.append(
            "全球資料來源警告："
            + "；".join(
                global_errors
            )
        )

    for error in validation_errors:
        message = (
            "即時資料驗證錯誤："
            + error
        )

        if message not in health_warnings:
            health_warnings.append(
                message
            )

    # ---------------------------------------------------------
    # Build final system-health.json
    # ---------------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).astimezone(
        TAIPEI_TZ
    )

    payload = {
        "generatedAt": now.isoformat(
            timespec="seconds"
        ),
        "mode": args.mode,
        "status": status,

        "liveGeneratedAt": (
            live.get("generatedAt")
        ),

        "globalGeneratedAt": (
            global_data.get(
                "generatedAt"
            )
        ),

        "briefGeneratedAt": (
            brief.get(
                "generatedAt"
            )
        ),

        "sourceWarningCount": (
            warning_count
        ),

        "staleMetrics": stale,

        "missingMetrics": missing,

        "warnings": (
            health_warnings
        ),

        "liveValidation": {
            "status": (
                validation_status
            ),
            "taiexAsOf": (
                taiex_as_of
            ),
            "turnoverAsOf": (
                turnover_as_of
            ),
            "turnoverFreshness": (
                freshness
            ),
            "turnoverFreshnessMessage": (
                freshness_message
            ),
        },

        "note": (
            "healthy=主要來源正常；"
            "degraded=部分來源延遲或警告但仍有可用資料；"
            "partial=資料過舊、缺失或多個來源異常。"
        ),
    }

    write(
        "system-health.json",
        payload,
    )

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()