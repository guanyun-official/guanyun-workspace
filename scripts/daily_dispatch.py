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
        feishu_io.log_run(summary=f"派活 {n_new} 条(跳过在途 {len(rows)-n_new})", action="派活")  # 记运行日志
    print(f"今天派活 {len(rows)} 条(号×模式):")
    for r in rows:
        tag = r.get("skipped") or (f"→待出文案 {r.get('note_id')}" if a.write else "(干跑)")
        print(f"  {r['account']:20} {r['content_type']:12} 技能={r['gen_skill']:22} 素材={r['material_needs']}  {tag}")
        print(f"    素材来源[{r['sourcing']}]:{r['sourcing_hint']}")
    if not a.write:
        print("(干跑:未写库。加 --write 把活落成『待出文案』占位)")
    # 爆款模仿(trend_imitate)原料:灵感库未转化的爆款灵感,提示可借鉴点+出稿承接
    ideas = dispatch.pending_ideas(a.brand)
    if ideas:
        print(f"\n爆款模仿待办({len(ideas)} 条灵感未转化,trend_imitate 号可据此出稿):")
        for it in ideas[:8]:
            has_body = "有正文✓" if it.get("文案") else "无正文(去灵感库补『文案』)"
            print(f"  · {it['标题']}  可借鉴:{it['可借鉴'] or '—'}  [{has_body}]")
        print("  出稿:draft_one --account <trend_imitate号> --title-seed \"<灵感标题>\" "
              "--source-text \"<灵感库『文案』全文>\";**传 --source-text 防搬运门才比对得到爆款正文**(只给标题=门看不到正文)。"
              "出后回填灵感库『转化为笔记』。")
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
