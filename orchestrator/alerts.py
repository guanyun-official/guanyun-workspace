"""投递到人眼前(Observation 的最后一公里):文本走 hermes 网关,交互卡片走 lark-cli。

**运营不敲终端。** 算出来、判出来的东西没送到他手机上 = 等于没算。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

HOME_CHAT = os.environ.get("GY_FEISHU_CHAT", "oc_efa54ec613c82e240925eb04f42c7da0")


def send_card(card: dict, chat_id: str = "") -> bool:
    """发飞书**交互卡片**(lark-cli im,bot 身份)。今日卡片/补拍单/周报卡都走它。
    发失败**如实返回 False 并打印原因**——绝不假装发出去了(人在等,而消息根本没到)。"""
    args = ["lark-cli", "im", "+messages-send", "--as", "bot",
            "--chat-id", chat_id or HOME_CHAT,
            "--msg-type", "interactive", "--content", json.dumps(card, ensure_ascii=False)]
    env = {**os.environ, "LARK_CLI_NO_PROXY": "1"}
    try:
        r = subprocess.run(args, capture_output=True, text=True, env=env, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"[卡片没发出去] {e}")
        return False
    ok = r.returncode == 0 and '"code":0' in (r.stdout or "")
    if not ok:
        print(f"[卡片没发出去] {(r.stdout or r.stderr)[-300:]}")
    return ok


def send(text: str, *, title: str = "巧荷推进器") -> bool:
    msg = f"【{title}】\n{text}"
    if os.environ.get("ALERT_DRY_RUN", "0") == "1" or not shutil.which("hermes"):
        print(f"[alert:dry] {msg}")
        return False
    target = os.environ.get("HERMES_TO", "feishu")
    try:
        subprocess.run(["hermes", "send", "--to", target, msg],
                       capture_output=True, text=True, timeout=20, check=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[alert 降级 stdout] {e}\n{msg}")
        return False
