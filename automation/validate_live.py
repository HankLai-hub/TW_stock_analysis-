import json
import re
from datetime import date
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "data" / "live.json"
obj = json.loads(path.read_text(encoding="utf-8"))
assert obj.get("schemaVersion") == 1
assert obj.get("generatedAt")
assert isinstance(obj.get("metrics"), dict)
required = {"taiex", "otc", "turnover", "breadth", "usdTwd", "tx", "foreignSpot", "foreignTx", "putCall", "margin"}
missing = required - set(obj["metrics"])
assert not missing, f"missing live metrics: {sorted(missing)}"
for key in required:
    row = obj["metrics"][key]
    assert isinstance(row, dict)
    for f in ("value", "asOf", "state", "source"):
        assert f in row, f"{key}: missing {f}"

# Plausibility guards: fail closed instead of publishing silently mis-mapped fields.
def pct(text):
    m = re.search(r"([+-]?[\d.]+)%", str(text or ""))
    return float(m.group(1)) if m else None

for key in ("taiex", "otc", "tx"):
    p = pct(obj["metrics"][key].get("change"))
    if p is not None:
        assert abs(p) <= 20, f"{key}: implausible daily percentage {p}% (possible field mapping error)"

b = str(obj["metrics"]["breadth"].get("value", ""))
m = re.search(r"([\d,]+)↑\s*/\s*([\d,]+)↓", b)
if m:
    up = int(m.group(1).replace(",", "")); down = int(m.group(2).replace(",", ""))
    assert 0 <= up <= 3000 and 0 <= down <= 3000, f"breadth: implausible stock counts {up}/{down}"

# Official TAIEX and turnover should refer to the same close when both are available.
td = obj["metrics"]["taiex"].get("asOf")
vd = obj["metrics"]["turnover"].get("asOf")
if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(td)) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(vd)):
    assert td == vd, f"TAIEX/turnover date mismatch: {td} vs {vd}"

print("live.json schema + plausibility OK")
