#!/usr/bin/env python3
"""从备份 JSON 恢复一张表到测试库(补齐"误删可恢复"的 restore 半边)。

  python3 -m scripts.restore_tables backups/test-20260712 灵感库          # dry-run:打印将恢复什么,不写
  python3 -m scripts.restore_tables backups/test-20260712 灵感库 --write   # 过红线闸恢复到测试库

link 字段(账号/内容类型/关联素材…)按备份里的名字(text_arr)在**当前** base 重解析成新 record_id
(备份里的旧 record_id 失效);解析不到的 link 丢弃、不写。computed/写不了的字段单条 create 失败即跳过并报告。
红线:只测试库(TEST_MODE 下写库闸拒生产);默认 dry-run。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import config, draft, feishu_io, guard  # noqa: E402

# link-target 表的主字段(link.text_arr 里的名字对应它);schema fields[0] 不可靠(如账号表首字段是 workspace_ref)
_PRIMARY = {
    "账号表": "账号名", "内容类型表": "内容类型名", "素材表": "素材编号", "笔记表": "标题",
    "灵感库": "标题", "关键词库": "关键词", "目标客户": "主页链接", "衣服总表": "衣服编号",
}


def _table_name_by_id() -> dict[str, str]:
    return {tid: name for name, tid in config.tables().items()}


def _primary_field(table_name: str) -> str | None:
    """link-target 表的主字段名(重解析按它匹配名字)。未知表回退 schema 首字段(可能不准,会丢 link 并报告)。"""
    if table_name in _PRIMARY:
        return _PRIMARY[table_name]
    p = config.WORKSPACE / "schema" / "test" / f"{table_name}.json"
    try:
        fs = json.loads(p.read_text(encoding="utf-8")).get("fields") or []
        return fs[0]["field_name"] if fs else None
    except Exception:
        return None


def _is_link_value(v) -> bool:
    return isinstance(v, list) and bool(v) and isinstance(v[0], dict) and "record_ids" in v[0]


def restore_fields(fields: dict, tbl_by_id: dict[str, str]) -> dict:
    """备份 fields → 可写 fields:link 按名在当前 base 重解析;解析不到的 link 丢弃;其余原样。"""
    out = {}
    for k, v in fields.items():
        if _is_link_value(v):
            ids: list[str] = []
            for e in v:
                target = tbl_by_id.get(e.get("table_id"))
                nf = _primary_field(target) if target else None
                if target and nf:
                    for name in (e.get("text_arr") or []):
                        ids += draft._resolve_link(target, nf, name)
            if ids:
                out[k] = ids            # 解析到才写(否则丢弃该 link,不写孤儿)
        else:
            out[k] = v                  # scalar/text/url({link,text})/number 原样
    return out


def restore(backup_dir: str, table: str, write: bool = False) -> dict:
    recs = json.loads((Path(backup_dir) / f"{table}.json").read_text(encoding="utf-8"))
    tbl_by_id = _table_name_by_id()
    existing = len(feishu_io.list_records(table))
    print(f"备份 {table}: {len(recs)} 条 | 当前 base: {existing} 条")
    if not write:
        for r in recs[:3]:
            f = restore_fields(r["fields"], tbl_by_id)
            preview = {k: (f"link×{len(v)}" if isinstance(v, list) else v) for k, v in list(f.items())[:5]}
            print("  将恢复:", preview)
        print("(dry-run:未写库。加 --write 恢复到测试库)")
        return {"备份": len(recs), "恢复": 0, "跳过": 0}
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只测试库
    done, degraded, skip = 0, 0, 0
    for r in recs:
        f = restore_fields(r["fields"], tbl_by_id)
        try:
            feishu_io.create_record(table, f)
            done += 1
        except Exception:  # noqa: BLE001
            # 降级重试:丢掉所有 link(反向link/lookup/失效link 常写不回),保底恢复核心数据
            core = {k: v for k, v in f.items() if not isinstance(v, list)}
            try:
                feishu_io.create_record(table, core)
                degraded += 1
            except Exception as e:  # noqa: BLE001
                skip += 1
                print(f"  跳过一条(核心字段也写不回):{str(e)[:80]}")
    print(f"✅ 恢复 {done + degraded} 条到测试库 {table}(完整 {done} / 丢link降级 {degraded} / 跳过 {skip})")
    return {"备份": len(recs), "恢复": done + degraded, "完整": done, "降级": degraded, "跳过": skip}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backup_dir")
    ap.add_argument("table")
    ap.add_argument("--write", action="store_true", help="过红线闸恢复到测试库(默认 dry-run)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE}")
    restore(a.backup_dir, a.table, write=a.write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
