#!/usr/bin/env python3
"""每日备份:关键表全记录 dump 到 backups/<env>-<日期>/<表名>.json(误删可恢复;gitignore)。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402

TABLES = ["笔记表", "素材表", "账号表", "衣服总表", "运行日志表"]


def main() -> int:
    out = config.WORKSPACE / "backups" / f"{config.ENV_NAME}-{datetime.now():%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        recs = feishu_io.list_records(t)
        (out / f"{t}.json").write_text(
            json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {t}: {len(recs)} 条")
    print(f"✅ 备份 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
