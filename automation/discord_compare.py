from __future__ import annotations

import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / os.getenv("MARKET_DATA_DIR", "data")
STATE_FILE = ROOT / ".github" / "discord-history" / "last_snapshot.json"
REPORT_DIR = ROOT / "reports" / "discord-history"
TAIPEI = ZoneInfo("Asia/Taipei")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
DRY_RUN = os.getenv("DISCORD_DRY_RUN", "").lower() in {"1", "true", "yes"}
SITE_URL = os.getenv(
    "SITE_URL", "https://hanklai-hub.github.io/TW_stock_analysis-/?mode=daily#overview"
).strip()

# Discord: at most 10 embeds and 6,000 visible characters across all embeds.
MAX_EMBED_TEXT = 5_700
MAX_SECTION_TEXT = 760

FILE_LABELS = {
    "data/auto-brief.json": "市場摘要",
    "data/daily-dashboard.json": "每日儀表板",
    "data/global.json": "全球市場",
    "data/intelligence.json": "市場情報",
    "data/live-history.json": "歷史行情",
    "data/live.json": "即時市場",
    "data/system-health.json": "系統健康",
}
SEGMENT_LABELS = {
    "advance": "上漲家數", "asOf": "資料日期", "borrowShortBalance": "借券賣出餘額",
    "breadth": "市場廣度", "change": "漲跌／補充", "close": "收盤價",
    "confidence": "模型完整度", "daily": "每日摘要", "dealerHedgeSpot": "自營商避險",
    "dealerSelfSpot": "自營商自行買賣", "dealerSpot": "自營商現貨", "decline": "下跌家數",
    "foreignSpot": "外資現貨", "foreignSpotOfficial": "外資現貨", "foreignTx": "外資期貨淨部位",
    "generatedAt": "產生時間", "headline": "市場結論", "investmentTrust": "投信現貨",
    "label": "狀態標籤", "macro": "總體市場", "margin": "融資餘額",
    "marketPhase": "市場階段", "metrics": "市場指標", "missingMetrics": "缺漏指標",
    "mode": "執行模式", "nasdaq": "Nasdaq", "note": "說明", "otc": "櫃買指數",
    "phase": "市場階段", "putCall": "Put/Call Ratio", "rawValueYi": "原始值（億元）",
    "regime": "全球環境", "runKind": "更新類型", "score": "市場風險分數",
    "shortBalance": "融券餘額", "source": "資料來源", "sourceStatus": "資料來源狀態",
    "sourceWarningCount": "來源警告數", "sp500": "S&P 500", "staleMetrics": "過期指標",
    "state": "資料狀態", "status": "系統狀態", "taiex": "加權指數",
    "tone": "訊號色彩", "trustSpot": "投信現貨", "turnover": "上市成交值",
    "tx": "台指期", "usdTwd": "美元／台幣", "value": "數值", "weekly": "每週摘要",
}


@dataclass(frozen=True)
class Metric:
    section: str
    label: str
    path: str
    detail_path: str | None = None


METRICS = (
    Metric("市場狀態", "市場風險分數", "data/auto-brief.json:daily.score"),
    Metric("市場狀態", "市場階段", "data/auto-brief.json:daily.phase"),
    Metric("市場狀態", "全球環境", "data/daily-dashboard.json:regime"),
    Metric("指數", "加權指數", "data/live.json:metrics.taiex.value", "data/live.json:metrics.taiex.change"),
    Metric("指數", "櫃買指數", "data/live.json:metrics.otc.value", "data/live.json:metrics.otc.change"),
    Metric("指數", "上市成交值", "data/live.json:metrics.turnover.value"),
    Metric("市場廣度", "上漲／下跌家數", "data/live.json:metrics.breadth.value", "data/live.json:metrics.breadth.change"),
    Metric("法人／外資", "外資現貨", "data/live.json:metrics.foreignSpot.value"),
    Metric("法人／外資", "投信現貨", "data/live.json:metrics.trustSpot.value"),
    Metric("法人／外資", "自營商現貨", "data/live.json:metrics.dealerSpot.value"),
    Metric("期貨", "台指期", "data/live.json:metrics.tx.value", "data/live.json:metrics.tx.change"),
    Metric("期貨", "外資期貨淨部位", "data/live.json:metrics.foreignTx.value", "data/live.json:metrics.foreignTx.change"),
    Metric("期貨", "Put/Call Ratio", "data/live.json:metrics.putCall.value", "data/live.json:metrics.putCall.change"),
    Metric("融資", "融資餘額", "data/live.json:metrics.margin.value", "data/live.json:metrics.margin.change"),
    Metric("融資", "融券餘額", "data/live.json:metrics.shortBalance.value", "data/live.json:metrics.shortBalance.change"),
    Metric("融資", "借券賣出餘額", "data/live.json:metrics.borrowShortBalance.value"),
)
SECTION_ICONS = {
    "市場狀態": "🧭", "指數": "📈", "市場廣度": "↕️",
    "法人／外資": "🏦", "期貨": "📊", "融資": "💳",
}


def safe_load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__read_error__": str(exc)}


def load_current_files() -> dict[str, Any]:
    if not DATA_DIR.exists():
        raise RuntimeError(f"Data directory not found: {DATA_DIR}")
    return {
        path.relative_to(ROOT).as_posix(): safe_load_json(path)
        for path in sorted(DATA_DIR.rglob("*.json")) if path.is_file()
    }


def load_previous_files() -> tuple[dict[str, Any], str | None]:
    if not STATE_FILE.exists():
        return {}, None
    state = safe_load_json(STATE_FILE)
    if not isinstance(state, dict):
        return {}, None
    files = state.get("files")
    if isinstance(files, dict):
        generated_at = state.get("generatedAt")
        return files, str(generated_at) if generated_at else None
    # Compatibility with an early draft that stored the file map directly.
    if any(str(key).startswith("data/") for key in state):
        return state, None
    return {}, None


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
        for index, item in enumerate(value):
            child = f"{prefix}[{index}]" if prefix else f"[{index}]"
            out.update(flatten(item, child))
    else:
        out[prefix or "$"] = value
    return out


def compare(current_files: dict[str, Any], previous_files: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    counts = {"files": 0, "fields": 0, "changed": 0, "same": 0, "new": 0, "removed": 0}
    for rel_path in sorted(set(current_files) | set(previous_files)):
        counts["files"] += 1
        current = flatten(current_files[rel_path]) if rel_path in current_files else {}
        previous = flatten(previous_files[rel_path]) if rel_path in previous_files else {}
        for field in sorted(set(current) | set(previous)):
            before_exists, after_exists = field in previous, field in current
            before, after = previous.get(field), current.get(field)
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
            rows.append({"file": rel_path, "field": field, "before": before, "after": after, "status": status})
    return rows, counts


def get_path(files: dict[str, Any], qualified_path: str | None) -> Any:
    if not qualified_path:
        return None
    rel_path, field_path = qualified_path.split(":", 1)
    value: Any = files.get(rel_path)
    if value is None:
        return None
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", field_path):
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(value, list) or index >= len(value):
                return None
            value = value[index]
        else:
            if not isinstance(value, dict) or token not in value:
                return None
            value = value[token]
    return value


def fmt_value(value: Any, limit: int = 120) -> str:
    if value is None:
        text = "—"
    elif isinstance(value, bool):
        text = "是" if value else "否"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            text = str(value)
        else:
            text = f"{value:,.4f}".rstrip("0").rstrip(".")
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def first_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def value_unit(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    for unit in ("億元", "億股", "億", "萬張", "張", "口", "%", "點"):
        if unit in value:
            return f" {unit}"
    return ""


def fmt_number(value: float) -> str:
    return f"{value:+,.2f}".rstrip("0").rstrip(".")


def metric_delta(before: Any, after: Any) -> tuple[str, str]:
    before_number, after_number = first_number(before), first_number(after)
    if before_number is None or after_number is None:
        if before == after:
            return "▬", "無變化"
        if before is None:
            return "◆", "新增資料"
        if after is None:
            return "◆", "資料移除"
        return "◆", "狀態更新"
    delta = after_number - before_number
    if math.isclose(delta, 0.0, abs_tol=1e-12):
        return "▬", "0"
    direction = "▲" if delta > 0 else "▼"
    pct = "" if before_number == 0 else f" ({delta / abs(before_number) * 100:+.2f}%)"
    return direction, f"{fmt_number(delta)}{value_unit(after)}{pct}"


def render_metric(metric: Metric, current: dict[str, Any], previous: dict[str, Any]) -> str:
    before, after = get_path(previous, metric.path), get_path(current, metric.path)
    direction, delta = metric_delta(before, after)
    detail = get_path(current, metric.detail_path)
    detail_text = f" ｜現況 {fmt_value(detail, 38)}" if detail not in (None, "") else ""
    return (
        f"**{metric.label}** {direction} `{delta}`\n"
        f"前次 {fmt_value(before, 48)} → 本次 **{fmt_value(after, 48)}**{detail_text}"
    )


def humanize_path(rel_path: str, field: str) -> str:
    parts: list[str] = []
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", field):
        if token.startswith("["):
            parts.append(f"第 {int(token[1:-1]) + 1} 筆")
        else:
            parts.append(SEGMENT_LABELS.get(token, token))
    return " › ".join([FILE_LABELS.get(rel_path, Path(rel_path).stem), *parts])


def numeric_delta(before: Any, after: Any) -> str:
    before_number, after_number = first_number(before), first_number(after)
    if before_number is None or after_number is None:
        return ""
    delta = after_number - before_number
    pct = "" if before_number == 0 else f", {delta / abs(before_number) * 100:+.2f}%"
    return f"{fmt_number(delta)}{value_unit(after)}{pct}"


def write_snapshot(current_files: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(TAIPEI).isoformat(timespec="seconds"),
        "files": current_files,
    }
    temp_path = STATE_FILE.with_suffix(".tmp")
    temp_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(STATE_FILE)


def make_report(rows: list[dict[str, Any]], counts: dict[str, int], previous_at: str | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TAIPEI)
    path = REPORT_DIR / f"market-comparison-{now.strftime('%Y%m%d-%H%M%S')}.md"
    lines = [
        "# TW Market Radar — 完整資料比較", "",
        f"- 產生時間：{now.isoformat(timespec='seconds')}",
        f"- 上次快照：{previous_at or '無；本次建立初始基準'}",
        f"- JSON 檔案：{counts['files']}", f"- 欄位總數：{counts['fields']}",
        f"- 變更：{counts['changed']}", f"- 新增：{counts['new']}",
        f"- 移除：{counts['removed']}", f"- 未變：{counts['same']}", "",
        "> Discord 僅顯示重要的人類可讀指標；本報告保留所有 JSON 欄位差異。", "",
        "## 全部欄位", "",
        "| 狀態 | 中文欄位 | 技術路徑 | 上一次 | 本次 | 差異 |",
        "|---|---|---|---:|---:|---|",
    ]
    labels = {"changed": "變更", "new": "新增", "removed": "移除", "same": "未變"}
    order = {"changed": 0, "new": 1, "removed": 2, "same": 3}
    for row in sorted(rows, key=lambda item: (order[item["status"]], item["file"], item["field"])):
        before = fmt_value(row["before"]).replace("|", "\\|")
        after = fmt_value(row["after"]).replace("|", "\\|")
        delta = numeric_delta(row["before"], row["after"]).replace("|", "\\|")
        readable = humanize_path(row["file"], row["field"]).replace("|", "\\|")
        technical = f"{row['file']}:{row['field']}".replace("|", "\\|")
        lines.append(f"| {labels[row['status']]} | {readable} | `{technical}` | {before} | {after} | {delta} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def score_color(current: dict[str, Any]) -> int:
    score = first_number(get_path(current, "data/auto-brief.json:daily.score"))
    if score is None:
        return 0x5865F2
    if score >= 60:
        return 0x2ECC71
    if score < 45:
        return 0xE74C3C
    return 0xF1C40F


def embed_text_size(embed: dict[str, Any]) -> int:
    size = len(str(embed.get("title", ""))) + len(str(embed.get("description", "")))
    footer = embed.get("footer", {})
    size += len(str(footer.get("text", ""))) if isinstance(footer, dict) else 0
    for field in embed.get("fields", []):
        size += len(str(field.get("name", ""))) + len(str(field.get("value", "")))
    return size


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def build_embeds(current: dict[str, Any], previous: dict[str, Any], counts: dict[str, int], previous_at: str | None) -> list[dict[str, Any]]:
    now = datetime.now(TAIPEI)
    score = get_path(current, "data/auto-brief.json:daily.score")
    label = get_path(current, "data/auto-brief.json:daily.label") or "—"
    phase = get_path(current, "data/auto-brief.json:daily.phase") or "—"
    headline = get_path(current, "data/auto-brief.json:daily.headline")
    color = score_color(current)
    main = {
        "title": "TW Market Radar｜市場更新比較", "url": SITE_URL,
        "description": truncate(str(headline or "本次市場資料更新已完成。"), 600), "color": color,
        "fields": [
            {"name": "市場狀態", "value": f"**{fmt_value(score)} / 100｜{fmt_value(label)}**\n{fmt_value(phase)}", "inline": True},
            {"name": "本次差異", "value": f"變更 **{counts['changed']}**｜新增 **{counts['new']}**\n移除 **{counts['removed']}**｜未變 {counts['same']}", "inline": True},
            {"name": "比較範圍", "value": f"{counts['files']} 個 JSON\n{counts['fields']:,} 個欄位", "inline": True},
        ],
        "footer": {"text": f"每次更新皆新增訊息｜上次快照 {previous_at or '首次建立'}｜完整差異見附件與 history branch｜僅供研究"},
        "timestamp": now.isoformat(),
    }
    embeds: list[dict[str, Any]] = [main]
    for section, icon in SECTION_ICONS.items():
        body = "\n\n".join(render_metric(metric, current, previous) for metric in METRICS if metric.section == section)
        embeds.append({"title": f"{icon} {section}", "description": truncate(body or "本次無可用資料。", MAX_SECTION_TEXT), "color": color})
    health = get_path(current, "data/system-health.json:status") or "未知"
    warnings = get_path(current, "data/system-health.json:sourceWarningCount")
    missing = get_path(current, "data/system-health.json:missingMetrics")
    stale = get_path(current, "data/system-health.json:staleMetrics")
    missing_count = len(missing) if isinstance(missing, list) else 0
    stale_count = len(stale) if isinstance(stale, list) else 0
    system_text = (
        f"**資料健康**　`{fmt_value(health)}`｜來源警告 **{fmt_value(warnings)}**｜缺漏 {missing_count}｜過期 {stale_count}\n"
        f"**完整比較**　{counts['files']} 個 JSON／{counts['fields']:,} 欄位\n"
        f"**結果統計**　變更 {counts['changed']}｜新增 {counts['new']}｜移除 {counts['removed']}｜未變 {counts['same']}\n"
        "完整逐欄差異已附上 Markdown，並保存於 `discord-history-data/reports/`。"
    )
    embeds.append({"title": "⚙️ 系統統計", "description": system_text, "color": color})
    total = sum(embed_text_size(embed) for embed in embeds)
    if len(embeds) > 10 or total > MAX_EMBED_TEXT:
        raise RuntimeError(f"Discord embed limits exceeded: {len(embeds)} embeds, {total} characters")
    return embeds


def validate_payload(payload: dict[str, Any]) -> None:
    embeds = payload.get("embeds", [])
    if not isinstance(embeds, list) or not 1 <= len(embeds) <= 10:
        raise RuntimeError("Discord payload must contain 1 to 10 embeds")
    total = sum(embed_text_size(embed) for embed in embeds)
    if total > 6_000:
        raise RuntimeError(f"Discord payload is too long: {total} characters")
    for embed in embeds:
        if len(str(embed.get("title", ""))) > 256 or len(str(embed.get("description", ""))) > 4_096:
            raise RuntimeError("Discord embed title or description exceeds its limit")
        fields = embed.get("fields", [])
        if len(fields) > 25 or any(len(str(field.get("value", ""))) > 1_024 for field in fields):
            raise RuntimeError("Discord embed field exceeds its limit")


def send_discord(embeds: list[dict[str, Any]], report: Path) -> None:
    # POST without a message ID always creates a new message; never PATCH/DELETE history.
    payload = {"username": "TW Market Radar", "allowed_mentions": {"parse": []}, "embeds": embeds}
    validate_payload(payload)
    if DRY_RUN:
        preview = REPORT_DIR / "discord-payload-preview.json"
        preview.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Dry run: Discord payload written to {preview.relative_to(ROOT)}")
        return
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is empty. Add it to GitHub Actions Secrets.")
    import requests

    with report.open("rb") as file_handle:
        response = requests.post(
            WEBHOOK_URL,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files={"files[0]": (report.name, file_handle, "text/markdown")}, timeout=30,
        )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook failed: HTTP {response.status_code}: {response.text[:500]}")


def main() -> int:
    try:
        current_files = load_current_files()
        previous_files, previous_at = load_previous_files()
        rows, counts = compare(current_files, previous_files)
        report = make_report(rows, counts, previous_at)
        embeds = build_embeds(current_files, previous_files, counts, previous_at)
        write_snapshot(current_files)
        send_discord(embeds, report)
        print(f"Discord history post sent. Report: {report.relative_to(ROOT)}")
        print(json.dumps(counts, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
