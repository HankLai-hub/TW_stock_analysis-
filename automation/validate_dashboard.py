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
    warnings = []

    for key in ("meta", "global", "focus", "news", "flow", "freshness", "whyVolume", "sectors", "scenarios"):
        if key not in d:
            errors.append(f"missing root key: {key}")

    tw = str((d.get("meta") or {}).get("twDate") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tw):
        errors.append(f"invalid twDate: {tw!r}")

    critical = {"TAIEX", "櫃買", "外資現貨", "外資 TX", "Put/Call", "USD/TWD", "市場廣度"}
    stale = [x for x in d.get("freshness", []) if x.get("name") in critical and x.get("state") == "stale"]
    if stale:
        errors.append("critical stale fields: " + ", ".join(f"{x.get('name')}({x.get('date')})" for x in stale))

    optional = {"投信", "自營商", "融券", "借券賣出"}
    opt_stale = [x for x in d.get("freshness", []) if x.get("name") in optional and x.get("state") == "stale"]
    if opt_stale:
        errors.append("optional fields are stale; use N/A instead: " + ", ".join(f"{x.get('name')}({x.get('date')})" for x in opt_stale))

    if tw > "2026-09-11":
        text = json.dumps(d, ensure_ascii=False)
        suspicious = ["-85,067", "31.638", "-892.70"]
        hit = [x for x in suspicious if x in text]
        if hit:
            errors.append("legacy 9/11 values leaked into V2.2.1 dashboard: " + ", ".join(hit))

    # Missing industry data must never be represented as a synthetic 0/100 score.
    for s in d.get("sectors", []):
        if s.get("direction") == "N/A" and s.get("score") in (0, "0", "0/100"):
            errors.append(f"sector {s.get('name')} uses fake 0/100 for missing data")
        desc = str(s.get("desc") or "")
        if "法人產業" in desc and "N/A" not in desc:
            warnings.append(f"sector {s.get('name')} may still be presenting unverified industry institutional flow")

    # New schema uses scenario weights, not probabilities.
    for s in d.get("scenarios", []):
        if "weight" not in s:
            errors.append(f"scenario {s.get('type')} missing weight field")
        if "probability" in s:
            warnings.append(f"scenario {s.get('type')} still carries legacy probability field")

    # Any FOMC event shown after the hotfix must be marked as verified from the
    # current-year official calendar. If repair fails, events should be purged.
    for e in d.get("events", []):
        title = str(e.get("title") or e.get("name") or "")
        if "FOMC" in title:
            verification = str(e.get("verification") or "")
            if e.get("source") != "Federal Reserve":
                errors.append(f"FOMC event has non-Fed source: {title}")
            if "current-year" not in verification:
                errors.append(f"unverified FOMC event leaked into dashboard: {title}")

    if errors:
        print("DASHBOARD V2.2.1 VALIDATION FAILED")
        for e in errors:
            print(" -", e)
        return 1

    for w in warnings:
        print("::warning::" + w)
    print(f"dashboard V2.2.1 validation ok · twDate={tw} · news={len(d.get('news', []))} · sectors={len(d.get('sectors', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
