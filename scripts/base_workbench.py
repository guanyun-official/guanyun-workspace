#!/usr/bin/env python3
"""BaseWorkbench dry-run：只读生成测试 Base 字段重构计划。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import base_workbench  # noqa: E402


def _print_human(plan: dict) -> None:
    s = plan["summary"]
    print(f"BaseWorkbench dry-run schema={plan['schema_dir']}")
    print(
        f"  tables={s['tables_total']} add_missing={s['add_missing']} "
        f"delete_present={s['delete_present']} deprecate_present={s['deprecate_present']}"
    )
    if s["deprecate_tables"]:
        print(f"  deprecate_tables={', '.join(s['deprecate_tables'])}")
    if s["rename_tables"]:
        print(f"  rename_tables={', '.join(s['rename_tables'])}")
    if s["missing_target_tables"] or s["unknown_tables"]:
        print(f"  missing_target_tables={s['missing_target_tables']}")
        print(f"  unknown_tables={s['unknown_tables']}")
    for table in plan["tables"]:
        actionable = [f for f in table["fields"] if f["status"] in {"missing", "present"}]
        if not actionable and table["table_action"] == "keep":
            continue
        print(f"\n[{table['table']}] table_action={table['table_action']} — {table['reason']}")
        for f in actionable:
            suffix = f" ({f['field_type']})" if f["action"] == "add" else ""
            print(f"  - {f['action']}: {f['field']}{suffix} — {f['reason']}")
    if base_workbench.has_blocking_drift(plan):
        print("\n❌ BaseWorkbench 目标清单与 schema 表集合不一致")
    else:
        print("\n✅ BaseWorkbench dry-run 可执行：字段动作待迁移，表集合无漂移")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema-dir", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    plan = base_workbench.build_plan(Path(args.schema_dir) if args.schema_dir else None)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        _print_human(plan)
    return 1 if base_workbench.has_blocking_drift(plan) else 0


if __name__ == "__main__":
    raise SystemExit(main())
