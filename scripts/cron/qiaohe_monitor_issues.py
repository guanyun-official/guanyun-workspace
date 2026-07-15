#!/usr/bin/env python3
"""qiaohe-monitor-issues pre-check (cheap cursor probe)."""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("LARK_CLI_NO_PROXY", "1")
sys.path.insert(0, "/home/ubuntu/guanyun-workspace")

CURSOR = Path.home() / ".hermes" / "state" / "qiaohe-last-issue-cursor"
CURSOR.parent.mkdir(parents=True, exist_ok=True)

from orchestrator import config, bitable
from orchestrator.feishu_io import _call

TABLE = "Issue 表"

def _text(v):
    return bitable.text(v) if v is not None else ""

def main() -> int:
    tid = config.tables()[TABLE]
    d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records",
              {"page_size": 20})
    items = d.get("items") or []
    if not items:
        print("NO_CHANGE")
        return 0

    items.sort(key=lambda r: int(r.get("last_modified_time") or r.get("created_time") or 0),
               reverse=True)
    newest_id = items[0].get("record_id", "")

    last_seen = CURSOR.read_text().strip() if CURSOR.exists() else ""
    new_records = []
    for r in items:
        if r.get("record_id") == last_seen:
            break
        new_records.append(r)

    if not new_records:
        print("NO_CHANGE")
        if newest_id:
            CURSOR.write_text(newest_id)
        return 0

    lines = [f"NEW_ISSUES count={len(new_records)} newest_id={newest_id}"]
    for r in new_records:
        f = r.get("fields", {})
        title = _text(f.get("Issue 标题") or f.get("标题") or f.get("需求") or "")[:80]
        status = _text(f.get("状态") or "")
        desc = _text(f.get("需求描述") or f.get("描述") or f.get("解决方案") or "")[:120]
        domain = _text(f.get("归属域") or "")
        lines.append(f"- record_id={r.get('record_id')} title={title!r} status={status!r} domain={domain!r} desc={desc!r}")
    print("\n".join(lines))
    CURSOR.write_text(newest_id)
    return 0

if __name__ == "__main__":
    sys.exit(main())
