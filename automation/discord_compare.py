from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / os.getenv("MARKET_DATA_DIR", "data")
REPORT_DIR = ROOT / "discord_reports"
TAIPEI = ZoneInfo("Asia/Taipei")

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
SITE_URL = os.getenv(
    "SITE_URL",
    "https://hanklai-hub.github.io/TW_stock_analysis-/?mode=daily#overview",
).strip()

MAX_IMPORTANT_CHANGES = 12
MAX_DISCORD_TEXT = 1000


def run_git(*args: str) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "git command failed")
    return p.stdout.strip()


def current_json_paths() -> set[str]:
    if not DATA_DIR.exists():
        raise RuntimeError(f"Data directory not found: {DATA_DIR}")
    return {p.relative_to(ROOT).as_posix() for p in DATA_DIR.rglob("*.json") if p.is_file()}


def previous_json_paths(commit: str | None) -> set[str]:
    if not commit:
        return set()
    rel_data = DATA_DIR.relative_to(ROOT).as_posix()
    p = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", rel_data],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if p.returncode != 0:
        return set()
    return {line.strip() for line in p.stdout.splitlines() if line.strip().endswith(".json")}


def safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__read_error__": str(exc)}


def load_json_from_commit(commit: str, rel_path: str) -> Any:
    p = subprocess.run(
        ["git", "show", f"{commit}:{rel_path}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"__read_error__": "invalid JSON in previous commit"}


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        if not value:
            out[prefix or "$"] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(value[key], child))
    elif isinstance(value, list):
        if not value:
            out[prefix or "$"] = []
        for i, item in enumerate(value):
            child = f"{prefix}[{i}]" if prefix else f"[{i}]"
            out.update(flatten(item, child))
    else:
        out[prefix or "$"] = value
    return out


def find_previous_data_commit() -> str | None:
    try:
        commits = run_git("log", "--format=%H", "-n", "2", "--", str(DATA_DIR.relative_to(ROOT))).splitlines()
    except Exception:
        return None
    return commits[1] if len(commits) >= 2 else None


def fmt_value(v: Any, limit: int = 160) -> str:
    if v is None:
        s = "∅"
    elif isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            s = str(v)
        else:
            s = f"{v:,}"
    else:
        s = str(v).replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def numeric_delta(before: Any, after: Any) -> str:
    if isinstance(before, bool) or isinstance(after, bool):
        return ""
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return ""
    delta = after - before
    pct = None if before == 0 else (delta / abs(before)) * 100
    sign = "+" if delta > 0 else ""
    if pct is None:
        return f" ({sign}{delta:,.4g})"
    return f" ({sign}{delta:,.4g}, {sign}{pct:.2f}%)"


def compare() -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
    previous_commit = find_previous_data_commit()
    rows: list[dict[str, Any]] = []
    counts = {"files": 0, "fields": 0, "changed": 0, "same": 0, "new": 0, "removed": 0}

    all_paths = sorted(current_json_paths() | previous_json_paths(previous_commit))

    for rel in all_paths:
        counts["files"] += 1
        path = ROOT / rel
        current_obj = safe_load_json(path) if path.exists() else None
        current = flatten(current_obj) if current_obj is not None else {}
        previous_obj = load_json_from_commit(previous_commit, rel) if previous_commit else None
        previous = flatten(previous_obj) if previous_obj is not None else {}

        keys = sorted(set(current) | set(previous))
        for key in keys:
            before_exists = key in previous
            after_exists = key in current
            before = previous.get(key)
            after = current.get(key)
            if not before_exists:
                status = "new"
            elif not after_exists:
                status = "removed"
            elif before == after:
                status = "same"
            else:
                status = "changed"

            counts["fields"] += 1
            counts[status] += 1
            rows.append(
                {
                    "file": rel,
                    "field": key,
                    "before": before,
                    "after": after,
                    "status": status,
                }
            )

    return rows, counts, previous_commit


def make_report(rows: list[dict[str, Any]], counts: dict[str, int], previous_commit: str | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TAIPEI).strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"market-comparison-{stamp}.md"

    lines = [
        "# TW Market Radar — 完整資料比較",
        "",
        f"- 產生時間：{datetime.now(TAIPEI).isoformat(timespec='seconds')}",
        f"- 前一資料版本：`{previous_commit or '無可比較版本'}`",
        f"- JSON 檔案：{counts['files']}",
        f"- 欄位總數：{counts['fields']}",
        f"- 變更：{counts['changed']}",
        f"- 新增：{counts['new']}",
        f"- 移除：{counts['removed']}",
        f"- 未變：{counts['same']}",
        "",
        "## 全部欄位",
        "",
        "| 狀態 | 檔案 | 欄位 | 上一次 | 本次 | 差異 |",
        "|---|---|---|---:|---:|---|",
    ]

    labels = {"changed": "變更", "new": "新增", "removed": "移除", "same": "未變"}
    order = {"changed": 0, "new": 1, "removed": 2, "same": 3}

    for row in sorted(rows, key=lambda r: (order[r["status"]], r["file"], r["field"])):
        before = fmt_value(row["before"], 120).replace("|", "\\|")
        after = fmt_value(row["after"], 120).replace("|", "\\|")
        delta = numeric_delta(row["before"], row["after"]).strip().replace("|", "\\|")
        field = row["field"].replace("|", "\\|")
        file_name = row["file"].replace("|", "\\|")
        lines.append(f"| {labels[row['status']]} | `{file_name}` | `{field}` | {before} | {after} | {delta} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def importance(row: dict[str, Any]) -> tuple[int, float]:
    text = f"{row['file']} {row['field']}".lower()
    keywords = [
        "score", "index", "close", "price", "change", "pct", "percent",
        "foreign", "外資", "投信", "futures", "期貨", "margin", "融資",
        "breadth", "advance", "decline", "volatility", "risk", "health",
    ]
    kw = sum(1 for k in keywords if k in text)
    magnitude = 0.0
    b, a = row["before"], row["after"]
    if isinstance(b, (int, float)) and not isinstance(b, bool) and isinstance(a, (int, float)) and not isinstance(a, bool):
        magnitude = abs(a - b) / (abs(b) + 1e-9)
    return kw, magnitude


def important_changes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed = [r for r in rows if r["status"] != "same"]
    changed.sort(key=importance, reverse=True)
    return changed[:MAX_IMPORTANT_CHANGES]


def find_brief() -> dict[str, Any]:
    candidates = [DATA_DIR / "auto-brief.json", DATA_DIR / "brief.json"]
    for path in candidates:
        if path.exists():
            obj = safe_load_json(path)
            if isinstance(obj, dict):
                daily = obj.get("daily") if isinstance(obj.get("daily"), dict) else obj
                return daily if isinstance(daily, dict) else {}
    return {}


def build_embed(rows: list[dict[str, Any]], counts: dict[str, int], previous_commit: str | None) -> dict[str, Any]:
    brief = find_brief()
    title = "TW Market Radar｜資料更新比較"
    headline = brief.get("headline") or brief.get("summary") or "本次資料更新已完成，完整欄位比較已附檔。"

    top = important_changes(rows)
    if top:
        detail_lines = []
        for r in top:
            symbol = {"changed": "↕", "new": "+", "removed": "−"}.get(r["status"], "•")
            field = r["field"]
            if len(field) > 56:
                field = "…" + field[-55:]
            delta = numeric_delta(r["before"], r["after"])
            detail_lines.append(
                f"{symbol} `{field}`\n{fmt_value(r['before'], 50)} → **{fmt_value(r['after'], 50)}**{delta}"
            )
        important_text = "\n".join(detail_lines)
        if len(important_text) > MAX_DISCORD_TEXT:
            important_text = important_text[: MAX_DISCORD_TEXT - 1] + "…"
    else:
        important_text = "本次所有可比較欄位皆無變化。"

    score = brief.get("score")
    label = brief.get("label") or brief.get("phase") or "—"
    score_text = f"{score} / 100 · {label}" if score is not None else str(label)

    return {
        "title": title,
        "url": SITE_URL,
        "description": str(headline)[:4000],
        "color": 3447003,
        "fields": [
            {"name": "本次狀態", "value": score_text[:1024], "inline": True},
            {
                "name": "比較範圍",
                "value": f"{counts['files']} 個 JSON\n{counts['fields']} 個欄位",
                "inline": True,
            },
            {
                "name": "差異統計",
                "value": (
                    f"變更 {counts['changed']}｜新增 {counts['new']}｜移除 {counts['removed']}\n"
                    f"未變 {counts['same']}"
                ),
                "inline": True,
            },
            {"name": "重要變化", "value": important_text, "inline": False},
            {
                "name": "完整比較",
                "value": "本訊息附有完整 Markdown 報告，包含每個 JSON 欄位的上次值、本次值與數值差異。",
                "inline": False,
            },
        ],
        "footer": {
            "text": f"歷史模式：每次更新新增一篇｜prev {previous_commit[:8] if previous_commit else 'N/A'}｜僅供研究，不構成投資建議"
        },
        "timestamp": datetime.now(TAIPEI).isoformat(),
    }


def send_discord(embed: dict[str, Any], report: Path) -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is empty. Add it to GitHub Actions Secrets.")

    payload = {
        "username": "TW Market Radar",
        "allowed_mentions": {"parse": []},
        "embeds": [embed],
    }

    with report.open("rb") as f:
        response = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files={"files[0]": (report.name, f, "text/markdown")},
            timeout=30,
        )

    if response.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook failed: HTTP {response.status_code}: {response.text[:500]}")


def main() -> int:
    try:
        rows, counts, previous_commit = compare()
        report = make_report(rows, counts, previous_commit)
        embed = build_embed(rows, counts, previous_commit)
        send_discord(embed, report)

        print(f"Discord history post sent. Report: {report.relative_to(ROOT)}")
        print(json.dumps(counts, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
