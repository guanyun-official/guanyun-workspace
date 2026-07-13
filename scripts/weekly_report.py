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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
