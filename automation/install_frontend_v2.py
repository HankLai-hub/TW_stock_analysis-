#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PACKAGE = ROOT / "package.json"
TAG = '  <script src="market-radar-v2.js?v=4.0.0"></script>'


def patch_index():
    text = INDEX.read_text(encoding="utf-8")
    if "market-radar-v2.js" in text:
        return False
    anchor = '  <script src="live.js?v=3.1.0"></script>'
    if anchor in text:
        text = text.replace(anchor, anchor + "\n" + TAG)
    else:
        text = text.replace("</body>", TAG + "\n</body>")
    INDEX.write_text(text, encoding="utf-8")
    return True


def patch_package():
    if not PACKAGE.exists():
        return False
    obj = json.loads(PACKAGE.read_text(encoding="utf-8"))
    scripts = obj.setdefault("scripts", {})
    check = scripts.get("check", "")
    if "market-radar-v2.js" not in check:
        if check:
            scripts["check"] = check.replace("node --check live.js", "node --check live.js && node --check market-radar-v2.js") if "node --check live.js" in check else check + " && node --check market-radar-v2.js"
        else:
            scripts["check"] = "node --check market-radar-v2.js"
        PACKAGE.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True
    return False


def main():
    print("index.html patched:", patch_index())
    print("package.json patched:", patch_package())


if __name__ == "__main__":
    main()
