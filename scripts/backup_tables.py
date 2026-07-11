#!/usr/bin/env python3
"""每日备份:关键表全记录 dump 到 backups/<env>-<日期>/<表名>.json(误删可恢复;gitignore)。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, feishu_io  # noqa: E402


def main() -> int:
    out = config.WORKSPACE / "backups" / f"{config.ENV_NAME}-{datetime.now():%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    tables = list(config.tables().keys())  # 全表备份:完整不漏(误删可恢复),自适应 schema 增删表
    ok = 0
    for t in tables:
        try:
            recs = feishu_io.list_records(t)
        except Exception as e:  # noqa: BLE001  单表失败不拖垮整轮备份,其余照备
            print(f"  ✗ {t}: {e}")
            continue
        (out / f"{t}.json").write_text(
            json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {t}: {len(recs)} 条")
        ok += 1
    print(f"✅ 备份 {ok}/{len(tables)} 表 → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
