import json
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
print("live.json schema OK")
