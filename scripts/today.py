"""巧荷 · 今日面板(顺手:一条命令看完今日头尾要做的事)。纯读,不写库。

  python3 -m scripts.today            # 打印今日:待审/待发/待回填链接/要补拍
  python3 -m scripts.today --alert     # 顺带推飞书(hermes),手机上一眼看完

替代挨个敲 run_day/publish_ready/shot_list——人/接手 agent 每天就看这一个。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 直接 python3 scripts/today.py 也能跑(不止 -m)

from orchestrator import cockpit, config

# 告警/面板发 bot 私聊(p2p);上线再指向工作群(要群 chat_id + 确认,对外动作)。可 env 覆盖。
HOME_CHAT = os.environ.get("GY_FEISHU_CHAT", "oc_efa54ec613c82e240925eb04f42c7da0")


def send_card(card: dict, chat_id: str = HOME_CHAT, dry: bool = True) -> bool:
    """发飞书交互卡片(lark-cli im,bot 身份)。dry=True 只打印 JSON 不发。"""
    args = ["lark-cli", "im", "+messages-send", "--as", "bot", "--chat-id", chat_id,
            "--msg-type", "interactive", "--content", json.dumps(card, ensure_ascii=False)]
    if dry:
        print(json.dumps(card, ensure_ascii=False, indent=1))
        print(f"\n(干跑:未发。加 --send 真发到 {chat_id})")
        return False
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=30)
    print((r.stdout or r.stderr)[-300:])
    return r.returncode == 0 and '"ok"' in r.stdout and 'true' in r.stdout


def _fmt(p: dict) -> str:
    L = [f"📮 巧荷 · 今日面板（{config.ENV_NAME}）"]
    L.append(f"\n📋 待你审 {len(p['待审'])} 条：")
    for n in p["待审"]:
        L.append(f"   · 「{n['title']}」 {n['account']}" + (f"  → 打开审批 {n['open']}" if n.get("open") else ""))
    L.append(f"\n📤 待你发 {len(p['待发'])} 条（发完回填链接）：")
    for n in p["待发"]:
        L.append(f"   · 「{n['title']}」 {n['account']}" + (f"  → 打开 {n['open']}" if n.get("open") else ""))
        for m in n["materials"]:
            L.append(f"       取素材 {m['code']} → {m['link'] or '(无链接)'}")
    if p["待回填链接"]:
        L.append(f"\n🔗 已发待回填链接 {len(p['待回填链接'])} 条（不填回流没数据）：")
        for n in p["待回填链接"]:
            L.append(f"   · 「{n['title']}」 {n['account']}" + (f"  → 打开回填 {n['open']}" if n.get("open") else ""))
    L.append(f"\n📷 要补拍 {len(p['要补拍'])} 项：")
    for s in p["要补拍"]:
        L.append(f"   · {s['account']}｜{s['类型']}：缺 {s['缺']} 条 → {s['投递去向']}")
    if not any([p["待审"], p["待发"], p["待回填链接"], p["要补拍"]]):
        L.append("\n✅ 今日无待办：没要审的、没要发的、库存也够。")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="巧荷")
    ap.add_argument("--alert", action="store_true", help="推飞书纯文本(hermes)")
    ap.add_argument("--card", action="store_true", help="生成飞书交互卡片(默认干打印 JSON)")
    ap.add_argument("--send", action="store_true", help="配合 --card:真发卡片到 bot 私聊")
    a = ap.parse_args()
    if a.card:
        card = cockpit.today_card(a.brand)
        send_card(card, dry=not a.send)
        return 0
    report = _fmt(cockpit.today_panel(a.brand))
    print(report)
    if a.alert:
        from orchestrator import alerts
        alerts.send(report, title="巧荷·今日面板")
        print("\n(已推飞书)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
