"""runbook:状态 → 动作 路由(纯函数,零 LLM 零 IO)。
状态机: 想法储备→待拍素材→待出文案→草稿待发(=待审)→已批准→待发布→已发→已回流;暂缓归档旁路。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from .bitable import NoteFields as NF
from .bitable import NoteStatus as NS
from .bitable import Record
from .bitable import parse_ts  # 单一 ts 解析源(re-export,原 runbook._ts→bitable.parse_ts)


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
    """按笔记记录字段决定下一动作。只读字段,不产生副作用。字段访问经 bitable.Record(候选A)。"""
    r = Record(fields)
    state = r.text(NF.STATUS) or None
    if state in (None, "", NS.ON_HOLD, NS.LOOPED_BACK):
        return Action.NOOP
    if state == NS.IDEA:
        return Action.LIST_IDEA
    if state == NS.NEED_SHOOT:
        return Action.REMIND_SHOOT
    if state == NS.NEED_COPY:
        return Action.GEN_COPY
    if state == NS.DRAFT_PENDING:  # =待审:人审卡点,推进器只催不推
        entered = parse_ts(fields.get("_state_changed_at")) or r.ts(NF.PLANNED_AT)
        if entered and now - entered > timedelta(hours=review_overdue_hours):
            return Action.REMIND_REVIEW
        return Action.NOOP
    if state == NS.APPROVED:
        return Action.ASSEMBLE_PACKAGE
    if state == NS.TO_PUBLISH:
        # 人发布后回填「发布链接」;推进器检测到即置已发
        if r.raw(NF.PUBLISH_LINK):
            return Action.MARK_PUBLISHED
        return Action.NOOP
    if state == NS.PUBLISHED:
        pub = r.ts(NF.PUBLISHED_AT)
        if pub and now - pub >= timedelta(days=metrics_close_days):
            return Action.CLOSE_LOOP
        return Action.COLLECT_METRICS
    return Action.NOOP  # 未知状态:不动 + 由 engine 记告警
