#!/usr/bin/env python3
"""qiaohe-monitor-status pre-check (cheap cursor probe on note status changes).

Uses last_modified_time to detect notes whose state changed since last tick.
Prints "NO_CHANGE" or a summary of changed notes for the agent to route.
"""
from __future__ import annotations
import os, sys, time as _time
from pathlib import Path

os.environ.setdefault("LARK_CLI_NO_PROXY", "1")
sys.path.insert(0, "/home/ubuntu/guanyun-workspace")

CURSOR_TS = Path.home() / ".hermes" / "state" / "qiaohe-last-status-ts"
CURSOR_TS.parent.mkdir(parents=True, exist_ok=True)

from orchestrator import config, bitable
from orchestrator.feishu_io import _call

def main() -> int:
    tid = config.tables()[bitable.NoteFields.TABLE]
    now_ms = int(_time.time() * 1000)
    last_ms = 0
    if CURSOR_TS.exists():
        try:
            last_ms = int(CURSOR_TS.read_text().strip() or "0")
        except (OSError, ValueError):
            last_ms = 0

    d = _call("GET", f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{tid}/records",
              {"page_size": 30})
    items = d.get("items") or []
    if not items:
        print("NO_CHANGE")
        CURSOR_TS.write_text(str(now_ms))
        return 0

    items.sort(key=lambda r: int(r.get("last_modified_time") or 0), reverse=True)
    changed = []
    for r in items:
        lm = int(r.get("last_modified_time") or 0)
        if lm <= last_ms:
            break
        changed.append(r)

    if not changed:
        print("NO_CHANGE")
        CURSOR_TS.write_text(str(now_ms))
        return 0

    lines = [f"STATUS_CHANGED count={len(changed)}"]
    for r in changed:
        f = r.get("fields", {})
        title = bitable.text(f.get(bitable.NoteFields.TITLE, ""))[:60]
        status = bitable.text(f.get(bitable.NoteFields.STATUS, ""))
        acct = bitable.link_names(f.get(bitable.NoteFields.ACCOUNT, ""))
        link = bitable.url(f.get(bitable.NoteFields.PUBLISH_LINK, ""))
        lm = int(r.get("last_modified_time") or 0)
        lines.append(
            f"- record_id={r.get('record_id')} title={title!r} status={status!r} acct={acct!r} link={link!r} last_modified={lm}"
        )
    print("\n".join(lines))
    CURSOR_TS.write_text(str(now_ms))
    return 0

if __name__ == "__main__":
    sys.exit(main())
