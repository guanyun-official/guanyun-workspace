"""观云 · 今日面板(顺手:一条命令看完今日头尾要做的事)。纯读,不写库。

  python3 -m scripts.today            # 打印今日:待审/待发/待回填链接/要补拍
  python3 -m scripts.today --alert     # 顺带推飞书(hermes),手机上一眼看完

替代挨个敲 run_day/publish_ready/shot_list——人/接手 agent 每天就看这一个。
"""
from __future__ import annotations

import argparse

from orchestrator import cockpit, config


def _fmt(p: dict) -> str:
    L = [f"📮 观云 · 今日面板（{config.ENV_NAME}）"]
    L.append(f"\n📋 待你审 {len(p['待审'])} 条：")
    for n in p["待审"]:
        L.append(f"   · 「{n['title']}」 {n['account']}")
    L.append(f"\n📤 待你发 {len(p['待发'])} 条（发完回填链接）：")
    for n in p["待发"]:
        L.append(f"   · 「{n['title']}」 {n['account']}")
        for m in n["materials"]:
            L.append(f"       取素材 {m['code']} → {m['link'] or '(无链接)'}")
    if p["待回填链接"]:
        L.append(f"\n🔗 已发待回填链接 {len(p['待回填链接'])} 条（不填回流没数据）：")
        for n in p["待回填链接"]:
            L.append(f"   · 「{n['title']}」 {n['account']}")
    L.append(f"\n📷 要补拍 {len(p['要补拍'])} 项：")
    for s in p["要补拍"]:
        L.append(f"   · {s['account']}｜{s['类型']}：缺 {s['缺']} 条 → {s['投递去向']}")
    if not any([p["待审"], p["待发"], p["待回填链接"], p["要补拍"]]):
        L.append("\n✅ 今日无待办：没要审的、没要发的、库存也够。")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="观云")
    ap.add_argument("--alert", action="store_true", help="推飞书(hermes),手机上看")
    a = ap.parse_args()
    report = _fmt(cockpit.today_panel(a.brand))
    print(report)
    if a.alert:
        from orchestrator import alerts
        alerts.send(report, title="观云·今日面板")
        print("\n(已推飞书)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
