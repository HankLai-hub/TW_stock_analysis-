from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Asia/Taipei")


def read(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def write(name, payload):
    (DATA / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="unknown")
    args = ap.parse_args()

    live = read("live.json", {})
    global_data = read("global.json", {})
    brief = read("auto-brief.json", {})

    live_errors = list(live.get("errors") or []) if isinstance(live, dict) else []
    global_errors = list(global_data.get("errors") or []) if isinstance(global_data, dict) else []
    metrics = live.get("metrics") or {} if isinstance(live, dict) else {}

    stale = []
    missing = []
    for key, row in metrics.items():
        if not isinstance(row, dict):
            continue
        state = row.get("state")
        value = row.get("value")
        if state == "stale":
            stale.append(key)
        if value in (None, "", "N/A") or state == "missing":
            missing.append(key)

    error_count = len(live_errors) + len(global_errors)
    if error_count == 0 and len(stale) <= 1:
        status = "healthy"
    elif error_count <= 3:
        status = "degraded"
    else:
        status = "partial"

    payload = {
        "generatedAt": datetime.now(timezone.utc).astimezone(TZ).isoformat(timespec="seconds"),
        "mode": args.mode,
        "status": status,
        "liveGeneratedAt": live.get("generatedAt") if isinstance(live, dict) else None,
        "globalGeneratedAt": global_data.get("generatedAt") if isinstance(global_data, dict) else None,
        "briefGeneratedAt": brief.get("generatedAt") if isinstance(brief, dict) else None,
        "sourceWarningCount": error_count,
        "staleMetrics": stale,
        "missingMetrics": missing,
        "note": "healthy=主要來源正常；degraded=部分來源警告但有可用資料；partial=多個來源異常。",
    }
    write("system-health.json", payload)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
