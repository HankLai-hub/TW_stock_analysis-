from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
HISTORY_DIR = ROOT / "history"
TAIPEI = ZoneInfo("Asia/Taipei")
UA = "TW-Market-Radar/3.0 (+GitHub Pages research dashboard)"


def now_taipei() -> datetime:
    return datetime.now(timezone.utc).astimezone(TAIPEI)


def iso_now() -> str:
    return now_taipei().isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def http_json(url: str, *, token: str | None = None, retries: int = 3, timeout: int = 25) -> Any:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-API-Key"] = token
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8-sig", errors="replace")
                return json.loads(raw)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.4 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def compact(s: Any) -> str:
    return re.sub(r"[\s_()（）%％/\-]+", "", str(s or "")).lower()


def find_value(row: dict[str, Any], candidates: Iterable[str]) -> Any:
    normalized = {compact(k): v for k, v in row.items()}
    for candidate in candidates:
        c = compact(candidate)
        if c in normalized:
            return normalized[c]
    for candidate in candidates:
        c = compact(candidate)
        for k, v in normalized.items():
            if c and (c in k or k in c):
                return v
    return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "").replace("％", "")
    s = s.replace("▲", "").replace("▼", "").replace("+", "")
    if not s or s in {"-", "--", "N/A", "nan", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def signed_number(value: Any, sign_value: Any = None) -> float | None:
    f = to_float(value)
    if f is None:
        return None
    sign = str(sign_value or "").strip()
    if sign in {"-", "▼", "－"}:
        return -abs(f)
    return f


def fmt_number(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def roc_to_iso(value: Any) -> str | None:
    s = re.sub(r"\D", "", str(value or ""))
    if len(s) == 7:
        year = int(s[:3]) + 1911
        return f"{year:04d}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def row_date(row: dict[str, Any]) -> str | None:
    return roc_to_iso(find_value(row, ["Date", "日期", "交易日期"]))


def metric(value: str = "N/A", change: str = "", as_of: str = "N/A", state: str = "missing", source: str = "") -> dict[str, str]:
    return {"value": value, "change": change, "asOf": as_of, "state": state, "source": source}


def append_history(snapshot: dict[str, Any], max_rows: int = 800) -> None:
    path = DATA_DIR / "live-history.json"
    rows = read_json(path, [])
    key = snapshot.get("generatedAt")
    if not rows or rows[-1].get("generatedAt") != key:
        rows.append(snapshot)
    atomic_write_json(path, rows[-max_rows:])


def archive_snapshot(snapshot: dict[str, Any]) -> None:
    dt = now_taipei()
    day = dt.strftime("%Y-%m-%d")
    folder = HISTORY_DIR / day
    folder.mkdir(parents=True, exist_ok=True)
    name = dt.strftime("%H%M%S") + f"-{snapshot.get('runKind','run')}.json"
    atomic_write_json(folder / name, snapshot)
