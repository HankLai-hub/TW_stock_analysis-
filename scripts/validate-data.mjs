import fs from 'node:fs';
import vm from 'node:vm';

const code = fs.readFileSync(
  new URL('../data.js', import.meta.url),
  'utf8'
);

const sandbox = { window: {} };

vm.createContext(sandbox);
vm.runInContext(code, sandbox);

const data = sandbox.window.MARKET_DASHBOARD_DATA;

if (
  !data?.daily ||
  !data?.weekly ||
  !Array.isArray(data.sources)
) {
  throw new Error('核心資料結構缺漏');
}

for (const mode of ['daily', 'weekly']) {
  const d = data[mode];

  const required = [
    'meta',
    'score',
    'kpis',
    'marketThemes',
    'global',
    'focus',
    'news',
    'flow',
    'derivatives',
    'leverage',
    'breadth',
    'sectors',
    'levels',
    'scenarios',
    'events',
    'freshness'
  ];

  for (const key of required) {
    if (d[key] == null) {
      throw new Error(`${mode}.${key} 缺漏`);
    }
  }

  if (d.score < 0 || d.score > 100) {
    throw new Error(`${mode}.score 超出 0-100`);
  }

  if (d.kpis.length < 4) {
    throw new Error(`${mode}.kpis 太少`);
  }

  if (d.focus.length !== 5) {
    throw new Error(`${mode}.focus 必須正好 5 項`);
  }
}

console.log('✓ data.js schema OK');
