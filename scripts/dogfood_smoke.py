#!/usr/bin/env python3
"""dogfood 冒烟(真库跑,反"mock 假绿"):把系统当运营真跑一遍关键路径,断言**人能看懂的真事**——
不是"mock 同意",是"真飞书数据下账号名非空、link 能解析、去重键成立"。任一条假 → 非0退出。

**为什么存在**:mock 用的是 get_record 形态([{text,record_ids}]),真 search 是 {link_record_ids}(无text)——
mock 比真数据"干净"→ 关联字段读空的 bug 能过每一轮绿门,只有真跑才暴露(实测:今日面板账号全空、派活不去重)。
以后"done"= 真跑过这个,不是 mock 绿。只读,零写入,对测试库跑。

  python3 scripts/dogfood_smoke.py            # 真库跑冒烟,列每步真结果 + 断言
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator import cockpit, collect, config, dispatch  # noqa: E402

FAIL = 0
def ck(name: str, ok: bool, detail: str = "") -> None:
    global FAIL
    print(f"  {'✓' if ok else '✗'} {name}{('  — ' + detail) if detail else ''}")
    if not ok:
        FAIL = 1


def main() -> int:
    print(f"══════ dogfood 冒烟(真库 {config.ENV_NAME})══════")

    # ① 今日面板:link 字段(账号/内容类型)必须解析成真名,不能空(search 形态坑的直接暴露点)
    print("① 今日面板 today_panel(真库)")
    p = cockpit.today_panel("巧荷")
    active = p["待审"] + p["待发"]
    empty_acc = [n["title"] for n in active if not n["account"].strip()]
    ck(f"待审/待发 {len(active)} 条账号名全部非空(link 从 search 解析成功)",
       not empty_acc, f"账号空的: {empty_acc[:5]}" if empty_acc else "")
    bad_quota = [q for q in p["控量"] if not q["account"].strip()]
    ck("控量键都是真账号名(不是空串聚成一坨)", not bad_quota, str(bad_quota[:3]))

    # ①b 运营真正看的是**飞书卡片**(不敲终端):卡片必须按真账号名分组,不能出现空账号表头(那样人没法用)
    print("①b 今日卡片 today_card(运营手机上真看到的)")
    card = cockpit.today_card("巧荷", panel=p)
    heads = [el.get("text", {}).get("content", "") for el in card["elements"]]
    empty_head = [h for h in heads if h.startswith("**") and h.split("\n")[0].strip("* ") in ("", "·")]
    ck("卡片按真账号名分组(无空账号表头,人一眼知道是哪个号)", not empty_head, str(empty_head[:3]))
    ck("卡片有内容(不是空卡)", len(card["elements"]) >= 1)

    # ② 派活去重:in-flight 键必须是 (真账号名, 真模式),否则 daily_assignments 真名永不命中→天天重复派活
    print("② 派活去重 _open_slots(真库)")
    slots = dispatch._open_slots()
    bad_slots = [s for s in slots if not s[0].strip()]
    ck(f"在途去重键 {len(slots)} 个账号名全非空(去重真成立)", not bad_slots, str(bad_slots[:3]))
    asn = dispatch.daily_assignments("巧荷")
    ck(f"今日派活 {len(asn)} 条(daily_assignments 出得来)", bool(asn))

    # ③ 回流可跑:harvestable 不炸 + 冷热分离查询真返(不整拉)
    print("③ 回流采集 harvestable_notes(真库)")
    try:
        h = collect.harvestable_notes()
        ck(f"harvestable_notes 真库跑通({len(h)} 条可回流)", True)
    except Exception as e:  # noqa: BLE001
        ck("harvestable_notes 真库跑通", False, str(e)[:100])

    # ④ 周排期:账号名也走 link 解析,不能空
    print("④ 本周排期 weekly_schedule(真库)")
    try:
        w = cockpit.weekly_schedule("巧荷")
        allnotes = [n for d in w["days"] for n in d["notes"]] + w["逾期"] + w["未排期"]
        empty_w = [n["title"] for n in allnotes if not n["account"].strip()]
        ck(f"排期 {len(allnotes)} 条账号名全非空", not empty_w, f"空的:{empty_w[:5]}" if empty_w else "")
    except Exception as e:  # noqa: BLE001
        ck("weekly_schedule 真库跑通", False, str(e)[:100])

    print("══════", "✅ dogfood 冒烟全过(真库人能看懂的事都成立)" if not FAIL else "❌ 冒烟有假 — 真跑就崩,别信绿门", "══════")
    return FAIL


if __name__ == "__main__":
    raise SystemExit(main())
