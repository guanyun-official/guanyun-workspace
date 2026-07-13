"""每周总结 CLI（人只管头尾的『每周有总结』）。读回流效果数 → 人可读周报,可推飞书。

  python3 -m scripts.weekly_report            # 打印本周复盘
  python3 -m scripts.weekly_report --alert     # 同时推飞书(hermes)

纯读不写库。喂周复盘飞轮/人调技能权重。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/weekly_report.py 也能跑(不止 -m)

from orchestrator import config, feishu_io, report, shotlist
from orchestrator.bitable import NoteFields as NF


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--alert", action="store_true", help="推飞书(hermes)")
    ap.add_argument("--schedule-card", action="store_true",
                    help="连本周排期卡片一起推(运营周一要看这周该发什么)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand}")
    notes = [r["fields"] for r in feishu_io.list_records(NF.TABLE)]
    needs = shotlist.shot_needs(a.brand)
    summary = report.weekly_summary(notes, needs=needs)
    text = report.format_weekly(summary)
    print("\n" + text)
    if a.alert:
        from orchestrator import alerts
        alerts.send(text, title="巧荷·本周复盘")
        print("\n(已推飞书)")

    # **本周排期卡片**(2026-07-14 对齐审查:`cockpit.weekly_schedule_card` 生产零调用 = 造好了从没推给人)。
    # 运营周一要的不只是"上周表现",更是"**这周该发什么**"——排期卡片就是答这个的,一直躺在代码里没人推。
    if a.schedule_card:
        from orchestrator import cockpit
        from scripts.today import send_card
        card = cockpit.weekly_schedule_card(a.brand)
        send_card(card, dry=not a.alert)     # --alert 才真发,否则打印 JSON
        print("\n(本周排期卡片:运营周一一眼看清这周每天该发什么)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
