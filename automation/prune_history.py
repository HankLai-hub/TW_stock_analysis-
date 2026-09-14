from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HISTORY = ROOT / "history"
TAIPEI = ZoneInfo("Asia/Taipei")

MAX_HISTORY_ROWS = 800
KEEP_ARCHIVE_DAYS = 120


def main():
    path = DATA / "live-history.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        rows = []
    if isinstance(rows, list) and len(rows) > MAX_HISTORY_ROWS:
        path.write_text(json.dumps(rows[-MAX_HISTORY_ROWS:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"trimmed live-history.json to {MAX_HISTORY_ROWS} rows")

    cutoff = datetime.now(timezone.utc).astimezone(TAIPEI).date() - timedelta(days=KEEP_ARCHIVE_DAYS)
    removed = 0
    if HISTORY.exists():
        for p in HISTORY.iterdir():
            if not p.is_dir():
                continue
            try:
                day = datetime.strptime(p.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if day < cutoff:
                shutil.rmtree(p)
                removed += 1
    print(f"archive prune complete: removed {removed} day folders; keep {KEEP_ARCHIVE_DAYS} days")


if __name__ == "__main__":
    main()
