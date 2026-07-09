#!/usr/bin/env python3
"""通用账号策略解释器(泛化引擎:读每个账号声明的模式→执行,加新模式=写 strategy 文件零代码)。

架构三层:能力=skill(怎么做) / 模式=strategy data(每号怎么运营,声明式) / 引擎=本文件(读声明→执行)。
一个账号的"模式"全在 brands/{brand}/accounts/{账号}.strategy.json,本解释器不硬编码任何账号特定逻辑。

执行:按各号 strategy 的 cadence/material_needs 算 缓发+余量+催拍。cadence.pattern=manual/未上线→跳过(声明决定,非代码)。
用法: python3 scripts/planner.py [--account 科普号] [--brand 观云]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import accounts, bitable, feishu_io, metrics  # noqa: E402
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


def _pb_views(account: str, pbs: list, used_clips: set) -> list[dict]:
    """每套方法论视图的 选入/可发 子素材(算一次,供余量展示 + 今日发挑选)。
    可发 = 视图里选入、且尚未被本号笔记用掉的子素材(SKU 无关:挂不挂 SKU 都算)。"""
    out = []
    for pb in pbs:
        selects = mv.view_selects(account, pb.get("view") or pb.get("id"), root=mv.ASSET_ROOT)
        out.append({"pb": pb, "selects": selects,
                    "avail": [s for s in selects if s.get("clip_id") not in used_clips]})
    return out


def _pick_today(pb_views: list, ready: list, editable: list) -> dict | None:
    """统一「今日发」(G9):**视图为发布主轴**——最高权重、且视图有可发子素材的 playbook 先出片;
    视图皆空则回退 SKU 轴(现成成片→AI剪)。SKU 轴自此退为补料/拍摄指导,不再是并行的第二个"今日发"。"""
    for v in sorted(pb_views, key=lambda x: -(x["pb"].get("weight") or 0)):
        if v["avail"]:
            c = v["avail"][0]
            return {"来源": "视图", "方法论": v["pb"].get("id"),
                    "clip": {k: c.get(k) for k in ("clip_id", "material", "span")}}
    if ready:
        candidate = ready[0]
        have = set(candidate.get("有素材") or [])
        matching = [
            v["pb"] for v in pb_views
            if have & set(v["pb"].get("material_needs") or [])
        ]
        fallback_pb = max(matching, key=lambda pb: pb.get("weight") or 0, default={})
        return {"来源": "现成成片", "方法论": fallback_pb.get("id"), **candidate}
    if editable:
        fallback_pb = max((v["pb"] for v in pb_views), key=lambda pb: pb.get("weight") or 0, default={})
        return {"来源": "AI剪", "方法论": fallback_pb.get("id"), **editable[0]}
    return None


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
        acct_notes = [n for n in notes if _txt(n.get(NF.ACCOUNT)) == name]
        note_codes = {_txt(n.get(NF.CODE)) for n in acct_notes}
        used_clips = {u.get("clip_id") for u in ledger if u.get("note") in note_codes}  # 本号已用掉的 clip
        pbv = _pb_views(name, pbs, used_clips)  # 每套方法论视图选入/可发(算一次)
        out[name] = {
            "模式": s.get("mode"), "自动": True, "自主": s.get("autonomy"),
            "方法论": [{"id": pb.get("id"), "内容类型": pb.get("content_type") or pb.get("id"),
                       "权重": pb.get("weight"), "需素材": pb.get("material_needs", [])}
                       for pb in pbs],
            "视图余量": [{"id": v["pb"].get("id"), "已选": len(v["selects"]), "可发": len(v["avail"]),
                         "见底": len(v["avail"]) < alert} for v in pbv],  # G6
            "节奏": f"{cadence.get('posts_per_day') or s.get('posts_per_week')}/{'天' if cadence.get('posts_per_day') else '周'}",
            "余量天数": runway, "素材见底": runway < alert,
            "今日发": _pick_today(pbv, ready, editable),   # G9:统一发布主轴(视图优先→SKU 回退)
            "方法论表现": metrics.aggregate_by_playbook(acct_notes),  # G7 反馈:哪套方法论均赞高(闭环学习信号)
            "就绪队列": ready, "待剪队列": editable, "拍摄需求": shoot,  # SKU 轴=补料/拍摄指导
        }
    return out


def _plan_code(day: date, account: str, playbook: str, today: dict) -> str:
    """排产 Note 的稳定业务键。同日同账号同方法论同候选重跑得到同一键。"""
    entity = today.get("sku") or (today.get("clip") or {}).get("clip_id") or today.get("来源", "")
    digest = hashlib.sha1(f"{account}\x1f{playbook}\x1f{entity}".encode("utf-8")).hexdigest()[:10]
    return f"PLAN-{day:%Y%m%d}-{digest}"


def materialize_day(only: str | None = None, brand: str = "观云", day: date | None = None) -> dict:
    """把 planner 的「今日发」幂等物化为笔记表 Note。

    只物化已有可发布资产的「视图 / 现成成片」候选；「AI剪」仍缺媒体加工状态与动作，
    显式跳过而不是把原料伪装成成片推进发布链。
    """
    target_day = day or date.today()
    planned = plan(only=only, brand=brand)
    notes = feishu_io.list_records("笔记表")
    existing_codes = {_txt(r["fields"].get(NF.CODE)) for r in notes}
    content_types = {
        _txt(r["fields"].get("内容类型名")): r["record_id"]
        for r in feishu_io.list_records("内容类型表")
        if _txt(r["fields"].get("内容类型名"))
    }
    clothes = {
        _txt(r["fields"].get(CF.CODE)): r["record_id"]
        for r in feishu_io.list_records("衣服总表")
        if _txt(r["fields"].get(CF.CODE))
    }
    materials = feishu_io.list_records("素材表")
    material_by_code = {
        _txt(r["fields"].get(MF.CODE)): r["record_id"]
        for r in materials if _txt(r["fields"].get(MF.CODE))
    }

    summary = {"created": 0, "existing": 0, "skipped": [], "errors": [], "record_ids": []}
    for account, account_plan in planned.items():
        today = account_plan.get("今日发")
        if not account_plan.get("自动") or not today:
            summary["skipped"].append({"account": account, "reason": "inactive_or_no_candidate"})
            continue
        if today.get("来源") == "AI剪":
            summary["skipped"].append({"account": account, "reason": "media_processing_not_wired"})
            continue

        playbook = today.get("方法论") or ""
        pb = next((x for x in account_plan.get("方法论", []) if x.get("id") == playbook), {})
        content_type = pb.get("内容类型") or playbook
        content_type_id = content_types.get(content_type)
        if not content_type_id:
            summary["errors"].append(f"{account}: 内容类型「{content_type}」未在内容类型表登记")
            continue

        code = _plan_code(target_day, account, playbook, today)
        if code in existing_codes:
            summary["existing"] += 1
            continue

        fields = {
            NF.CODE: code,
            NF.TITLE: f"{account}·{content_type}·{target_day:%m-%d}",
            NF.STATUS: NS.NEED_COPY,
            NF.PLANNED_AT: int(datetime.combine(target_day, time(9)).timestamp() * 1000),
            NF.CONTENT_TYPE: [content_type_id],
            NF.PLAYBOOK: playbook,
        }
        if today.get("来源") == "视图":
            clip = today.get("clip") or {}
            if clip.get("clip_id"):
                fields[NF.CLIPS] = clip["clip_id"]
            material_id = material_by_code.get(clip.get("material"))
            if material_id:
                fields[NF.LINKED_MATERIALS] = [material_id]
        else:
            sku = today.get("sku")
            if sku in clothes:
                fields[NF.LINKED_CLOTHES] = [clothes[sku]]
            wanted_types = set(today.get("有素材") or [])
            material_ids = [
                r["record_id"] for r in materials
                if sku in {x.strip() for x in _txt(r["fields"].get(MF.LINKED_CLOTHES)).split(",")}
                and (not wanted_types or _txt(r["fields"].get(MF.TYPE)) in wanted_types)
            ]
            if material_ids:
                fields[NF.LINKED_MATERIALS] = material_ids

        rid = feishu_io.create_record("笔记表", fields)
        existing_codes.add(code)
        summary["created"] += 1
        summary["record_ids"].append(rid)
    return summary


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
        if d.get("方法论表现"):
            best = sorted(d["方法论表现"].items(), key=lambda kv: -kv[1].get("均赞", 0))
            print("  📈 方法论表现(均赞):" + " / ".join(f"{pb}={v['均赞']}(n={v['条数']})" for pb, v in best))
        t = d["今日发"]
        if not t:
            print("  📮 今日无可发(视图空 + SKU 无成片/原料)")
        elif t["来源"] == "视图":
            print(f"  📮 今日发[视图·{t['方法论']}]:子素材 {t['clip']['material']} [{t['clip']['span']}]")
        elif t["来源"] == "现成成片":
            print(f"  📮 今日发[现成成片]:{t['款式']}({t['sku']}) 用 {t['有素材']}")
        else:  # AI剪
            print(f"  ✂️ 今日发[AI剪]:{t['款式']}({t['sku']}) 原料{t['原料']}→剪成{t['剪成']}")
        if d["待剪队列"]:
            print(f"  ✂️ 补料·可剪({len(d['待剪队列'])}):{'、'.join(x['sku'] for x in d['待剪队列'][:5])}(有原料,交剪辑skill)")
        if d["拍摄需求"]:
            print(f"  📸 补料·拍摄需求({len(d['拍摄需求'])},无任何素材才催拍):")
            for x in d["拍摄需求"][:4]:
                print(f"     {x['款式']}({x['sku']}) 要拍:{'/'.join(x['要拍'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
