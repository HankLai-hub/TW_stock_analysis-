#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'global.json'

obj = json.loads(PATH.read_text(encoding='utf-8'))
if not isinstance(obj, dict):
    raise SystemExit('global.json must be an object')
for key in ['generatedAt','macro','equity','news','events','reaction','risk','sources','errors']:
    if key not in obj:
        raise SystemExit(f'global.json missing {key}')

ranges = {
    'us2y': (0, 15), 'us10y': (0, 15), 'us30y': (0, 15),
    'real10y': (-5, 10), 'spread2s10s': (-1000, 1000),
    'wti': (5, 400), 'brent': (5, 400), 'broadDollar': (50, 200),
    'cpi': (-20, 30), 'coreCpi': (-20, 30), 'unemployment': (0, 30),
    'payrolls': (-5000, 5000), 'ahe': (-20, 30),
}
macro = obj.get('macro') or {}
for key, (lo, hi) in ranges.items():
    row = macro.get(key)
    if not isinstance(row, dict):
        continue
    value = row.get('value')
    if value is None:
        continue
    try:
        x = float(value)
    except Exception:
        raise SystemExit(f'{key}.value is not numeric: {value!r}')
    if not lo <= x <= hi:
        raise SystemExit(f'{key}.value out of range: {x}')

risk = obj.get('risk') or {}
score = risk.get('score')
if score is not None and not (0 <= float(score) <= 100):
    raise SystemExit(f'global risk score out of range: {score}')

news = obj.get('news') or []
if not isinstance(news, list):
    raise SystemExit('news must be a list')
for row in news[:20]:
    if not isinstance(row, dict):
        raise SystemExit('news item must be an object')
    impact = row.get('impact')
    if impact is not None and not (1 <= int(impact) <= 5):
        raise SystemExit(f'news impact out of range: {impact}')
    link = str(row.get('link') or '')
    if link and not link.startswith('https://'):
        raise SystemExit(f'news link must use https: {link}')

print('✓ global.json schema/plausibility OK')


events = obj.get('events') or []
if not isinstance(events, list):
    raise SystemExit('events must be a list')
for row in events[:30]:
    if not isinstance(row, dict):
        raise SystemExit('event item must be an object')
    impact = row.get('impact')
    if impact is not None and not (1 <= int(impact) <= 5):
        raise SystemExit(f'event impact out of range: {impact}')
    link = str(row.get('link') or '')
    if link and not link.startswith('https://'):
        raise SystemExit(f'event link must use https: {link}')

reaction = obj.get('reaction') or {}
if not isinstance(reaction, dict):
    raise SystemExit('reaction must be an object')
