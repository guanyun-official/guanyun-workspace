"""硬闸(纯函数,零 IO):Base 守卫 / AI 声明门 / 控量门 / 防搬运门。闸不过 = 抛 GuardError,不静默。"""
from __future__ import annotations

import re

from . import config
from .bitable import NoteFields as NF


def _norm(s: str) -> str:
    """归一化:去所有空白/标点/下划线,只留实义字符(中文/字母/数字)。
    防搬运比对的前置——插空格、改标点、换全半角标点都归到同一串,搬运者绕不过。"""
    return re.sub(r"[\s\W_]+", "", s or "", flags=re.UNICODE)


class GuardError(RuntimeError):
    """硬闸拒绝。message 面向告警可读。"""


def assert_base_allowed(base_token: str, test_mode: bool) -> None:
    """TEST_MODE 下只许写**已登记品牌的测试 Base**;写生产必须显式 TEST_MODE=0 且 token 属已登记生产 Base。
    白名单走 config.known_bases(多品牌注册表):目前仅巧荷,加品牌=注册表加一行即自动放行其 Base(接口已留)。"""
    if not base_token:
        raise GuardError("Base 守卫:LARK_APP_TOKEN 为空")
    env = "test" if test_mode else "prod"
    if base_token not in config.known_bases(env):
        raise GuardError(f"Base 守卫:TEST_MODE={'1' if test_mode else '0'} 只允许已登记品牌的{env} Base,"
                         f"当前 {base_token[:8]}…被拒(加品牌请在 config.BRAND_BASES 登记)")


def ai_declaration_required(material_sources) -> bool:
    """AI 声明是否**必须**(法规规则,纯函数吃素材来源列表):
    挂的素材任一『来源=AI生成』(真合成了新内容)→ 必须勾;全『实拍』(哪怕 AI 剪辑但没往里合成新画面)→ 无需勾。
    判定依据是**素材来源事实**,不是人工拍脑袋——这样实拍内容不必每条手动确认,AI 合成内容一条都跑不掉。"""
    from .bitable import MaterialSource as MSrc
    return any((s or "").strip() == MSrc.AI for s in (material_sources or []))


def assert_ai_declared(fields: dict, *, ai_required: bool = True) -> None:
    """已批准 → 待发布 前的 AI 声明门。
    ai_required=False(素材全实拍)→ 法规无需 AI 标识,放行(免除人工勾);
    ai_required=True(含 AI 合成素材,默认)→ AI 声明必须已勾(**人勾,机器绝不代勾**),否则抛。"""
    if not ai_required:
        return
    if not fields.get(NF.AI_DECLARED):
        raise GuardError(f"AI声明门:「{fields.get(NF.CODE, '?')}」含 AI 合成素材但未勾 AI声明,拒绝进入待发布")


def assert_has_material(material_count: int, code: str = "?") -> None:
    """**零素材门**:一张图/视频都没挂的稿,**物理上发不出去**(小红书图文/视频都必须有媒体)。

    2026-07-14 走运营流程发现:『待发布』队列里 **5 条稿全是零素材**——运营打开卡片准备发,
    点进 base 一张图都没有,今天一条都发不了。根因是进入『待发布』的路径上**根本没有素材检查**:
    发不出去的稿被放进了待发区,让运营到最后一步才发现。
    拦在门外,而不是放进去再让人扑空。"""
    if material_count <= 0:
        raise GuardError(f"零素材门:「{code}」一张图/视频都没挂,小红书发不出去——先去 base 关联素材")


def assert_publish_quota(published_today_for_account: int) -> None:
    """单号每日发布上限(平台风控红线)。推进器只在组装发布包时预检。"""
    if published_today_for_account >= config.PER_ACCOUNT_DAILY_PUBLISH:
        raise GuardError(
            f"控量门:该账号今日已发/待发 {published_today_for_account} 篇,达上限 {config.PER_ACCOUNT_DAILY_PUBLISH}"
        )


def assert_no_source_leak(source_text: str, payload: str, n: int = 10,
                          imitating: bool = False) -> None:
    """防搬运出口闸(红线):产出 payload 不得逐字搬对标/灵感源 source_text 的 ≥n 连续实义字符片段。
    爆款只当情报——出稿不得含对标原帖/原标题的连续片段。**先归一化去空白/标点再比对**,
    加空格/改标点也绕不过(这是该红线的唯一实现,原 lib/skill_gate 那份已退役并入此处)。

    **imitating=True 时,拿不出源正文 = 直接拒绝**(2026-07-14 全体系对齐审查抓到的红线空洞)。
    原来这里写着"源过短 → 放行(短源不产生保护也不误伤,**设计取舍**)"——而真实数据里
    **灵感库 5 条,『文案』字段全是空的**(找热点那一步从没抓过正文)。于是门每次都走"提前放行",
    **整段逐字搬也能过**。门造好了、装上了、单测也绿,可它比对的东西在真数据里根本不存在——
    这是这类病最危险的形态:**不是没做,是做了、看着像在保护你、实际是空的**。
    门自己判断不了调用方是不是在蹭爆款,所以**由调用方声明**:声称在模仿某条爆款、却拿不出源正文,
    就必须拒绝(不然"防搬运"三个字是假的)。非模仿场景(自由创作)仍按原样放行,不误伤。
    """
    src, pay = _norm(source_text), _norm(payload)
    if imitating and len(src) < n:
        raise GuardError(
            "防搬运门:这条稿声称在**蹭爆款/模仿灵感**,却拿不出对标源正文 —— 门无从比对,"
            "等于没门。先去灵感库把该条的『文案』(原帖正文)补上,再出稿"
            "(draft_one 传 --source-text)。")
    if len(src) < n or not pay:
        return
    for i in range(len(src) - n + 1):
        frag = src[i:i + n]
        if frag in pay:
            raise GuardError(f"防搬运门:产出含对标源 {n} 字连续片段「{frag}」,拒绝(爆款只当情报,不搬原文)")
