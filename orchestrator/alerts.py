"""即时告警/摘要投递:hermes 飞书网关;ALERT_DRY_RUN=1 或 hermes 缺席时降级 stdout。"""
from __future__ import annotations

import os
import shutil
import subprocess


def send(text: str, *, title: str = "观云推进器") -> bool:
    msg = f"【{title}】\n{text}"
    if os.environ.get("ALERT_DRY_RUN", "0") == "1" or not shutil.which("hermes"):
        print(f"[alert:dry] {msg}")
        return False
    try:
        subprocess.run(["hermes", "send", msg], capture_output=True, text=True, timeout=15, check=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[alert 降级 stdout] {e}\n{msg}")
        return False
