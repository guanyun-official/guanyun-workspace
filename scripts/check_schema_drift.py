#!/usr/bin/env python3
"""活 schema 漂移探针(ADR-0009 P1『读侧漂告警接进运营 cron 前置』)。

test_schema_contract 是**离线**契约(代码词汇 ⊆ 上次 dump 的**快照**)——只抓"代码 vs 快照"漂移,
抓不到"飞书 UI 改了字段/选项但没人重跑 dump"(快照本身过期)。本探针补这个盲区:
**实时拉当前 Base 的 field-list,断言代码消费的字段名/枚举值 ⊆ 活 schema**,漂了非0退出(+可告警)。

只读(lark-cli field-list/table-list),对任何 Base 零写入。cron 前置跑:漂移=停后续自动化,别拿错字段空跑。

  python3 scripts/check_schema_drift.py            # 查当前 .env 的 Base(测试库即测试库)
  python3 scripts/check_schema_drift.py --alert     # 漂了发飞书私聊(cron 用)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrator import bitable as B, config          # noqa: E402
from scripts.dump_schema import _lark, _field_contract  # noqa: E402  复用只读拉取,不重造

# 词汇类 → 表名(与 test_schema_contract 同一张表,单一真相)
VOCAB_TABLE = [
    (B.NoteFields, "笔记表"), (B.MaterialFields, "素材表"), (B.AccountFields, "账号表"),
    (B.RunLogFields, "运行日志表"), (B.ContentTypeFields, "内容类型表"),
    (B.InspirationFields, "灵感库"), (B.KeywordFields, "关键词库"),
    (B.NoteStatus, "笔记表"), (B.AutoSched, "账号表"),
    (B.MaterialStatus, "素材表"), (B.MaterialSource, "素材表"),
]


def _live_names_opts(token: str, table_id: str) -> set[str]:
    """活 schema:该表字段名 ∪ 所有 select 选项(与离线契约同款 union 判定)。"""
    fields = _lark(["+field-list", "--base-token", token, "--table-id", table_id])["data"]["fields"]
    out: set[str] = set()
    for f in fields:
        c = _field_contract(f)
        out.add(c["field_name"])
        out.update(c.get("options") or [])
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true", help="漂移发飞书私聊(cron 用)")
    args = ap.parse_args()
    token = config.BASE_TOKEN
    if not token:
        print("❌ LARK_APP_TOKEN 为空,无法探测活 schema", file=sys.stderr)
        return 2
    print(f"活 schema 漂移探针 · Base={config.ENV_NAME}({token[:8]}…)")
    tid_of = {t["name"]: t["id"] for t in _lark(["+table-list", "--base-token", token])["data"]["tables"]}

    drift: list[str] = []
    for cls, table in VOCAB_TABLE:
        tid = tid_of.get(table)
        if not tid:
            drift.append(f"{table}: 活库无此表(整表改名/删除?)")
            continue
        live = _live_names_opts(token, tid)
        miss = set(B.declared_field_names(cls)) - live
        mark = "✗" if miss else "✓"
        print(f"  {mark} {cls.__name__:20}→{table:8} {'漂移:' + str(sorted(miss)) if miss else '对齐'}")
        if miss:
            drift.append(f"{cls.__name__}({table}):{sorted(miss)}")

    if drift:
        msg = "活 schema 漂移(代码消费的字段/枚举不在活库,会静默读空/写失败):" + "；".join(drift)
        print(f"❌ {msg}")
        if args.alert:
            try:
                from orchestrator import alerts
                alerts.send(msg, title="巧荷 schema 漂移⚠️")
            except Exception as e:  # noqa: BLE001
                print(f"(告警投递失败 {str(e)[:60]})", file=sys.stderr)
        return 1
    print("✅ 代码词汇全部对齐活 schema,无读侧漂移。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
