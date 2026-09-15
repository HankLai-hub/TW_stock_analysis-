from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TZ = ZoneInfo("Asia/Taipei")

EXPLICIT = {
    "30 0 * * 1-5": ("premarket", "afterhours"),
    "7 1-5 * * 1-5": ("intraday", "intraday"),
    "37 5 * * 1-5": ("afterhours", "afterhours"),
    "17 7,10,13,16,19,22 * * 1-5": ("afterhours", "afterhours"),
    "0 12 * * 0": ("weekly", "afterhours"),
}
HEARTBEAT = "53 * * * 0-6"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        return None


def write_output(values):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in values.items()]
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print(json.dumps(values, ensure_ascii=False))


def main():
    event_name = os.environ.get("EVENT_NAME", "")
    schedule = os.environ.get("EVENT_SCHEDULE", "")
    manual_mode = os.environ.get("MANUAL_MODE", "afterhours") or "afterhours"
    now = datetime.now(TZ)

    # Manual runs always execute immediately.
    if event_name == "workflow_dispatch":
        market_kind = "intraday" if manual_mode == "intraday" else "afterhours"
        write_output({
            "should_run": True,
            "mode": manual_mode,
            "market_kind": market_kind,
            "reason": "manual run",
        })
        return

    # Normal fixed schedules always execute. Heartbeat only catches missed runs.
    if schedule in EXPLICIT:
        mode, market_kind = EXPLICIT[schedule]
        write_output({
            "should_run": True,
            "mode": mode,
            "market_kind": market_kind,
            "reason": f"explicit schedule {schedule}",
        })
        return

    if schedule != HEARTBEAT:
        write_output({
            "should_run": False,
            "mode": "skip",
            "market_kind": "afterhours",
            "reason": f"unknown schedule {schedule}",
        })
        return

    live = read_json(DATA / "live.json", {})
    health = read_json(DATA / "system-health.json", {})
    last_live = parse_dt(live.get("generatedAt"))
    last_health = parse_dt(health.get("generatedAt"))
    last_mode = str(health.get("mode") or "")
    phase = str(live.get("marketPhase") or "")
    age_live = (now - last_live).total_seconds() / 60 if last_live else 10**9

    weekday = now.weekday()  # Mon=0
    hm = now.hour * 60 + now.minute

    # Sunday weekly catch-up after 20:00.
    if weekday == 6 and hm >= 20 * 60:
        already_weekly_today = (
            last_mode == "weekly"
            and last_health is not None
            and last_health.date() == now.date()
        )
        write_output({
            "should_run": not already_weekly_today,
            "mode": "weekly",
            "market_kind": "afterhours",
            "reason": "weekly heartbeat catch-up" if not already_weekly_today else "weekly already completed",
        })
        return

    # No weekday market automation on Saturday/Sunday outside weekly catch-up.
    if weekday >= 5:
        write_output({
            "should_run": False,
            "mode": "skip",
            "market_kind": "afterhours",
            "reason": "weekend",
        })
        return

    # 08:30 premarket catch-up.
    if 8 * 60 + 30 <= hm < 9 * 60:
        done = (
            last_mode == "premarket"
            and last_health is not None
            and last_health.date() == now.date()
        )
        write_output({
            "should_run": not done,
            "mode": "premarket",
            "market_kind": "afterhours",
            "reason": "premarket heartbeat catch-up" if not done else "premarket already completed",
        })
        return

    # Intraday: if the fixed hourly job was missed, catch it when live data is
    # older than ~50 minutes. This makes the site self-healing rather than
    # depending on every GitHub cron event arriving on time.
    if 9 * 60 <= hm < 13 * 60 + 30:
        due = age_live >= 50
        write_output({
            "should_run": due,
            "mode": "intraday",
            "market_kind": "intraday",
            "reason": f"intraday heartbeat; live age {age_live:.0f}m",
        })
        return

    # Immediately after close, catch a missed 13:37 close run if the last
    # snapshot is still marked as intraday.
    if 13 * 60 + 30 <= hm < 15 * 60:
        due = ("盤中" in phase) or age_live >= 75
        write_output({
            "should_run": due,
            "mode": "afterhours",
            "market_kind": "afterhours",
            "reason": f"close catch-up; phase={phase}; live age {age_live:.0f}m",
        })
        return

    # After hours: target ~3 hours from the last successful market snapshot.
    # A manual 22:49 run therefore naturally makes the next heartbeat around
    # 01:53 eligible, which matches the intuitive 'three hours later' behavior.
    due = age_live >= 165
    write_output({
        "should_run": due,
        "mode": "afterhours",
        "market_kind": "afterhours",
        "reason": f"afterhours heartbeat; live age {age_live:.0f}m",
    })


if __name__ == "__main__":
    main()
