"""Bitable 记录适配器(候选A深化:6份重复的字段取值逻辑 + 90+裸字符串 塌成一个 seam)。
纯模块,零 IO——只把飞书那颗多形态 record dict 收进窄接口。runbook 等纯函数可放心 import。

字段形态(飞书 record.fields 的值):
- 文本/单选/超链: str 或 {"text":..,"link":..}
- 关联/lookup/富文本: list[{"text":..,"record_ids":[..]}]
- 日期: 毫秒时间戳 int(或上述 list/dict 包裹)
- checkbox: bool
"""
from __future__ import annotations

from datetime import datetime


class NoteFields:
    """笔记表字段词汇(取代散落 90+ 裸字符串;飞书改名只改这里)。"""
    CODE = "排期编号"
    TITLE = "标题"
    STATUS = "状态"
    AI_DECLARED = "AI声明"
    ACCOUNT = "账号(自动)"
    CONTENT_TYPE = "内容类型"
    DRAFT = "文案草稿"
    STORYBOARD = "脚本·分镜"
    PUBLISH_LINK = "发布链接"
    PUBLISHED_AT = "实际发布日"
    PLANNED_AT = "计划发布日"
    LINKED_CLOTHES = "关联衣服"
    LINKED_MATERIALS = "关联素材"


class MaterialFields:
    CODE = "素材编号"
    TYPE = "类型"
    LINK = "链接"
    SHOT_STATUS = "拍摄状态"
    SOURCE = "来源"
    NOTE = "备注"
    LINKED_CLOTHES = "关联衣服"
    LINKED_CRAFT = "关联面料·工艺"
    ACCOUNTS = "适用账号"


def text(v) -> str:
    """任意字段值 → 文本。list[dict]→逗号连;dict→text/link;标量→str。"""
    if isinstance(v, list):
        return ",".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("text") or v.get("link") or "")
    return str(v or "")


def parse_ts(v) -> datetime | None:
    """日期字段 → datetime。容错 int(毫秒)/数字串/list[dict]/dict(lookup·公式形态)。"""
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("value") or v.get("text")
        if isinstance(v, list):
            v = v[0] if v else None
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000)
    if isinstance(v, str) and v.isdigit():
        return datetime.fromtimestamp(int(v) / 1000)
    return None


def link_record_ids(v) -> list[str]:
    """关联字段 → 目标 record_id 列表。"""
    out = []
    if isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                out += x.get("record_ids", []) or []
    return out


class Record:
    """一条飞书记录的窄接口。包 raw(record dict 或其 fields)。"""

    def __init__(self, raw: dict):
        self.record_id = raw.get("record_id", "")
        self.f = raw.get("fields", raw)

    def text(self, field: str) -> str:
        return text(self.f.get(field))

    def ts(self, field: str) -> datetime | None:
        return parse_ts(self.f.get(field))

    def link_ids(self, field: str) -> list[str]:
        return link_record_ids(self.f.get(field))

    def bool(self, field: str) -> bool:
        return bool(self.f.get(field))

    def raw(self, field: str):
        return self.f.get(field)
