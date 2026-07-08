"""提醒节流(F1):per-笔记 per-类型 每日最多提醒一次。sidecar JSON,单实例(flock 下)无并发。
状态只是"降噪账本",丢了顶多多发一条,不影响正确性——故不进 Base、不做幂等。
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config

STATE_FILE = config.WORKSPACE / "locks" / "reminder_state.json"


def _load() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def should_remind(record_id: str, kind: str, now: datetime | None = None) -> bool:
    """今天是否还没提醒过这条这类。"""
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    return _load().get(f"{kind}:{record_id}") != today


def mark(record_id: str, kind: str, now: datetime | None = None) -> None:
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    d = _load()
    d[f"{kind}:{record_id}"] = today
    # 顺手清理 30 天前的陈旧键,防无限膨胀
    cutoff = today
    d = {k: v for k, v in d.items() if v >= _minus_days(cutoff, 30)}
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _minus_days(day: str, n: int) -> str:
    from datetime import timedelta
    return (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")
