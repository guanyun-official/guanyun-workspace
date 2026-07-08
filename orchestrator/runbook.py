"""runbook:状态 → 动作 路由(纯函数,零 LLM 零 IO)。
状态机: 想法储备→待拍素材→待出文案→草稿待发(=待审)→已批准→待发布→已发→已回流;暂缓归档旁路。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum


class Action(Enum):
    NOOP = "无动作"
    LIST_IDEA = "列入储备清单(日报)"
    REMIND_SHOOT = "催拍"
    GEN_COPY = "生成文案草稿"
    REMIND_REVIEW = "催审"
    ASSEMBLE_PACKAGE = "组装发布包"
    MARK_PUBLISHED = "检测到发布回填→置已发"
    COLLECT_METRICS = "效果回流采集"
    CLOSE_LOOP = "回流收口→置已回流"


def route(fields: dict, now: datetime, review_overdue_hours: int = 24, metrics_close_days: int = 7) -> Action:
    """按笔记记录字段决定下一动作。只读字段,不产生副作用。"""
    state = fields.get("状态")
    if state in (None, "", "暂缓归档", "已回流"):
        return Action.NOOP
    if state == "想法储备":
        return Action.LIST_IDEA
    if state == "待拍素材":
        return Action.REMIND_SHOOT
    if state == "待出文案":
        return Action.GEN_COPY
    if state == "草稿待发":  # =待审:人审卡点,推进器只催不推
        entered = _ts(fields.get("_state_changed_at")) or _ts(fields.get("计划发布日"))
        if entered and now - entered > timedelta(hours=review_overdue_hours):
            return Action.REMIND_REVIEW
        return Action.NOOP
    if state == "已批准":
        return Action.ASSEMBLE_PACKAGE
    if state == "待发布":
        # 人发布后回填「发布链接」;推进器检测到即置已发
        if fields.get("发布链接"):
            return Action.MARK_PUBLISHED
        return Action.NOOP
    if state == "已发":
        pub = _ts(fields.get("实际发布日"))
        if pub and now - pub >= timedelta(days=metrics_close_days):
            return Action.CLOSE_LOOP
        return Action.COLLECT_METRICS
    return Action.NOOP  # 未知状态:不动 + 由 engine 记告警


def _ts(v) -> datetime | None:
    """bitable 日期字段=毫秒时间戳(int)或空;容错字符串。"""
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000)
    if isinstance(v, str) and v.isdigit():
        return datetime.fromtimestamp(int(v) / 1000)
    return None
