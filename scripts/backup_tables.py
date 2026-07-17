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
    ok, failed = 0, []
    for t in tables:
        try:
            recs = feishu_io.list_records(t)
        except Exception as e:  # noqa: BLE001  单表失败不拖垮整轮备份,其余照备
            print(f"  ✗ {t}: {e}")
            failed.append(t)
            continue
        (out / f"{t}.json").write_text(
            json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {t}: {len(recs)} 条")
        ok += 1

    # ★备份只有"全备成"才叫备成★(2026-07-17 修):
    # 旧代码 `print(f"✅ 备份 {ok}/…")` 里的 ✅ **是写死的** —— 0/11 也打 ✅,印在 11 个 ✗ 底下。
    # 更毒的是旧的 `return 0 if ok else 1`:备成 **5/11 就返 0,门变绿** ——
    # 而没备成的那 6 张**根本没有备份**。然后有人信着这个绿去做 schema 操作,
    # 恰好抹的就是那 6 张里的一张(2026-07-14 真发生过:一次 PUT 抹空 280 行)。
    # **半份备份 ≠ 备份。** 读不到 ≠ 0 张 —— 缺哪几张必须点名说出来。
    if failed:
        print(f"❌ 备份 {ok}/{len(tables)} 表 → {out}")
        print(f"   **没备成:{'、'.join(failed)}** —— 这几张现在**没有备份**,误删恢复不了。"
              f"别拿这次备份当护身符去做 schema 操作。")
        return 1
    print(f"✅ 备份 {ok}/{len(tables)} 表 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
