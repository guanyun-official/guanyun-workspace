#!/usr/bin/env python3
"""每日排产提议(解决'每个号每天发什么没管理清楚')。

按 launch 账号回答"今天发哪件衣服":该号还没发过的 SKU × 素材就绪度,给排序提议。
只读(不写表、不建笔记),提议交人/agent 拍板后再建笔记。呼应'系统主动提议排产,非被动处理已有笔记'。

用法: python3 scripts/plan_day.py            # 全 launch 账号提议
      python3 scripts/plan_day.py --account 科普号
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import feishu_io  # noqa: E402

USED_STATES = {"已发", "待发布", "已批准", "草稿待发", "待出文案"}  # 已在该号排上/发过=不重复提议


def _txt(v) -> str:
    if isinstance(v, list):
        return ",".join(x.get("text", "") for x in v if isinstance(x, dict))
    return str(v or "")


def propose(only_account: str | None = None) -> dict:
    accounts = [a["fields"] for a in feishu_io.list_records("账号表")
                if a["fields"].get("上线状态") == "launch先上"]
    clothes = feishu_io.list_records("衣服总表")
    notes = [n["fields"] for n in feishu_io.list_records("笔记表")]

    # 素材就绪:SKU→已拍素材数(素材表 拍摄状态=已拍 且 关联衣服=SKU)
    ready: dict[str, int] = {}
    for m in feishu_io.list_records("素材表"):
        mf = m["fields"]
        if mf.get("拍摄状态") == "已拍":
            for sku in _txt(mf.get("关联衣服")).split(","):
                if sku.strip():
                    ready[sku.strip()] = ready.get(sku.strip(), 0) + 1

    out: dict[str, list] = {}
    for acc in accounts:
        name = _txt(acc.get("账号名"))
        if only_account and name != only_account:
            continue
        # 该号已排/已发过的衣服
        used = {_txt(n.get("关联衣服")) for n in notes
                if _txt(n.get("账号(自动)")) == name and n.get("状态") in USED_STATES}
        used = {u for u in used if u}
        cands = []
        for c in clothes:
            cf = c["fields"]
            code = _txt(cf.get("衣服编号"))
            style = _txt(cf.get("款式名称")) or code
            if not code or code in used:
                continue
            n_ready = ready.get(code, 0)
            cands.append({"sku": code, "款式": style, "素材就绪": n_ready,
                          "状态": "素材齐可发" if n_ready > 0 else "需先拍素材"})
        # 素材齐的排前面
        cands.sort(key=lambda x: -x["素材就绪"])
        out[name] = cands
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=None)
    a = ap.parse_args()
    plan = propose(a.account)
    for acc, cands in plan.items():
        print(f"\n📋 {acc} — 今天可发({len(cands)}件候选):")
        if not cands:
            print("  (该号所有 SKU 都已排过,可复盘或等新衣服入库)")
        for c in cands[:5]:
            mark = "✅" if c["素材就绪"] else "📸"
            print(f"  {mark} {c['款式']}({c['sku']}) — {c['状态']}"
                  + (f",素材{c['素材就绪']}条" if c["素材就绪"] else ",要先拍"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
