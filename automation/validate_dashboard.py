#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "daily-dashboard.json"


def main():
    if not P.exists():
        raise SystemExit("daily-dashboard.json missing")
    d = json.loads(P.read_text(encoding="utf-8"))
    errors = []
    for key in ("meta", "global", "focus", "news", "freshness", "whyVolume"):
        if key not in d:
            errors.append(f"missing root key: {key}")
    tw = str((d.get("meta") or {}).get("twDate") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tw):
        errors.append(f"invalid twDate: {tw!r}")
    critical = {"TAIEX", "櫃買", "外資現貨", "外資 TX", "Put/Call", "USD/TWD", "市場廣度"}
    stale = [x for x in d.get("freshness", []) if x.get("name") in critical and x.get("state") == "stale"]
    # Stale critical fields are a deployment error: it is safer to show N/A than a silent old value.
    if stale:
        errors.append("critical stale fields: " + ", ".join(f"{x.get('name')}({x.get('date')})" for x in stale))
    # Reject the historical 2026/09/11 contamination once the dashboard benchmark is later.
    if tw > "2026-09-11":
        text = json.dumps(d, ensure_ascii=False)
        suspicious = ["-85,067", "31.638", "-892.70"]
        hit = [x for x in suspicious if x in text]
        if hit:
            errors.append("legacy 9/11 values leaked into v2 dashboard: " + ", ".join(hit))
    if errors:
        print("DASHBOARD VALIDATION FAILED")
        for e in errors:
            print(" -", e)
        return 1
    print(f"dashboard validation ok · twDate={tw} · news={len(d.get('news', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
