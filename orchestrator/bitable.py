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
    ACCOUNT = "账号"
    CONTENT_TYPE = "内容类型"
    DRAFT = "文案草稿"
    PUBLISH_LINK = "发布链接"
    PUBLISHED_AT = "实际发布日"
    PLANNED_AT = "计划发布日"
    LINKED_MATERIALS = "关联素材"   # #32 薄执行器选素材挂这里(link→素材表)
    PLAYBOOK = "方法论"        # 显式所属方法论 id(为空则回退 content_type 解析)
    LIKED = "点赞"            # 效果采集写回;热度分是 formula 由 Bitable 自算,不写
    COLLECTED = "收藏"
    COMMENTS = "评论"
    SHARED = "转发"


class MaterialFields:
    TABLE = "素材表"
    CODE = "素材编号"
    TYPE = "类型"
    LINK = "链接"          # url 字段:人点开的分享链(投手一点直达该图/视频)
    REL_PATH = "相对路径"   # text 字段:系统耐久指针(baidupan:/... 或 file://);寻址用,不被 url 改写
    SHOT_STATUS = "拍摄状态"
    SHOOTER = "拍摄人"      # text:谁拍的(可空)
    SHOOT_REQ = "拍摄要求"  # text:拍摄 brief(shotlist 派拍时的要求;可空,现多为空待回填)
    SOURCE = "来源"
    GEN_PARAMS = "生成参数"  # text:仅 AI 素材填(生成/加工参数=provenance 细节,ADR-0004 来源随像素)
    NOTE = "备注"
    THUMB = "缩略图"        # 附件字段:降采样预览图(base 驾驶舱瞄一眼选材,不用点开网盘)
    ACCOUNTS = "适用账号"   # 赛道(账号×模式)投影;打标留空,分发选材时按类型+备注语义现选并回填(消费即记录)
    CITED = "被引用次数"    # 被笔记引用次数(formula 自算);选素材少用优先→分散防撞图 #36


class AccountFields:
    """账号表字段词汇(AccountKernel 对齐 Base 账号行与 workspace Account data 用)。"""
    TABLE = "账号表"
    NAME = "账号名"
    XHS_ID = "小红书号"
    HOMEPAGE = "主页链接"
    LAUNCH_STATUS = "上线状态"
    AUTO_SCHED = "自动排产"          # 运营开关(base owner):暂停=跳过派活;跟随workspace=按 md 节奏
    CONTENT_TYPES_LOOKUP = "内容类型表-所属账号"


class AutoSched:
    """账号表「自动排产」select 取值:base 侧运营开关(暂停/跟随workspace 的唯一真相)。"""
    FIELD = "自动排产"
    PAUSED = "暂停"          # base 强制停(覆盖 md,谁接手都读得到)
    FORCE_ON = "开启"        # base 强制派(覆盖 md,即使 md posts_per_day<1 也派)
    FOLLOW_WS = "跟随workspace"  # 按 workspace 账号 md 的 cadence 节奏派(默认)


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
    ACCOUNT_LINK = "所属账号"


class InspirationFields:
    """灵感库字段词汇(爆款灵感=trend_imitate 出稿原料;此前散在 dispatch 用裸中文串,飞书改名会漏改)。"""
    TABLE = "灵感库"
    TITLE = "标题"
    MERITS = "优点"           # 可借鉴优点
    BODY = "文案"             # 爆款正文——防搬运门比对源(出稿逐字搬这个即拒);出稿时传 generate_draft(source_text=)
    LINK = "链接"             # 爆款源链接
    CONVERTED = "转化为笔记"   # link 字段(写 record_id 列表);非空=已转化,跳过


class KeywordFields:
    """关键词库字段词汇(选题/SEO 池;此前散在 draft.load_keywords 用裸中文串)。"""
    TABLE = "关键词库"
    KEYWORD = "关键词"
    ENABLED = "启用状态"      # 取值≠"禁用"(下方 DISABLED)即视为启用
    DISABLED = "禁用"         # 「启用状态」的禁用取值(select 值,非字段名)


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


# 写库字段格式坑(实测反复踩,codify 防复发):link 字段收 record_id 列表、url 字段收 {link,text} dict,
# 写字符串一律炸(FeishuIOError 5次重试未成功)。写这些字段前用下面 link_value/url_value 包一下。
LINK_FIELDS = frozenset({"账号", "内容类型", "关联素材", "适用账号", "转化为笔记", "关联关键词", "关联笔记"})
URL_FIELDS = frozenset({"发布链接", "链接", "主页链接"})  # 主页链接=URL字段(2026-07实测URLFieldConvFail坐实,曾误当text)


def link_value(record_ids) -> list:
    """link 字段值:record_id(单个 str 或列表)→ record_id 列表(飞书 link 字段只收列表)。"""
    if isinstance(record_ids, str):
        return [record_ids] if record_ids else []
    return list(record_ids or [])


def url_value(url: str, text: str = "") -> dict:
    """url 字段值:URL → {link, text} dict(url 字段写纯字符串会炸)。"""
    return {"link": url, "text": text or url}


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
    """关联字段 → 目标 record_id 列表(飞书 link 字段回读形态:list[{record_ids:[...]}])。
    这几个自由函数 text/parse_ts/link_record_ids = 飞书多形态 record dict 的**唯一收窄 seam**,
    调用点统一 `bitable.text(f.get(字段常量))`;字段名走 NoteFields/MaterialFields/… 词汇常量。"""
    out = []
    if isinstance(v, list):
        for x in v:
            if isinstance(x, dict):
                out += x.get("record_ids", []) or []
    return out
