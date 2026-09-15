#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
LIVE = DATA / 'live.json'
HISTORY = DATA / 'live-history.json'
OUT = DATA / 'auto-brief.json'
GLOBAL = DATA / 'global.json'


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def num(v):
    if v is None:
        return None
    m = re.search(r'[+-]?\d[\d,]*(?:\.\d+)?', str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', ''))
    except Exception:
        return None


def pct(v):
    return num(v)


def breadth_ratio(v):
    m = re.search(r'([\d,]+)↑\s*/\s*([\d,]+)↓', str(v or ''))
    if not m:
        return None
    up = int(m.group(1).replace(',', ''))
    down = int(m.group(2).replace(',', ''))
    if up + down == 0:
        return None
    return up / (up + down)


def risk_bucket(score):
    if score is None:
        return '資料不足'
    if score >= 70:
        return 'Risk-On'
    if score >= 55:
        return '偏多'
    if score >= 45:
        return 'Neutral'
    if score >= 30:
        return '偏空'
    return 'Risk-Off'


def tone_from_score(score):
    if score is None:
        return 'neutral'
    if score >= 55:
        return 'good'
    if score >= 45:
        return 'warn'
    return 'bad'


def metric(live, key):
    return (live.get('metrics') or {}).get(key) or {}


def metric_is_current(live, key, benchmark=None):
    row = metric(live, key)
    if row.get('state') == 'stale':
        return False
    if benchmark is None:
        benchmark = metric(live, 'taiex').get('asOf')
    import re
    def day(v):
        m = re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})', str(v or ''))
        return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}' if m else None
    b = day(benchmark)
    d = day(row.get('asOf'))
    return not (b and d and d < b)


def daily_brief(live, global_data=None):
    risk = live.get('risk') or {}
    score = risk.get('score') if isinstance(risk.get('score'), (int, float)) else None
    label = risk.get('label') or risk_bucket(score)
    confidence = risk.get('confidence') if isinstance(risk.get('confidence'), (int, float)) else 0
    phase = live.get('marketPhase') or 'N/A'

    taiex = metric(live, 'taiex')
    otc = metric(live, 'otc')
    breadth = metric(live, 'breadth')
    fspot = metric(live, 'foreignSpot')
    ftx = metric(live, 'foreignTx')
    pc = metric(live, 'putCall')

    taiex_pct = pct(taiex.get('change'))
    otc_pct = pct(otc.get('change'))
    b_ratio = breadth_ratio(breadth.get('value'))
    fspot_n = num(fspot.get('value'))
    ftx_current = metric_is_current(live, 'foreignTx', taiex.get('asOf'))
    ftx_n = num(ftx.get('value')) if ftx_current else None

    if score is None:
        headline = '目前資料不足，先以來源完整性與最新官方資料時間為優先。'
    elif score < 30:
        headline = '資金、期貨曝險與市場廣度形成偏空共振，短線先以風險控制為優先。'
    elif score < 45:
        headline = '市場仍偏空，但尚未進入全面恐慌；等待資金與廣度同步改善。'
    elif score < 55:
        headline = '市場多空分歧，指數與資金訊號尚未形成一致方向。'
    elif score < 70:
        headline = '市場風險偏好改善，但仍需確認外資與中小型股是否同步跟上。'
    else:
        headline = '價格、資金與市場廣度形成 Risk-On 共振，但仍需防範槓桿快速升溫。'

    bullets = []
    if taiex_pct is not None or otc_pct is not None:
        parts = []
        if taiex_pct is not None:
            parts.append(f'TAIEX {taiex_pct:+.2f}%')
        if otc_pct is not None:
            parts.append(f'櫃買 {otc_pct:+.2f}%')
        bullets.append('價格面：' + '、'.join(parts) + '。')

    if fspot_n is not None or ftx_n is not None or ftx.get('value') not in {None, '', 'N/A'}:
        parts = []
        if fspot_n is not None:
            parts.append(f'外資現貨 {fspot_n:+,.0f} 億')
        if ftx_n is not None:
            parts.append(f'外資 TX {ftx_n:+,.0f} 口')
        elif ftx.get('value') not in {None, '', 'N/A'}:
            parts.append(f'外資 TX {ftx.get("value")}（資料至 {ftx.get("asOf") or "N/A"}，不納入今日方向）')
        bullets.append('法人曝險：' + '；'.join(parts) + '。')

    if b_ratio is not None:
        bullets.append(f'市場廣度：上漲家數占漲跌家數約 {b_ratio*100:.1f}%，' + ('內部結構偏弱。' if b_ratio < 0.45 else ('廣度偏強。' if b_ratio > 0.55 else '多空接近均衡。')))

    global_data = global_data or {}
    gm = global_data.get('macro') or {}
    gr = global_data.get('risk') or {}
    global_parts = []
    us10 = (gm.get('us10y') or {}).get('display')
    brent = (gm.get('brent') or {}).get('display')
    cpi_disp = (gm.get('cpi') or {}).get('display')
    if us10 and us10 != 'N/A':
        global_parts.append(f'美10Y {us10}')
    if brent and brent != 'N/A':
        global_parts.append(f'Brent {brent}')
    if cpi_disp and cpi_disp != 'N/A':
        global_parts.append(f'CPI {cpi_disp}')
    if global_parts:
        glabel = gr.get('label') or 'N/A'
        gscore = gr.get('score')
        suffix = f'；全球宏觀 {glabel}' + (f' {float(gscore):.0f}分' if isinstance(gscore, (int, float)) else '')
        bullets.append('全球宏觀：' + '、'.join(global_parts) + suffix + '。')

    if pc.get('value') not in {None, '', 'N/A'}:
        bullets.append(f'選擇權：{pc.get("value")}；{pc.get("change") or "OI 比率同步觀察"}，不作單一方向訊號。')

    while len(bullets) < 4:
        bullets.append('資料稽核：缺漏或尚未更新的官方資料維持 N/A，不以推估值補洞。')

    if score is None:
        short_view = '資料不足，暫不下方向性判斷。'
    elif score < 30:
        short_view = '1–5 日：偏空／高波動。若風險分數無法回到 30 以上，反彈先視為修復而非反轉。'
    elif score < 45:
        short_view = '1–5 日：震盪偏空。需要廣度與外資曝險改善才能上修。'
    elif score < 55:
        short_view = '1–5 日：中性震盪。等待分數脫離 45–55 區間。'
    elif score < 70:
        short_view = '1–5 日：震盪偏多。若資金與廣度持續改善，可上修風險承擔。'
    else:
        short_view = '1–5 日：偏多。若槓桿未過熱且外資持續加碼，Risk-On 結構延續。'

    if (global_data or {}).get('risk', {}).get('score') is not None:
        gr = global_data.get('risk') or {}
        swing_view = f'2–8 週：國內短線模型仍與中期趨勢分開；目前全球宏觀分數 {float(gr.get("score")):.0f}（{gr.get("label")}）。中期需同時追蹤美債、實質利率、油價、美元與企業獲利。'
    else:
        swing_view = '2–8 週：目前自動模型主要使用國內價格、法人與廣度資料；中期仍需搭配美債、美元、油價與企業獲利，不把短線分數直接等同中期趨勢。'

    invalidation = []
    if score is not None and score < 45:
        invalidation = [
            'Risk Score 回升至 45 以上並連續維持兩次更新。',
            '市場廣度回到 50% 以上，且櫃買相對強度同步改善。',
            ('外資現貨轉為淨買超，外資 TX 淨空顯著收斂。' if ftx_current else '外資現貨轉為淨買超，並等待外資 TX 更新至最新交易日後確認。'),
        ]
    else:
        invalidation = [
            'Risk Score 跌破 45 並連續維持兩次更新。',
            '市場廣度跌破 40%，中小型股明顯轉弱。',
            ('外資現貨轉賣且外資 TX 淨空同步擴大。' if ftx_current else '外資現貨轉賣，且外資 TX 更新至最新交易日後仍偏空。'),
        ]

    local_score = score
    global_score = (global_data.get('risk') or {}).get('score')
    resonance = {
        'label': '資料不足',
        'tone': 'neutral',
        'score': None,
        'note': '需同時取得台股與全球宏觀分數。',
    }
    if isinstance(local_score, (int, float)) and isinstance(global_score, (int, float)):
        combined = round((float(local_score) + float(global_score)) / 2)
        if local_score < 35 and global_score < 35:
            rlabel, rtone = '雙重 Risk-Off 共振', 'bad'
            rnote = '台股資金面與全球金融條件同時偏空，反彈優先視為風險修復。'
        elif local_score >= 55 and global_score >= 55:
            rlabel, rtone = 'Risk-On 共振', 'good'
            rnote = '台股與全球宏觀環境同時改善，風險承擔條件較完整。'
        elif local_score < 35 and global_score >= 45:
            rlabel, rtone = '台股偏弱、全球相對中性', 'warn'
            rnote = '主要壓力偏向台灣資金／籌碼面，需觀察外資與廣度是否回穩。'
        elif global_score < 35 and local_score >= 45:
            rlabel, rtone = '全球逆風、台股相對抗跌', 'warn'
            rnote = '全球金融條件偏緊，台股若續強需靠基本面與本地資金抵銷。'
        else:
            rlabel, rtone = '多空分歧', 'neutral'
            rnote = '本地與全球訊號未完全同向，降低單一訊號權重。'
        resonance = {'label': rlabel, 'tone': rtone, 'score': combined, 'note': rnote}

    warnings = len(live.get('errors') or [])
    data_note = f'模型完整度 {confidence:.0f}%；目前 {warnings} 個來源 warning。' if warnings else f'模型完整度 {confidence:.0f}%；本次來源無 warning。'

    return {
        'status': 'ready' if score is not None else 'partial',
        'generatedAt': live.get('generatedAt'),
        'phase': phase,
        'score': score,
        'label': label,
        'tone': tone_from_score(score),
        'headline': headline,
        'resonance': resonance,
        'quickTake': bullets[:4],
        'shortView': short_view,
        'swingView': swing_view,
        'invalidation': invalidation,
        'dataNote': data_note,
    }


def unique_trade_days(history, live):
    rows = []
    if isinstance(history, list):
        rows.extend(x for x in history if isinstance(x, dict))
    if isinstance(live, dict):
        rows.append(live)

    by_day = {}
    for row in rows:
        m = row.get('metrics') or {}
        day = str((m.get('taiex') or {}).get('asOf') or '')
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', day):
            continue
        # Keep the latest snapshot for each official trading day.
        old = by_day.get(day)
        if old is None or str(row.get('generatedAt') or '') > str(old.get('generatedAt') or ''):
            by_day[day] = row
    return [by_day[k] for k in sorted(by_day)]


def weekly_brief(history, live):
    days = unique_trade_days(history, live)
    recent = days[-5:]
    if len(recent) < 3:
        return {
            'status': 'collecting',
            'generatedAt': live.get('generatedAt'),
            'headline': '週報資料累積中：至少需要 3 個不同完整交易日，才建立自動週度趨勢。',
            'quickTake': [
                f'目前已累積 {len(recent)} 個不同交易日。',
                '系統會自動去除同一天的重複盤中／盤後快照，只保留該交易日最後有效資料。',
                '達到 3 日後先提供暫行週報；達到 5 日後形成完整 5 日週報。',
            ],
            'stats': [],
            'dataNote': '資料不足時不以單日數據偽裝週趨勢。',
        }

    scores = [r.get('risk', {}).get('score') for r in recent if isinstance(r.get('risk', {}).get('score'), (int, float))]
    first = recent[0]
    last = recent[-1]
    first_t = num((first.get('metrics', {}).get('taiex') or {}).get('value'))
    last_t = num((last.get('metrics', {}).get('taiex') or {}).get('value'))
    taiex_change = ((last_t / first_t - 1) * 100) if first_t and last_t else None

    fspot_sum = 0.0
    fspot_count = 0
    for r in recent:
        n = num((r.get('metrics', {}).get('foreignSpot') or {}).get('value'))
        if n is not None:
            fspot_sum += n
            fspot_count += 1

    first_tx = num((first.get('metrics', {}).get('foreignTx') or {}).get('value'))
    last_tx = num((last.get('metrics', {}).get('foreignTx') or {}).get('value'))
    tx_delta = last_tx - first_tx if first_tx is not None and last_tx is not None else None

    latest_breadth = breadth_ratio((last.get('metrics', {}).get('breadth') or {}).get('value'))
    avg_score = mean(scores) if scores else None
    start_score = scores[0] if scores else None
    end_score = scores[-1] if scores else None

    trend_word = '改善' if start_score is not None and end_score is not None and end_score > start_score + 3 else ('惡化' if start_score is not None and end_score is not None and end_score < start_score - 3 else '持平')
    headline = f'最近 {len(recent)} 個交易日 Risk Score 平均 {avg_score:.0f}，風險結構較期初{trend_word}。' if avg_score is not None else f'最近 {len(recent)} 個交易日資料已可形成暫行週報。'

    quick = []
    if taiex_change is not None:
        quick.append(f'指數：TAIEX 由 {first_t:,.2f} 到 {last_t:,.2f}，區間變動 {taiex_change:+.2f}%。')
    if fspot_count:
        quick.append(f'外資現貨：{fspot_count} 個不同交易日合計約 {fspot_sum:+,.0f} 億。')
    if tx_delta is not None:
        quick.append(f'外資 TX：期初 {first_tx:+,.0f} 口 → 期末 {last_tx:+,.0f} 口，變化 {tx_delta:+,.0f} 口。')
    if latest_breadth is not None:
        quick.append(f'最新市場廣度：上漲家數占漲跌家數約 {latest_breadth*100:.1f}%。')
    while len(quick) < 4:
        quick.append('週度自動報告只使用不同完整交易日，避免同日多次排程重複計算。')

    stats = [
        {'label': '交易日數', 'value': len(recent)},
        {'label': '平均 Risk Score', 'value': round(avg_score, 1) if avg_score is not None else None},
        {'label': '期末 Risk Score', 'value': round(end_score, 1) if end_score is not None else None},
        {'label': 'TAIEX 區間', 'value': round(taiex_change, 2) if taiex_change is not None else None},
    ]

    return {
        'status': 'ready',
        'generatedAt': live.get('generatedAt'),
        'headline': headline,
        'quickTake': quick[:4],
        'stats': stats,
        'dataNote': f'使用最近 {len(recent)} 個不同完整交易日；同一交易日只取最後有效快照。',
    }


def main():
    live = read_json(LIVE, {})
    hist = read_json(HISTORY, [])
    global_data = read_json(GLOBAL, {})
    if not isinstance(live, dict) or not live:
        raise SystemExit('data/live.json unavailable')

    obj = {
        'schemaVersion': 1,
        'generatedAt': live.get('generatedAt'),
        'daily': daily_brief(live, global_data),
        'weekly': weekly_brief(hist, live),
    }
    write_json(OUT, obj)
    print('✓ auto-brief.json generated')


if __name__ == '__main__':
    main()
