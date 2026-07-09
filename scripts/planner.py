#!/usr/bin/env python3
"""通用账号策略解释器(泛化引擎:读每个账号声明的模式→执行,加新模式=写 strategy 文件零代码)。

架构三层:能力=skill(怎么做) / 模式=strategy data(每号怎么运营,声明式) / 引擎=本文件(读声明→执行)。
一个账号的"模式"全在 brands/{brand}/accounts/{账号}.strategy.json,本解释器不硬编码任何账号特定逻辑。

执行:按各号 strategy 的 cadence/material_needs 算 缓发+余量+催拍。cadence.pattern=manual/未上线→跳过(声明决定,非代码)。
用法: python3 scripts/planner.py [--account 科普号] [--brand 观云]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import accounts, bitable, feishu_io  # noqa: E402
from lib import material_view as mv  # noqa: E402
from orchestrator.bitable import ClothesFields as CF  # noqa: E402
from orchestrator.bitable import MaterialFields as MF  # noqa: E402
from orchestrator.bitable import MaterialStatus as MS  # noqa: E402
from orchestrator.bitable import NoteFields as NF  # noqa: E402
from orchestrator.bitable import NoteStatus as NS  # noqa: E402

# 已占用该 SKU 的在制状态(有此状态的笔记 → planner 不再重复排该 SKU)
USED_STATES = {NS.NEED_COPY, NS.DRAFT_PENDING, NS.APPROVED, NS.TO_PUBLISH, NS.PUBLISHED}

_txt = bitable.text  # 候选A:统一字段取文本


def load_strategies(brand: str = "观云") -> dict:
    """读所有账号策略(候选C:统一 Account 定义的 frontmatter)。加账号/改模式=改 {号}.md,不动代码。"""
    from orchestrator import accounts
    return {name: acc.strategy for name, acc in accounts.load_all(brand).items()}


def _all_needed_types(strategy: dict) -> set:
    """该号所有方法论(playbook)合起来需要的素材切面类型。经 playbooks 收口——
    加一套方法论=写声明即改排产,零代码(G4)。"""
    out = set()
    for pb in accounts.playbooks_of(strategy):
        out.update(pb.get("material_needs") or [])
    return out


def _view_readiness(account: str, pbs: list, used_clips: set, alert: int) -> list[dict]:
    """G6:每套方法论的视图(bin)可发余量——SKU 无关(视图里的子素材挂不挂 SKU 都算)。
    可发 = 视图里选入、且尚未被本号笔记用掉的子素材数。这条轴让不挂 SKU 的素材也进得了排产。"""
    out = []
    for pb in pbs:
        selects = mv.view_selects(account, pb.get("id"), root=mv.ASSET_ROOT)
        avail = [s for s in selects if s.get("clip_id") not in used_clips]
        out.append({"id": pb.get("id"), "已选": len(selects), "可发": len(avail),
                    "见底": len(avail) < alert})
    return out


def plan(only: str | None = None, brand: str = "观云") -> dict:
    strategies = load_strategies(brand)
    clothes = {_txt(c["fields"].get(CF.CODE)): _txt(c["fields"].get(CF.NAME))
               for c in feishu_io.list_records("衣服总表") if _txt(c["fields"].get(CF.CODE))}
    notes = [n["fields"] for n in feishu_io.list_records("笔记表")]
    mats = [m["fields"] for m in feishu_io.list_records("素材表")]

    sku_types: dict[str, set] = {}
    for m in mats:
        if m.get(MF.SHOT_STATUS) == MS.SHOT:
            for sku in _txt(m.get(MF.LINKED_CLOTHES)).split(","):
                if sku.strip():
                    sku_types.setdefault(sku.strip(), set()).add(str(m.get(MF.TYPE)))

    ledger = mv.all_usage(root=mv.ASSET_ROOT)  # G6:使用账本(算各号视图已用掉哪些 clip)
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
        used = {_txt(n.get(NF.LINKED_CLOTHES)) for n in notes
                if _txt(n.get(NF.ACCOUNT)) == name and n.get(NF.STATUS) in USED_STATES}
        # 三档(呼应用户素材洞察:原始素材池→剪辑skill剪出每号成片):
        #   ready=有该号所需成片类型,直接发 / editable=有原始素材,AI按该号风格剪出所需(不催拍) / shoot=无任何素材,催拍
        ready, editable, shoot = [], [], []
        for sku, style in clothes.items():
            if sku in used:
                continue
            have = sku_types.get(sku, set())
            if need_types and (have & need_types):
                ready.append({"sku": sku, "款式": style, "有素材": sorted(have & need_types)})
            elif have:  # 有原料但非目标成片→交剪辑skill,不催拍
                editable.append({"sku": sku, "款式": style, "原料": sorted(have), "剪成": sorted(need_types)})
            else:       # 无任何素材→催拍
                shoot.append({"sku": sku, "款式": style, "要拍": sorted(need_types) or ["(无需求配置)"]})
        alert = s.get("runway_alert_days", 3)
        runway = len(ready) + len(editable)  # 可发+可剪=真实余量(原料能剪出成片)
        pbs = accounts.playbooks_of(s)  # G4:该号的多套发布方法论(声明式,零代码扩展)
        note_codes = {_txt(n.get(NF.CODE)) for n in notes if _txt(n.get(NF.ACCOUNT)) == name}
        used_clips = {u.get("clip_id") for u in ledger if u.get("note") in note_codes}  # 本号已用掉的 clip
        out[name] = {
            "模式": s.get("mode"), "自动": True, "自主": s.get("autonomy"),
            "方法论": [{"id": pb.get("id"), "权重": pb.get("weight"), "需素材": pb.get("material_needs", [])}
                       for pb in pbs],
            "视图余量": _view_readiness(name, pbs, used_clips, alert),  # G6:每套方法论视图可发余量(SKU 无关)
            "节奏": f"{cadence.get('posts_per_day') or s.get('posts_per_week')}/{'天' if cadence.get('posts_per_day') else '周'}",
            "余量天数": runway, "素材见底": runway < alert,
            "今日缓发": ready[0] if ready else None,
            "今日可剪": editable[0] if not ready and editable else None,  # 无现成成片但有原料→AI剪
            "就绪队列": ready, "待剪队列": editable, "拍摄需求": shoot,
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
        print(f"\n━━ {name} ━━  [{d['模式']}] {d['节奏']} 自主={d['自主']}  余量{d['余量天数']}天(可发+可剪)"
              + ("  ⚠️素材见底" if d["素材见底"] else ""))
        if d.get("方法论"):
            print("  📚 方法论:" + " / ".join(f"{pb['id']}(权重{pb['权重']})" for pb in d["方法论"]))
        if d.get("视图余量"):
            print("  🎞️ 视图可发:" + " / ".join(
                f"{v['id']}={v['可发']}条" + ("⚠️见底" if v["见底"] else "") for v in d["视图余量"]))
        if d["今日缓发"]:
            t = d["今日缓发"]
            print(f"  📮 今日发:{t['款式']}({t['sku']}) 用现成成片{t['有素材']}")
        elif d["今日可剪"]:
            t = d["今日可剪"]
            print(f"  ✂️ 今日剪:{t['款式']}({t['sku']}) 原料{t['原料']}→AI按本号风格剪成{t['剪成']}")
        else:
            print("  📮 队列空,今日无可发")
        if d["待剪队列"]:
            print(f"  ✂️ 可剪队列({len(d['待剪队列'])}):{'、'.join(x['sku'] for x in d['待剪队列'][:5])}(有原料,交剪辑skill)")
        if d["拍摄需求"]:
            print(f"  📸 拍摄需求({len(d['拍摄需求'])},无任何素材才催拍):")
            for x in d["拍摄需求"][:4]:
                print(f"     {x['款式']}({x['sku']}) 要拍:{'/'.join(x['要拍'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
