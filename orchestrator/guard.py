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


def assert_publish_quota(published_today_for_account: int) -> None:
    """单号每日发布上限(平台风控红线)。推进器只在组装发布包时预检。"""
    if published_today_for_account >= config.PER_ACCOUNT_DAILY_PUBLISH:
        raise GuardError(
            f"控量门:该账号今日已发/待发 {published_today_for_account} 篇,达上限 {config.PER_ACCOUNT_DAILY_PUBLISH}"
        )


def assert_no_source_leak(source_text: str, payload: str, n: int = 10) -> None:
    """防搬运出口闸(红线):产出 payload 不得逐字搬对标/灵感源 source_text 的 ≥n 连续实义字符片段。
    爆款只当情报——出稿不得含对标原帖/原标题的连续片段。**先归一化去空白/标点再比对**,
    加空格/改标点也绕不过(这是该红线的唯一实现,原 lib/skill_gate 那份已退役并入此处)。
    source 归一化后过短 / payload 空 → 放行(短源不产生保护也不误伤,设计取舍)。"""
    src, pay = _norm(source_text), _norm(payload)
    if len(src) < n or not pay:
        return
    for i in range(len(src) - n + 1):
        frag = src[i:i + n]
        if frag in pay:
            raise GuardError(f"防搬运门:产出含对标源 {n} 字连续片段「{frag}」,拒绝(爆款只当情报,不搬原文)")
