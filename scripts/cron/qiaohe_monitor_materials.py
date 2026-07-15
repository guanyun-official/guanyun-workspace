#!/usr/bin/env python3
"""qiaohe-monitor-materials pre-check (cheap cursor probe).

Single small GET, no pagination. Prints "NO_CHANGE" (agent should [SILENT])
or a summary of new material records for the agent to tag+ingest.
"""
from __future__ import annotations
import os, sys
from pathlib import Path

os.environ.setdefault("LARK_CLI_NO_PROXY", "1")
sys.path.insert(0, "/home/ubuntu/guanyun-workspace")

CURSOR = Path.home() / ".hermes" / "state" / "qiaohe-last-material-cursor"
CURSOR.parent.mkdir(parents=True, exist_ok=True)

from orchestrator import config, bitable
from orchestrator.feishu_io import _call

def main() -> int:
    tid = config.tables()[bitable.MaterialFields.TABLE]
    # Single page, page_size=20, no pagination (cheap)
    d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records",
              {"page_size": 20})
    items = d.get("items") or []
    if not items:
        print("NO_CHANGE")
        return 0

    # Bitable list endpoint returns oldest-first by default on some bases; sort
    # client-side by created_time desc to be safe.
    items.sort(key=lambda r: int(r.get("created_time") or 0), reverse=True)
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

    lines = [f"NEW_MATERIALS count={len(new_records)} newest_id={newest_id}"]
    for r in new_records:
        f = r.get("fields", {})
        code = bitable.text(f.get(bitable.MaterialFields.CODE, ""))
        note = bitable.text(f.get(bitable.MaterialFields.NOTE, ""))[:80]
        link = bitable.url(f.get(bitable.MaterialFields.LINK, ""))
        rel = bitable.text(f.get(bitable.MaterialFields.REL_PATH, ""))
        lines.append(f"- record_id={r.get('record_id')} code={code!r} link={link!r} rel={rel!r} note={note!r}")
    print("\n".join(lines))
    CURSOR.write_text(newest_id)
    return 0

if __name__ == "__main__":
    sys.exit(main())
