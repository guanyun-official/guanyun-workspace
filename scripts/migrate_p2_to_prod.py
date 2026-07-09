#!/usr/bin/env python3
"""历史工具:把 MIGRATION_P2 变更应用到生产 Base(只加不删)。

当前上线流程已改为在运营库 ZhzJbf(TEST_MODE=1) 挂 cron；不切 N9IVbi,不改 TEST_MODE=0。
本脚本不属于当前 P7 上线路径,仅作为历史迁移/审计工具保留。若未来明确恢复生产迁移,
仍需下面三重硬门:
  1) 默认 dry-run 只打印计划;真应用须 --apply
  2) --apply 必须 TEST_MODE=0 且 env PROD_CONFIRM=OK(人工显式两把钥匙)
  3) 应用前强制拍生产 schema 快照(回滚依据)
变更集(与测试 Base 对齐,来源 docs/MIGRATION_P2.md):
  笔记表.状态 += 已批准/待发布/已回流(回填原 option id);笔记表 +AI声明(checkbox)
用法: python3 scripts/migrate_p2_to_prod.py            # 预览
      TEST_MODE=0 PROD_CONFIRM=OK python3 scripts/migrate_p2_to_prod.py --apply
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config  # noqa: E402
from orchestrator.feishu_io import _call  # noqa: E402

NEW_OPTIONS = ["已批准", "待发布", "已回流"]
PROD = config.PROD_BASE


def main() -> int:
    apply = "--apply" in sys.argv
    if apply:
        assert os.environ.get("TEST_MODE") == "0" and os.environ.get("PROD_CONFIRM") == "OK", \
            "真应用需要 TEST_MODE=0 且 PROD_CONFIRM=OK(两把钥匙)"
        assert config.BASE_TOKEN == PROD, "LARK_APP_TOKEN 必须指向生产 Base"
    base = PROD  # 读取目标一律生产(dry-run 也读生产做差异计划,零写入)

    tables = {t["name"]: t["table_id"] for t in _call(
        "GET", f"/open-apis/bitable/v1/apps/{base}/tables")["items"]}
    note_tid = tables["笔记表"]
    fields = _call("GET", f"/open-apis/bitable/v1/apps/{base}/tables/{note_tid}/fields",
                   {"page_size": 100})["items"]
    status = next(f for f in fields if f["field_name"] == "状态")
    existing = [o["name"] for o in status["property"]["options"]]
    to_add = [o for o in NEW_OPTIONS if o not in existing]
    has_ai = any(f["field_name"] == "AI声明" for f in fields)

    print(f"目标:生产 Base {base[:8]}… 笔记表 {note_tid}")
    print(f"  状态现有 {len(existing)} 枚举;计划追加: {to_add or '无(已齐)'}")
    print(f"  AI声明字段: {'已存在' if has_ai else '计划新增 checkbox'}")
    if not apply:
        print("\n[dry-run] 未做任何写入。真应用见文件头用法。")
        return 0

    # 快照(硬门3)
    snap = config.WORKSPACE / "schema" / "snapshots" / f"prod-切换前-{datetime.now():%Y%m%d}"
    subprocess.run([sys.executable, "scripts/dump_schema.py", "--base", "prod"],
                   cwd=config.WORKSPACE, check=True)
    if snap.exists():
        shutil.rmtree(snap)
    shutil.copytree(config.WORKSPACE / "schema" / "prod", snap)
    print(f"  快照 → {snap}")

    if to_add:
        options = [{"id": o["id"], "name": o["name"]} for o in status["property"]["options"]]
        options += [{"name": n} for n in to_add]
        _call("PUT", f"/open-apis/bitable/v1/apps/{base}/tables/{note_tid}/fields/{status['field_id']}",
              data={"field_name": "状态", "type": 3, "property": {"options": options}})
        print(f"  ✓ 状态 += {to_add}")
    if not has_ai:
        _call("POST", f"/open-apis/bitable/v1/apps/{base}/tables/{note_tid}/fields",
              data={"field_name": "AI声明", "type": 7})
        print("  ✓ 新增 AI声明(checkbox)")
    subprocess.run([sys.executable, "scripts/dump_schema.py", "--base", "prod"],
                   cwd=config.WORKSPACE, check=True)
    print("✅ 迁移完成;请跑 schema_diff 复核(只应看到本次新增)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
