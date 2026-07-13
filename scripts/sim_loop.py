#!/usr/bin/env python3
"""闭环模拟(上线态验收·全账号全模式):对每个账号×模式走完整闭环一圈,证都能闭环。

一圈 = 薄执行器出【文案+选定素材】完整包草稿 → 模拟人审人发(改 状态=已发 + 发布链接 + 发布日,
       **仅模拟、代替人手**)→ 模拟回流(写 mock 点赞/收藏,代替真采集)→ metrics.aggregate 按方法论复盘。

红线:这是**开发验收模拟**,不是生产路径。真发布 / 勾 AI 声明 永远是人手,薄执行器绝不自动发布;
本脚本用 _SIM 前缀写测试库、跑完清场(只删本脚本建的 record),零 LLM(stub 默认)。

用法:
  python3 -m scripts.sim_loop            # 4 号各走一圈 + 复盘,跑完清场
  python3 -m scripts.sim_loop --keep     # 保留 _SIM 记录(在飞书看流转)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/sim_loop.py 也能跑(不止 -m)

from orchestrator import accounts, config, draft, feishu_io, guard, metrics
from orchestrator import bitable
from orchestrator.bitable import AccountFields as AF, ContentTypeFields as CTF
from orchestrator.bitable import NoteFields as NF, NoteStatus as NS

SIM = "_SIM-闭环"


def _link(table: str, name_field: str, name: str) -> list[str]:
    return [r["record_id"] for r in feishu_io.list_records(table)
            if bitable.text(r["fields"].get(name_field)).strip() == name]


def sim_one(account_name: str, content_type: str = "", liked: int = 128, collected: int = 32) -> dict:
    """走一圈闭环:出完整包→模拟已发+回流→写测试库 _SIM 已发 note。返回该圈事实(供复盘/断言)。
    content_type 给定=一号多模式时走指定模式(否则第一套)。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    r = draft.generate_draft(account_name, llm_mode="stub", content_type=content_type)
    acc = _link(AF.TABLE, AF.NAME, account_name)
    ct = _link(CTF.TABLE, CTF.NAME, r["content_type"])
    mats = draft.select_materials(r.get("material_needs") or [], acc[0] if acc else "", clothes=r.get("clothes", ""))
    fields = {
        NF.CODE: f"{SIM}-{account_name}-{r['playbook_id']}",
        NF.TITLE: f"[闭环模拟] {r['title']}",
        NF.PLAYBOOK: r["playbook_id"],
        NF.DRAFT: r["draft_text"],
        NF.STATUS: NS.PUBLISHED,                                   # 模拟人已发布(仅模拟)
        NF.PUBLISH_LINK: {"link": f"http://_sim/{account_name}", "text": f"模拟发布-{account_name}"},  # url 字段
        NF.PUBLISHED_AT: int(datetime.now().timestamp() * 1000),
        NF.LIKED: liked, NF.COLLECTED: collected,                  # 模拟回流采集结果
    }
    if acc:
        fields[NF.ACCOUNT] = acc
    if ct:
        fields[NF.CONTENT_TYPE] = ct
    if mats:
        fields[NF.LINKED_MATERIALS] = mats
    rid = feishu_io.create_record(NF.TABLE, fields)
    return {"account": account_name, "playbook": r["playbook_id"], "note_id": rid,
            "few_shot": r["skill_loaded"], "素材数": len(mats), "点赞": liked}


def cleanup() -> int:
    """删除本脚本建的 _SIM 已发 note(只删 _SIM 前缀)。"""
    n = 0
    for rec in feishu_io.list_records(NF.TABLE):
        if bitable.text(rec["fields"].get(NF.CODE)).startswith(SIM):
            feishu_io.delete_record(NF.TABLE, rec["record_id"]); n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留 _SIM 记录(默认跑完清场)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE}")
    cleanup()  # 先清残留 _SIM
    all_accs = accounts.load_all("巧荷")
    rounds = []
    i = 0
    for name in sorted(all_accs):                       # 全账号 × 全模式(一号多模式完整覆盖,不只第一套)
        for pb in all_accs[name].playbooks():
            ct = pb.get("content_type") or pb.get("id") or ""
            rounds.append(sim_one(name, content_type=ct, liked=100 + i * 30, collected=20 + i * 10))
            i += 1
    for x in rounds:
        ok = x["few_shot"] and x["素材数"] >= 1
        print(f"  {'✓' if ok else '✗'} {x['account']}｜{x['playbook']}: few-shot={x['few_shot']} "
              f"选素材={x['素材数']}条 →模拟已发(点赞{x['点赞']}) note={x['note_id']}")
    # 复盘:按方法论聚合本轮 _SIM 已发 note 的效果(哪套方法论有效)
    fields = [rec["fields"] for rec in feishu_io.list_records(NF.TABLE)
              if bitable.text(rec["fields"].get(NF.CODE)).startswith(SIM)]
    agg = metrics.aggregate_by_playbook(fields)
    print("按方法论复盘:", json.dumps({k: {"条数": v["条数"], "均赞": v["均赞"]} for k, v in agg.items()},
                                  ensure_ascii=False))
    closed = all(x["few_shot"] and x["素材数"] >= 1 and x["playbook"] in agg for x in rounds)
    print(f"{'✅ 每个账号×模式都闭环' if closed else '❌ 有账号未闭环'}({len(rounds)} 号,{len(agg)} 套方法论)")
    if not a.keep:
        print(f"清场:删 _SIM {cleanup()} 条")
    return 0 if closed else 1


if __name__ == "__main__":
    raise SystemExit(main())
