#!/usr/bin/env python3
"""BaseWorkbench dry-run：只读生成测试 Base 字段重构计划。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import base_workbench, config, guard  # noqa: E402
from orchestrator.feishu_io import _call  # noqa: E402


TYPE_IDS = {
    "text": 1,
    "number": 2,
    "select": 3,
    "datetime": 5,
    "link": 21,
}


def _print_human(plan: dict) -> None:
    s = plan["summary"]
    print(f"BaseWorkbench dry-run schema={plan['schema_dir']}")
    print(
        f"  tables={s['tables_total']} add_missing={s['add_missing']} "
        f"delete_present={s['delete_present']} deprecate_present={s['deprecate_present']}"
    )
    if s["deprecate_tables"]:
        print(f"  deprecate_tables={', '.join(s['deprecate_tables'])}")
    if s["delete_tables"]:
        print(f"  delete_tables={', '.join(s['delete_tables'])}")
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


def _live_fields(table_id: str) -> dict[str, dict]:
    data = _call(
        "GET",
        f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{table_id}/fields",
        {"page_size": 100},
    )
    return {f.get("field_name") or f.get("name"): f for f in data.get("items", [])}


def _create_field(table_id: str, field: dict) -> None:
    body = base_workbench.simple_create_body(field)
    data = {
        "field_name": body["name"],
        "type": TYPE_IDS[body["type"]],
    }
    if body["type"] == "select" and body.get("property"):
        data["property"] = body["property"]
    _call(
        "POST",
        f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{table_id}/fields",
        data=data,
    )


def _create_link_field(table_id: str, field: dict) -> None:
    body = base_workbench.link_create_body(field, config.tables())
    _call(
        "POST",
        f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{table_id}/fields",
        data={
            "field_name": body["name"],
            "type": TYPE_IDS["link"],
            "property": body["property"],
        },
    )


def _delete_field(table_id: str, field_id: str) -> None:
    _call(
        "DELETE",
        f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{table_id}/fields/{field_id}",
    )


def _delete_table(table_id: str) -> None:
    _call(
        "DELETE",
        f"/open-apis/bitable/v1/apps/{config.BASE_TOKEN}/tables/{table_id}",
    )


def _apply_simple_adds(plan: dict) -> int:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    count = 0
    for field in base_workbench.simple_adds(plan):
        table_id = config.tables()[field["table"]]
        if field["field"] in _live_fields(table_id):
            print(f"  ↷ skip existing: {field['table']}.{field['field']}")
            continue
        _create_field(table_id, field)
        print(f"  + created: {field['table']}.{field['field']}")
        count += 1
    return count


def _apply_link_adds(plan: dict) -> int:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    count = 0
    for field in base_workbench.link_adds(plan):
        table_id = config.tables()[field["table"]]
        if field["field"] in _live_fields(table_id):
            print(f"  ↷ skip existing: {field['table']}.{field['field']}")
            continue
        _create_link_field(table_id, field)
        target = base_workbench.link_target_table(field)
        print(f"  + linked: {field['table']}.{field['field']} -> {target}")
        count += 1
    return count


def _apply_deletes(plan: dict) -> int:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    count = 0
    for field in base_workbench.present_deletes(plan):
        table_id = config.tables()[field["table"]]
        live = _live_fields(table_id)
        if field["field"] not in live:
            print(f"  ↷ skip absent: {field['table']}.{field['field']}")
            continue
        field_id = live[field["field"]]["field_id"]
        _delete_field(table_id, field_id)
        print(f"  - deleted: {field['table']}.{field['field']}")
        count += 1
    return count


def _apply_table_deletes(plan: dict) -> int:
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    count = 0
    for table in plan["tables"]:
        if table["table_action"] != "delete_table":
            continue
        try:
            table_id = config.tables()[table["table"]]
        except KeyError:
            print(f"  ↷ skip absent table: {table['table']}")
            continue
        _delete_table(table_id)
        print(f"  - deleted table: {table['table']}")
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema-dir", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply-simple-adds", action="store_true",
                    help="physically create missing text/select/number/datetime fields in the test Base")
    ap.add_argument("--apply-link-adds", action="store_true",
                    help="physically create approved missing DuplexLink fields in the test Base")
    ap.add_argument("--apply-deletes", action="store_true",
                    help="physically delete fields whose target action is delete_field")
    ap.add_argument("--apply-table-deletes", action="store_true",
                    help="physically delete tables whose target action is delete_table")
    args = ap.parse_args(argv)

    plan = base_workbench.build_plan(Path(args.schema_dir) if args.schema_dir else None)
    if args.schema_dir and (
        args.apply_simple_adds
        or args.apply_link_adds
        or args.apply_deletes
        or args.apply_table_deletes
    ):
        raise SystemExit("--apply-* must use the live configured schema/test + current Base, not an arbitrary schema dir")
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        _print_human(plan)
    if args.apply_simple_adds:
        n = _apply_simple_adds(plan)
        print(f"\n✅ applied simple field additions: {n}")
    if args.apply_link_adds:
        n = _apply_link_adds(plan)
        print(f"\n✅ applied link field additions: {n}")
    if args.apply_deletes:
        n = _apply_deletes(plan)
        print(f"\n✅ applied physical field deletes: {n}")
    if args.apply_table_deletes:
        n = _apply_table_deletes(plan)
        print(f"\n✅ applied physical table deletes: {n}")
    return 1 if base_workbench.has_blocking_drift(plan) else 0


if __name__ == "__main__":
    raise SystemExit(main())
