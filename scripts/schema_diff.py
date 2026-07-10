#!/usr/bin/env python3
"""
schema_diff.py — 对比两份 schema dump(dump_schema.py 产出目录),输出差异。

用法:
  python3 scripts/schema_diff.py <before_dir> <after_dir>              # 只打差异报告
  python3 scripts/schema_diff.py <before_dir> <after_dir> --assert-p2  # 断言 P2 预期:
      只有登记过的受控新增/删除；零表删除、零改类型、零 select 选项删除,
      预期外新增/删除也算失败。

exit 0 = 通过;exit 1 = 断言失败或目录/文件问题。
纯本地文件对比,零网络零写入。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 自「改造前」快照以来所有**有意**的测试库 schema 变更登记表(P2 首批 + 后续架构演进逐条追加)。
# 这是 schema-diff 硬闸的白名单:登记过的算预期,没登记的新增/删除/改类型/改名一律报红——
# 加/删字段时必须来这里登记一行,否则 check_p2 会拦住(反漂移:UI/误操作改 schema 无所遁形)。
P2_EXPECTED = {
    "added_fields": {
        ('Issue 表', 'github_issue_url', 'text'),
        ('Issue 表', '归属域', 'select'),
        ('修订日志', '修订类型', 'select'),
        ('修订日志', '审核人', 'text'),
        ('关键词库', '启用状态', 'select'),
        ('关键词库', '平台', 'select'),
        ('关键词库', '禁用原因', 'text'),
        ('内容类型表', 'slug', 'text'),
        ('内容类型表', 'workspace_playbook_ref', 'text'),
        ('内容类型表', '启用状态', 'select'),
        ('内容类型表', '展示顺序', 'number'),
        ('灵感库', '去重键', 'text'),
        ('灵感库', '可借鉴点', 'text'),
        ('灵感库', '来源平台', 'select'),
        ('灵感库', '来源账号', 'text'),
        ('灵感库', '禁用片段/搬运风险', 'text'),
        ('灵感库', '采集时间', 'datetime'),
        ('目标客户', '人群假设', 'text'),
        ('目标客户', '更新时间', 'datetime'),
        ('目标客户', '证据链接', 'text'),
        ('笔记表', 'AI声明', 'checkbox'),
        ('笔记表', '关联子素材', 'text'),
        ('笔记表', '发布包路径', 'text'),
        ('笔记表', '数据用途', 'select'),
        ('笔记表', '方法论', 'text'),
        ('笔记表', '运行批次', 'text'),
        ('素人推广案例', '合作状态', 'select'),
        ('素人推广案例', '素材授权状态', 'select'),
        ('素人推广案例', '转化指标', 'text'),
        ('素材表', '数据用途', 'select'),
        ('素材表', '相对路径', 'text'),
        ('素材表', '素材哈希', 'text'),
        ('素材表', '验收状态', 'select'),
        ('衣服总表', '内容优先级', 'select'),
        ('衣服总表', '生命周期状态', 'select'),
        ('衣服总表', '素材缺口摘要', 'text'),
        ('账号表', 'workspace_ref', 'text'),
        ('账号表', '画像更新时间', 'datetime'),
        ('账号表', '画像状态', 'select'),
        ('账号表', '自动排产', 'select'),
        ('运行日志表', 'automation_id', 'text'),
        ('运行日志表', 'duration_ms', 'number'),
        ('运行日志表', 'error_type', 'text'),
        ('运行日志表', 'run_id', 'text'),
        ('运行日志表', '成本_元', 'number'),
        ('运行日志表', '数据用途', 'select'),
        ('面料·工艺库', '事实来源', 'text'),
        ('面料·工艺库', '可信级别', 'select'),
        ('面料·工艺库', '禁用说法', 'text'),
    },
    "removed_fields": {
        ('内容类型表', '取数字段·切面', 'text'),
        ('内容类型表', '文案元模版', 'text'),
    },
    "added_options": {
        ('笔记表', '状态', '已回流'),
        ('笔记表', '状态', '已批准'),
        ('笔记表', '状态', '待发布'),
    },
}

def load_dir(d: Path) -> dict[str, dict]:
    tables = {}
    for p in sorted(d.glob("*.json")):
        if p.name == "_tables.json":
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        tables[t["table_name"]] = t
    if not tables:
        raise SystemExit(f"❌ {d} 下没有表契约 json")
    return tables


def diff(before: dict, after: dict):
    """返回 (added_tables, removed_tables, added_fields, removed_fields,
             type_changes, added_options, removed_options)"""
    added_tables = sorted(set(after) - set(before))
    removed_tables = sorted(set(before) - set(after))
    added_fields, removed_fields, type_changes = [], [], []
    added_options, removed_options = [], []

    for tname in sorted(set(before) & set(after)):
        bf = {f["field_name"]: f for f in before[tname]["fields"]}
        af = {f["field_name"]: f for f in after[tname]["fields"]}
        for fn in sorted(set(af) - set(bf)):
            added_fields.append((tname, fn, af[fn].get("type", "?")))
        for fn in sorted(set(bf) - set(af)):
            removed_fields.append((tname, fn, bf[fn].get("type", "?")))
        for fn in sorted(set(bf) & set(af)):
            bt, at = bf[fn].get("type"), af[fn].get("type")
            if bt != at:
                type_changes.append((tname, fn, bt, at))
            bo = set(bf[fn].get("options") or [])
            ao = set(af[fn].get("options") or [])
            for o in sorted(ao - bo):
                added_options.append((tname, fn, o))
            for o in sorted(bo - ao):
                removed_options.append((tname, fn, o))
    return (added_tables, removed_tables, added_fields, removed_fields,
            type_changes, added_options, removed_options)


def main() -> int:
    ap = argparse.ArgumentParser(description="schema dump 目录差异对比")
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--assert-p2", action="store_true",
                    help="断言差异 == 已登记的测试 Base 受控迁移")
    args = ap.parse_args()

    before = load_dir(Path(args.before))
    after = load_dir(Path(args.after))
    (at, rt, af_, rf, tc, ao, ro) = diff(before, after)

    print(f"对比: {args.before}  →  {args.after}")
    print(f"  表: {len(before)} → {len(after)}")
    for x in at:
        print(f"  + 新增表: {x}")
    for x in rt:
        print(f"  - 删除表: {x}")
    for t, f, ty in af_:
        print(f"  + 新增字段: {t}.{f} ({ty})")
    for t, f, ty in rf:
        print(f"  - 删除字段: {t}.{f} ({ty})")
    for t, f, b, a in tc:
        print(f"  ~ 类型变更: {t}.{f}  {b} → {a}")
    for t, f, o in ao:
        print(f"  + 新增选项: {t}.{f} += 「{o}」")
    for t, f, o in ro:
        print(f"  - 删除选项: {t}.{f} -= 「{o}」")
    if not any([at, rt, af_, rf, tc, ao, ro]):
        print("  (无差异)")

    if not args.assert_p2:
        return 0

    errors = []
    if at:
        errors.append(f"预期外新增表: {at}")
    if rt:
        errors.append(f"删除了表(禁止): {rt}")
    if tc:
        errors.append(f"字段类型被改(禁止): {tc}")
    if ro:
        errors.append(f"删除了 select 选项(禁止): {ro}")
    got_f = set(af_)
    if got_f != P2_EXPECTED["added_fields"]:
        errors.append(f"新增字段 ≠ 预期: 实际={sorted(got_f)} 预期={sorted(P2_EXPECTED['added_fields'])}")
    got_rf = set(rf)
    if got_rf != P2_EXPECTED.get("removed_fields", set()):
        errors.append(f"删除字段 ≠ 预期: 实际={sorted(got_rf)} 预期={sorted(P2_EXPECTED.get('removed_fields', set()))}")
    got_o = set(ao)
    if got_o != P2_EXPECTED["added_options"]:
        errors.append(f"新增选项 ≠ 预期: 实际={sorted(got_o)} 预期={sorted(P2_EXPECTED['added_options'])}")

    if errors:
        print("\n❌ 断言失败:")
        for e in errors:
            print(f"  · {e}")
        return 1
    print("\n✅ 断言通过:只有登记过的受控新增/删除,零表删零改类型零删选项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
