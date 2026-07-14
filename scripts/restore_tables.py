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

from orchestrator import config, feishu_io, guard, notes  # noqa: E402

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
                        ids += notes.resolve_link(target, nf, name)
            if ids:
                out[k] = ids            # 解析到才写(否则丢弃该 link,不写孤儿)
        else:
            out[k] = v                  # scalar/text/url({link,text})/number 原样
    return out


def _fingerprint(fields: dict) -> tuple:
    """一条记录的**身份指纹**:所有标量字段(排除 link/附件/公式等 list/dict)的 (字段名, 值) 排序元组。
    恢复靠它判断"库里已经有这条了吗" —— 备份里的旧 record_id 在当前 base 已失效,不能拿来比。"""
    from orchestrator import bitable
    out = []
    for k, v in (fields or {}).items():
        if isinstance(v, (list, dict)):
            continue                       # link/附件/lookup:跨 base 不稳定,不进指纹
        s = bitable.text(v).strip()
        if s:
            out.append((k, s))
    return tuple(sorted(out))


def restore(backup_dir: str, table: str, write: bool = False) -> dict:
    """从备份恢复一张表 —— **只补库里缺的那些,绝不重灌已有的**。

    2026-07-14 真跑 L14(真删一条 → 真恢复 → 读回验证)才发现:**它根本不是"恢复",是"盲目重灌"**。
    原实现把备份里每一条都 `create_record` 一遍,**完全不看库里已经有没有**:
        关键词库 32 条 → 真删 1 条(31)→ 跑恢复 → **38 条**(凭空多出 7 条重复),
        而被误删的那一条**始终没回来**(它只是在按备份顺序无脑重插,插到哪算哪)。
    **「误删可恢复」是假的** —— 它不是恢复,是复制粘贴,而且是**破坏性的**:
    在还有数据的表上跑一次,整张表就翻倍污染。
    备份脚本有、恢复脚本有、门也绿 —— **但"真删一条再恢复"从来没人真验过**。

    现在:按**指纹**(所有标量字段)比对,只 create 库里**缺失**的记录。幂等——跑几次结果一样。
    """
    recs = json.loads((Path(backup_dir) / f"{table}.json").read_text(encoding="utf-8"))
    tbl_by_id = _table_name_by_id()
    live = feishu_io.list_records(table)
    have = {_fingerprint(r["fields"]) for r in live}
    missing = [r for r in recs if _fingerprint(r["fields"]) not in have]
    print(f"备份 {table}: {len(recs)} 条 | 当前 base: {len(live)} 条 | "
          f"**库里缺的: {len(missing)} 条**(只补这些,已有的绝不重灌)")
    if not missing:
        print("✅ 库里一条都不缺,无需恢复(幂等)")
        return {"备份": len(recs), "缺失": 0, "恢复": 0, "完整": 0, "降级": 0, "跳过": 0}
    if not write:
        for r in missing[:5]:
            f = restore_fields(r["fields"], tbl_by_id)
            preview = {k: (f"link×{len(v)}" if isinstance(v, list) else v) for k, v in list(f.items())[:5]}
            print("  将补回:", preview)
        print("(dry-run:未写库。加 --write 恢复到测试库)")
        return {"备份": len(recs), "缺失": len(missing), "恢复": 0, "跳过": 0}
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只测试库
    done, degraded, skip = 0, 0, 0
    for r in missing:
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
    print(f"✅ 补回 {done + degraded} 条缺失记录(完整 {done} / 丢link降级 {degraded} / 跳过 {skip})"
          f" —— 已有的一条没动")
    return {"备份": len(recs), "缺失": len(missing), "恢复": done + degraded,
            "完整": done, "降级": degraded, "跳过": skip}


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
