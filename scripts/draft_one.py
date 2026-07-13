"""薄执行器 CLI:给一个号即时产一条待审草稿(第一目标 A walking skeleton)。

  python3 -m scripts.draft_one --account ootd号                     # 干跑(stub):打印草稿+笔记字段,不写库
  python3 -m scripts.draft_one --account ootd号 --write             # 过红线闸写测试库笔记表(状态=草稿待发)
  python3 -m scripts.draft_one --account ootd号 --llm real --write  # 真生成(预算帽)后写库
  --title-seed "OOTD｜寒玉疏枝"                                      # 给标题线索(可选)

红线:发布与 AI 声明是人手;本执行器只推到「草稿待发」,绝不代勾 AI 声明、绝不自动发布。
--write 只在测试库(TEST_MODE)——写库闸拒生产 Base。
"""
from __future__ import annotations

import argparse
import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/draft_one.py 也能跑(不止 -m)

from orchestrator import config, draft


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", required=True)
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--llm", choices=["stub", "real"], default="stub")
    ap.add_argument("--title-seed", default="")
    ap.add_argument("--source-text", default="",
                    help="蹭爆款时传对标源完整正文(灵感库『文案』)——防搬运门比对它,逐字搬即拒")
    ap.add_argument("--clothes", default="", help="绑定知识库真实衣服编号(如 GY-001);官号品牌新作应绑,防编造")
    ap.add_argument("--content-type", default="", help="一号多模式时选哪个模式(内容类型名);空=第一套")
    ap.add_argument("--write", action="store_true", help="过红线闸写测试库笔记表(默认干跑不写)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} account={a.account} llm={a.llm} write={a.write}")
    if a.llm == "real":                       # 真出稿花钱:先查月度预算,超阈当场警示(不阻断,红线是发布不是成本)
        from orchestrator import cost
        warn = cost.budget_alert()
        if warn:
            print(f"⚠️ {warn}(本条仍出;如需收口降 GY_BUDGET_MONTHLY_CNY 或先停真出稿)")
    r = draft.generate_draft(a.account, a.brand, a.llm, a.title_seed, clothes=a.clothes,
                             content_type=a.content_type, source_text=a.source_text)
    print(f"gen_skill={r['gen_skill']} few-shot载入={r['skill_loaded']} 绑定衣服={r['clothes'] or '无'}"
          f"({'真实事实✓' if r['clothes_grounded'] else '未绑·禁编造'}) "
          f"playbook={r['playbook_id']} 内容类型={r['content_type']} 成本_元={r['cost']}")
    print("--- 标题 ---")
    print(r["title"])
    print("--- 文案草稿 ---")
    print(r["draft_text"])
    print("--- 笔记字段(将写入 笔记表)---")
    print(json.dumps(r["note_fields"], ensure_ascii=False, indent=1))
    if not a.write:
        print("(干跑:未写库。加 --write 才过红线闸落测试库笔记表)")
        return 0
    rid = draft.create_draft_note(r)
    from orchestrator import bitable, dispatch, feishu_io
    from orchestrator.bitable import InspirationFields as IF
    feishu_io.log_run(summary=f"出稿 {a.account}/{r['content_type']}", action="出稿",
                      skill=r["gen_skill"], note_ref=rid, table="笔记表", cost=r["cost"])   # 记运行日志(复盘/成本追踪据此)
    print(f"✅ 已写测试库笔记表 record_id={rid}(状态=草稿待发,待人审;发布/AI声明人手)")

    # **闭合爆款模仿环**(2026-07-14 对齐审查:`mark_idea_converted` 生产零调用 = 这个环从来没闭合过):
    # 这条稿是从某条灵感来的(--title-seed 就是灵感标题,dispatch 的『爆款模仿待办』就是这么派的),
    # 出完稿必须回填灵感库的『转化为笔记』——否则灵感永远是"未转化",**同一条爆款会被反复派活**。
    if a.title_seed:
        for row in feishu_io.list_records(IF.TABLE):
            if bitable.text(row["fields"].get(IF.TITLE)).strip() == a.title_seed.strip():
                dispatch.mark_idea_converted(row["record_id"], rid)
                print(f"🔗 已回填灵感库『转化为笔记』:「{a.title_seed}」→ {rid}(闭合爆款模仿环,不再重复派活)")
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
