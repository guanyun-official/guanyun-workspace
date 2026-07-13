"""拍摄需求单 CLI(『头』侧:告诉人需要拍什么)。纯读,不写库。

  python3 -m scripts.shot_list            # 打印拍摄需求单(每号缺哪类素材、拍几条、拍摄要求、参考)
  python3 -m scripts.shot_list --alert     # 同时推飞书(hermes),让人在手机收到补拍清单

素材一次性拍完 → 这是补货信号:库存够不提、见底才提。表达=类型+条数+拍摄要求 brief+参考帖。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/shot_list.py 也能跑(不止 -m)

from orchestrator import config, shotlist


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--alert", action="store_true", help="把拍摄需求单推飞书(hermes)")
    a = ap.parse_args()
    print(f"env={config.ENV_NAME} test_mode={config.TEST_MODE} brand={a.brand}")
    needs = shotlist.shot_needs(a.brand)
    if not needs:
        print("\n✅ 各号素材库存都够(≥目标缓冲),暂无需补拍。")
        return 0
    lines = [f"📷 拍摄需求单（{len(needs)} 项待补拍）："]
    for n in needs:
        lines.append(f"  · {n['account']}｜{n['类型']}：缺 {n['缺']} 条（已有 {n['已有']}/目标 {n['目标']}）")
        lines.append(f"      拍摄要求：{n['拍摄要求']}")
        lines.append(f"      拍完丢哪：{n['投递去向']}")
        lines.append(f"      参考：{n['参考']}")
    report = "\n".join(lines)
    print("\n" + report)
    if a.alert:
        from orchestrator import alerts
        alerts.send(report, title="巧荷·拍摄需求单")
        print("\n(已推飞书)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
