#!/usr/bin/env python3
"""通用账号策略解释器(泛化引擎:读每个账号声明的模式→执行,加新模式=写 strategy 文件零代码)。

架构三层:能力=skill(怎么做) / 模式=strategy data(每号怎么运营,声明式) / 引擎=本文件(读声明→执行)。
一个账号的"模式"全在 brands/{brand}/accounts/{账号}.strategy.json,本解释器不硬编码任何账号特定逻辑。

执行:按各号 strategy 的 cadence/material_needs 算 缓发+余量+催拍。cadence.pattern=manual/未上线→跳过(声明决定,非代码)。
用法: python3 scripts/planner.py [--account 科普号] [--brand 观云]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import bitable, config, feishu_io  # noqa: E402

USED_STATES = {"已发", "待发布", "已批准", "草稿待发", "待出文案"}

_txt = bitable.text  # 候选A:统一字段取文本


def load_strategies(brand: str = "观云") -> dict:
    """读所有账号策略声明。加账号/改模式=改这些文件,不动代码。"""
    d = {}
    for p in (config.WORKSPACE / "brands" / brand / "accounts").glob("*.strategy.json"):
        s = json.loads(p.read_text(encoding="utf-8"))
        d[s["account"]] = s
    return d


def _all_needed_types(strategy: dict) -> set:
    out = set()
    for types in (strategy.get("material_needs") or {}).values():
        out.update(types)
    return out


def plan(only: str | None = None, brand: str = "观云") -> dict:
    strategies = load_strategies(brand)
    clothes = {_txt(c["fields"].get("衣服编号")): _txt(c["fields"].get("款式名称"))
               for c in feishu_io.list_records("衣服总表") if _txt(c["fields"].get("衣服编号"))}
    notes = [n["fields"] for n in feishu_io.list_records("笔记表")]
    mats = [m["fields"] for m in feishu_io.list_records("素材表")]

    sku_types: dict[str, set] = {}
    for m in mats:
        if m.get("拍摄状态") == "已拍":
            for sku in _txt(m.get("关联衣服")).split(","):
                if sku.strip():
                    sku_types.setdefault(sku.strip(), set()).add(str(m.get("类型")))

    out: dict[str, dict] = {}
    for name, s in strategies.items():
        if only and name != only:
            continue
        cadence = s.get("cadence", {})
        active = cadence.get("posts_per_day", 0) > 0 or s.get("posts_per_week", 0) > 0
        if not active or s.get("launched") is False:
            out[name] = {"模式": s.get("mode"), "自动": False,
                         "说明": f"{s.get('notes','')}(声明为 {cadence.get('pattern','manual')},引擎不自动排)"}
            continue
        need_types = _all_needed_types(s)
        used = {_txt(n.get("关联衣服")) for n in notes
                if _txt(n.get("账号(自动)")) == name and n.get("状态") in USED_STATES}
        ready, shoot = [], []
        for sku, style in clothes.items():
            if sku in used:
                continue
            have = sku_types.get(sku, set())
            if need_types and (have & need_types):
                ready.append({"sku": sku, "款式": style, "有素材": sorted(have & need_types)})
            else:
                shoot.append({"sku": sku, "款式": style, "要拍": sorted(need_types - have) or ["(无需求配置)"]})
        alert = s.get("runway_alert_days", 3)
        out[name] = {
            "模式": s.get("mode"), "自动": True, "自主": s.get("autonomy"),
            "节奏": f"{cadence.get('posts_per_day') or s.get('posts_per_week')}/{'天' if cadence.get('posts_per_day') else '周'}",
            "余量天数": len(ready), "素材见底": len(ready) < alert,
            "今日缓发": ready[0] if ready else None, "就绪队列": ready, "拍摄需求": shoot,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default=None)
    ap.add_argument("--brand", default="观云")
    a = ap.parse_args()
    p = plan(a.account, a.brand)
    for name, d in p.items():
        if not d.get("自动"):
            print(f"\n━━ {name} ━━  [{d['模式']}] 引擎不自动 — {d['说明']}")
            continue
        print(f"\n━━ {name} ━━  [{d['模式']}] {d['节奏']} 自主={d['自主']}  余量{d['余量天数']}天"
              + ("  ⚠️素材见底" if d["素材见底"] else ""))
        if d["今日缓发"]:
            t = d["今日缓发"]
            print(f"  📮 今日发:{t['款式']}({t['sku']}) 用素材{t['有素材']}")
        else:
            print("  📮 队列空,今日无可发")
        if d["拍摄需求"]:
            print(f"  📸 拍摄需求:")
            for x in d["拍摄需求"][:4]:
                print(f"     {x['款式']}({x['sku']}) 要拍:{'/'.join(x['要拍'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
