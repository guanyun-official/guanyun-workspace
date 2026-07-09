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
    TABLE = "笔记表"
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
    TABLE = "素材表"
    CODE = "素材编号"
    TYPE = "类型"
    LINK = "链接"
    SHOT_STATUS = "拍摄状态"
    SOURCE = "来源"
    NOTE = "备注"
    LINKED_CLOTHES = "关联衣服"
    LINKED_CRAFT = "关联面料·工艺"
    ACCOUNTS = "适用账号"


class ClothesFields:
    """衣服总表字段词汇(planner 排产、ingest 挂 SKU 用)。"""
    TABLE = "衣服总表"
    CODE = "衣服编号"
    NAME = "款式名称"


class MaterialStatus:
    """素材拍摄状态取值(素材表 拍摄状态 select 枚举)。planner 靠「已拍」判可用素材。"""
    TABLE = "素材表"
    FIELD = "拍摄状态"
    NEED_SHOOT = "待拍"
    SHOT = "已拍"


class MaterialSource:
    """素材来源取值(素材表 来源 select 枚举)。生成媒体标 AI生成、拍摄标 实拍。"""
    TABLE = "素材表"
    FIELD = "来源"
    REAL = "实拍"
    AI = "AI生成"


class RunLogFields:
    """运行日志表字段词汇(9 字段契约;log_run 写、_monthly_cost_cny 读)。"""
    TABLE = "运行日志表"
    SUMMARY = "摘要"
    TIME = "时间"
    EXECUTOR = "执行体"
    SKILL = "技能"
    ACTION = "动作"
    TABLE_REF = "涉及表"
    RECORD_REF = "涉及记录"
    RESULT = "结果"
    DETAIL = "详情"
    COST = "成本_元"  # 数值成本(M3 已在测试库落字段);_cost_of_log 优先读它


class ContentTypeFields:
    """内容类型表字段词汇(引擎格式感知:内容类型名→格式 查表)。"""
    TABLE = "内容类型表"
    NAME = "内容类型名"
    FORMAT = "格式"


class NoteStatus:
    """笔记状态机取值(状态列 select 枚举;写回只能用声明过的值,否则飞书拒写/静默落空)。
    状态机: 想法储备→待拍素材→待出文案→草稿待发(=待审)→已批准→待发布→已发→已回流;暂缓归档旁路。"""
    TABLE = "笔记表"
    FIELD = "状态"
    IDEA = "想法储备"
    NEED_SHOOT = "待拍素材"
    NEED_COPY = "待出文案"
    DRAFT_PENDING = "草稿待发"  # =待审:人审卡点
    APPROVED = "已批准"
    TO_PUBLISH = "待发布"
    PUBLISHED = "已发"
    LOOPED_BACK = "已回流"
    ON_HOLD = "暂缓归档"


# 元属性(定位 schema 用,非字段/取值本身),契约收集时排除
_META_ATTRS = frozenset({"TABLE", "FIELD"})


def declared_field_names(fieldset: type) -> list[str]:
    """字段词汇/取值类里声明的常量值(UPPERCASE,排除 TABLE/FIELD 元属性)——供 schema 契约校验:
    代码消费 ⊆ 声明。飞书 UI 改字段名/删 select 选项而代码没跟上 → 契约测试红,不静默漂移。"""
    return [v for k, v in vars(fieldset).items()
            if k.isupper() and k not in _META_ATTRS and isinstance(v, str)]


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
