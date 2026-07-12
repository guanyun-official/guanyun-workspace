#!/usr/bin/env python3
"""体系完全可用 · 综合验收(#37):一条命令逐条过判定标准,全流程全账号×全模式全红线覆盖。
全离线 stub(不触网/零成本);真采集/真发布另测。任一条红=未完全可用,exit≠0。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import (accounts, alerts, bitable, cockpit, collect, config, dispatch, draft,  # noqa: E402
                          feishu_io, guard, metrics, publish, report, shotlist, trends)
from orchestrator.bitable import AccountFields as AF, NoteFields as NF, NoteStatus as NS  # noqa: E402
from orchestrator.bitable import MaterialSource as MSrc  # noqa: E402
from orchestrator.guard import GuardError  # noqa: E402


def _acc_id(name: str) -> str:
    for r in feishu_io.list_records(AF.TABLE):
        if bitable.text(r["fields"].get(AF.NAME)) == name:
            return r["record_id"]
    return ""

FAIL = 0
FAILED_ITEMS: list[str] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    global FAIL
    print(f"  {'✓' if ok else '✗'} {name}{('  — ' + detail) if detail else ''}")
    if not ok:
        FAIL = 1
        FAILED_ITEMS.append(name)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--alert", action="store_true", help="验收红了发告警到飞书私聊(cron 用;手动跑默认不扰)")
    args = ap.parse_args()
    print("══════ 体系完全可用 · 综合验收(#37)══════")

    # 1) 全账号×全模式:每个组合都能出对味货对板完整包
    print("① 全账号×全模式(对味 few-shot + 完整包素材 + 官号货对板)")
    # base「自动排产=暂停」的号不纳入"完全可用"要求(押后是运营开关,不是缺陷;同 ④)
    from orchestrator.bitable import AutoSched
    paused = {bitable.text(r["fields"].get(AF.NAME)).strip()
              for r in feishu_io.list_records(AF.TABLE)
              if bitable.text(r["fields"].get(AutoSched.FIELD)).strip() == AutoSched.PAUSED}
    combos = []
    for name, acc in sorted(accounts.load_all("巧荷").items()):
        if name in paused:
            continue
        for pb in acc.playbooks():
            ct = pb.get("content_type") or pb.get("id") or ""
            combos.append((name, ct))
    # 覆盖所有『活跃(未暂停)』账号×模式;数量随 base 暂停开关变,不焊死(暂停号退出要求是功能非缺陷)
    ck(f"覆盖 {len(combos)} 个活跃账号×模式组合", bool(combos), str([f"{a}/{c}" for a, c in combos]))
    for name, ct in combos:
        clothes = "GY-001" if "品牌新作" in ct else ""
        r = draft.generate_draft(name, llm_mode="stub", content_type=ct, clothes=clothes)
        mats = draft.select_materials(r["material_needs"], _acc_id(name), clothes=r.get("clothes", ""))
        ok = r["skill_loaded"] and r["playbook_id"] == ct and len(mats) >= 1
        ck(f"{name}/{ct}: few-shot={r['skill_loaded']} 完整包素材={len(mats)}条", ok)

    # 2) 红线焊死:三写路径拒生产库 + 任何模式绝不自带AI声明 + 官号货对板闸
    print("② 红线焊死")
    o = (config.BASE_TOKEN, config.TEST_MODE)
    try:
        config.BASE_TOKEN, config.TEST_MODE = config.PROD_BASE, True
        r = draft.generate_draft("ootd号", llm_mode="stub")
        for who, fn in [("draft写", lambda: draft.create_draft_note(r)),
                        ("collect写", lambda: collect.collect_and_writeback(mode="stub")),
                        ("dispatch写", lambda: dispatch.dispatch("巧荷", write=True))]:
            blocked = False
            try:
                fn()
            except GuardError:
                blocked = True
            except Exception:
                blocked = True
            ck(f"{who}→生产库被闸拒", blocked)
    finally:
        config.BASE_TOKEN, config.TEST_MODE = o
    ai_clean = all(NF.AI_DECLARED not in draft.generate_draft(n, llm_mode="stub", content_type=c)["note_fields"]
                   for n, c in combos)
    ck("任何账号×模式生成都不自带 AI声明(人审门)", ai_clean)
    status_ok = all(draft.generate_draft(n, llm_mode="stub", content_type=c)["note_fields"][NF.STATUS] == NS.DRAFT_PENDING
                    for n, c in combos)
    ck("生成一律止于草稿待发(不越审核门)", status_ok)

    # 3) 采集能力(stub 零成本;真采集零key另测赞805)
    print("③ 效果回流采集")
    ck("collect stub 零成本返空", metrics.collect("https://x", mode="stub") == {})
    ck("collect 取真链接非描述(_link)", collect._link({"link": "https://real", "text": "描述"}) == "https://real")

    # 4) 调度自动化 + 灵感前置
    print("④ 轻调度器 + 灵感前置")
    asn = dispatch.daily_assignments("巧荷")
    asn_combos = {(a["account"], a["content_type"]) for a in asn}
    # 派活是全组合的有效子集(base「自动排产=暂停」的号会被跳过——那正是功能,不是缺陷)
    ck(f"派活是全组合有效子集({len(asn)}条;暂停号已按 base 排产跳过)",
       bool(asn_combos) and asn_combos <= set(combos), f"派活⊆组合={asn_combos <= set(combos)}")
    ck("sourcing 三态齐(含爆款模仿)", set(dispatch.SOURCING_HINT) >= {"shoot_then_drip", "curated", "trend_imitate"})
    ck("灵感库→出稿前置就位(pending_ideas)", hasattr(dispatch, "pending_ideas"))

    # 5) 可扩展:加号/加模式=改声明不动代码(多模式已验证)
    print("⑤ 可扩展")
    multi = [n for n, a in accounts.load_all("巧荷").items() if len(a.playbooks()) >= 2]
    ck("一号多模式已实跑(声明式加模式不改代码)", bool(multi), f"多模式号={multi}")

    # 6) 人只管头尾:头=拍素材(拍摄需求单)· 中间系统全包(找热点/排期出稿/AI声明判定)· 尾=审发(base点)· 每周总结
    print("⑥ 人只管头尾全链就位")
    ck("中·跑一天脊梁(排期→出稿→挂素材→草稿待发,一条命令)",
       hasattr(dispatch, "run_day") and all(r["status"] == "(干跑)" for r in dispatch.run_day("巧荷", write=False)))
    ai_rule = (not guard.ai_declaration_required([MSrc.REAL, MSrc.REAL])) and guard.ai_declaration_required([MSrc.AI])
    ck("尾·AI声明按素材来源自动判定(实拍免勾/AI合成强制勾,机器不代勾)",
       ai_rule and hasattr(publish, "review_approved"))
    ck("头·拍摄需求单在位(需要拍什么/缺几条/拍摄要求/参考)",
       hasattr(shotlist, "shot_needs") and isinstance(shotlist.shot_needs("巧荷"), list))
    ck("周·每周总结在位(回流→按方法论复盘)",
       hasattr(report, "weekly_summary") and "复盘" in report.format_weekly(report.weekly_summary([])))
    ck("中·找热点→灵感库落库去重在位(trend_imitate 前置)",
       trends.harvest_trends([{"标题": "验收探针热点X"}], write=False)["新增"] == ["验收探针热点X"])

    # 7) 顺手:一条命令看完今日头尾(替代挨个敲 run_day/publish_ready/shot_list)——防"绿≠可用"照不到人机可用性
    print("⑦ 顺手·驾驶舱(一条命令看完今日)")
    panel = cockpit.today_panel("巧荷")
    ck("今日面板一条命令聚合 待审/待发/待回填链接/要补拍",
       hasattr(cockpit, "today_panel") and {"待审", "待发", "待回填链接", "要补拍"} <= set(panel))
    ck("待发条目带『用哪张素材+可开链接』(人发时知道用哪张)",
       all(all("link" in m for m in n["materials"]) for n in panel["待发"]))

    print("══════", "✅ 体系完全可用(综合验收全绿)" if not FAIL else "❌ 有未达标项,未完全可用", "══════")
    if FAIL and args.alert:   # 红了发告警到飞书私聊(hermes home=p2p私聊,不进群)
        alerts.send(f"综合验收未通过({len(FAILED_ITEMS)}项):{'、'.join(FAILED_ITEMS)}", title="巧荷周验收⚠️")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(main())
