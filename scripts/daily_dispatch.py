"""轻调度器 CLI(#8):每天派活——列出/落地今天每号每模式该出的活(待出文案),**绝不自动发布**。

  python3 -m scripts.daily_dispatch           # 干跑:打印今天派活清单(不写库)
  python3 -m scripts.daily_dispatch --write    # 过红线闸把活落成『待出文案』占位(已在途去重)

红线:调度器只把活推到「待出文案」;出稿走 draft_one(→草稿待发),发布与 AI 声明永远人手。
"""
from __future__ import annotations

import argparse

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/daily_dispatch.py 也能跑(不止 -m)

from orchestrator import config, dispatch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--write", action="store_true", help="落库为『待出文案』占位(默认干跑只打印)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand}")
    rows = dispatch.dispatch(a.brand, write=a.write)
    if a.write:
        from orchestrator import feishu_io
        n_new = sum(1 for r in rows if not r.get("skipped"))
        feishu_io.log_run(summary=f"派活 {n_new} 条(跳过在途 {len(rows)-n_new})", action="派活", table="笔记表")  # 记运行日志
    # **标题必须说实话**:老版本打的是 `今天派活 {len(rows)} 条` —— 它把"会被跳过的在途活"
    # 也算进"派活"里。真跑时 4 条全在途、一条都不派,它却报"今天派活 4 条"。
    # 干跑的唯一意义就是"告诉我实跑会发生什么",标题一撒谎,整个预览就废了。
    todo = [r for r in rows if not r.get("skipped")]
    skip = [r for r in rows if r.get("skipped")]
    print(f"今天真要派 {len(todo)} 条;{len(skip)} 条跳过(已在途,不重复堆活)")
    for r in todo:
        tag = f"→待出文案 {r.get('note_id')}" if a.write else "(干跑:实跑会派)"
        print(f"  + {r['account']:18} {r['content_type']:12} 技能={r['gen_skill']:22} 素材={r['material_needs']}  {tag}")
        print(f"      素材来源[{r['sourcing']}]:{r['sourcing_hint']}")
    for r in skip:
        print(f"  · {r['account']:18} {r['content_type']:12} 跳过:{r['skipped']}(队列里已有在途稿,先审它)")
    if not todo:
        print("\n📭 今天一条新活都不派 —— **在途的还没审完**。先去 base 把待审的稿处理掉。")
    if not a.write:
        print("(干跑:未写库。加 --write 才真落『待出文案』占位)")
    # 爆款模仿(trend_imitate)原料:灵感库未转化的爆款灵感,提示可借鉴点+出稿承接
    if a.write:
        # **每天自动把缺的爆款正文补回来**(2026-07-14 接线;写这个函数时我自己犯了"把操作做成功能"
        # 的反面 —— 写完只手动跑了一次,机器审当场判它死码。判据还是那句:
        # **以后要不要在没人的时候自动重复发生?** 要 —— 运营完全可能在飞书里手打一条灵感
        # (只有标题+链接),那条的正文就永远是空的。而正文是"只学结构"的**情报本身**,
        # 没有它,所谓"模仿爆款"只是照着一个标题瞎猜。抓取零凭证、几乎免费,每天补一次。)
        from orchestrator import trends
        filled = trends.fill_missing_bodies(write=True)
        if filled["回填"]:
            print(f"\n📥 自动补回 {len(filled['回填'])} 条爆款正文:{filled['回填']}")
        if filled["抓不到"]:
            print(f"⚠️ {len(filled['抓不到'])} 条抓不到正文(仍可出稿,只是少一层情报):{filled['抓不到']}")

    ideas = dispatch.pending_ideas(a.brand)
    if ideas:
        # 2026-07-14 上班撞到:这条待办以前写的是
        #   「trend_imitate 号可据此出稿 … draft_one --account <trend_imitate号> --source-text "<正文全文>"」
        # **两句都是假的**:
        #   ① **没有任何一个号有 trend_imitate 模式**(真查过:4 个号只有 视频/图文唯美OOTD、
        #      素人图文种草、品牌新作展示)。它让人去做一件**没有手能做的事**。
        #   ② --source-text 已经不用手传了(空且给了 --title-seed → 自动去灵感库取正文)。
        # 真相:**爆款模仿不是一个号,是一个选题来源** —— 拿热点当灵感,用**现有某个号+模式**去写。
        # 配给谁,是 agent 该现场判断的(看调性:知性通勤 → 素人种草;唯美意境 → ootd 号)。
        print(f"\n爆款模仿待办({len(ideas)} 条灵感未转化):")
        for it in ideas[:8]:
            has_body = "有正文✓" if it.get("文案") else "无正文"
            print(f"  · {it['标题']}  可借鉴:{it['可借鉴'] or '—'}  [{has_body}]")
        print("  它不是某个专属号的活 —— **看调性配给最合适的号**(知性/通勤/显高 → 素人种草号;"
              "唯美/意境 → ootd 号),用那个号自己的模式去写。")
        print("  出稿:draft_one --account <配给的号> --content-type <该号的模式> --title-seed \"<灵感标题>\" --llm real --write")
        print("  正文会**自动从灵感库取**(当情报学结构);抄原句由防搬运门在出口拦死,抄了会自动回炉重写。")
        print("  出稿后自动回填灵感库『转化为笔记』,不会重复派。")
    # 素材余量催拍(消费账号 md 的 runway_alert_days,曾是哑字段)
    alerts = dispatch.runway_alerts(a.brand)
    if alerts:
        print(f"\n⚠️ 素材催拍({len(alerts)} 号余量不足,快补拍):")
        for al in alerts:
            print(f"  · {al['account']}:可用素材 {al['avail']} 条 ≈ {al['runway_days']} 天 < 阈值 {al['threshold']} 天")
    # 月度成本告警(ADR-0009:BUDGET_MONTHLY_CNY 曾是零消费纸面数字,这里真接上告警)
    from orchestrator import cost
    warn = cost.budget_alert()
    if warn:
        print(f"\n{warn}")
        try:
            from orchestrator import alerts as _al
            _al.send(warn)
        except Exception:  # noqa: BLE001  告警投递失败不阻断
            pass
    print("\n红线:调度器只派活到『待出文案』,绝不出稿即发、绝不代勾 AI 声明——出稿走 draft_one,发布/声明人手。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
