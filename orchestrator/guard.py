"""硬闸(纯函数,零 IO):Base 守卫 / AI 声明门 / 控量门。闸不过 = 抛 GuardError,不静默。"""
from __future__ import annotations

from . import config
from .bitable import NoteFields as NF


class GuardError(RuntimeError):
    """硬闸拒绝。message 面向告警可读。"""


def assert_base_allowed(base_token: str, test_mode: bool) -> None:
    """TEST_MODE 下只许写测试 Base;写生产必须显式 TEST_MODE=0 且 token 等于已知生产。"""
    if not base_token:
        raise GuardError("Base 守卫:LARK_APP_TOKEN 为空")
    if test_mode:
        if base_token != config.TEST_BASE:
            raise GuardError(f"Base 守卫:TEST_MODE=1 只允许写测试 Base,当前 {base_token[:8]}…被拒")
        return
    if base_token != config.PROD_BASE:
        raise GuardError(f"Base 守卫:TEST_MODE=0 仅允许已知生产 Base,当前 {base_token[:8]}…被拒")


def assert_ai_declared(fields: dict) -> None:
    """已批准 → 待发布 前:AI 声明必须已置位(法规红线,发布包完整性门)。"""
    if not fields.get(NF.AI_DECLARED):
        raise GuardError(f"AI声明门:「{fields.get(NF.CODE, '?')}」未置 AI声明,拒绝进入待发布")


def assert_publish_quota(published_today_for_account: int) -> None:
    """单号每日发布上限(平台风控红线)。推进器只在组装发布包时预检。"""
    if published_today_for_account >= config.PER_ACCOUNT_DAILY_PUBLISH:
        raise GuardError(
            f"控量门:该账号今日已发/待发 {published_today_for_account} 篇,达上限 {config.PER_ACCOUNT_DAILY_PUBLISH}"
        )


def copy_quota_left(generated_this_run: int) -> bool:
    """每轮文案生成配额(成本闸):超额返回 False(跳过,不抛错——非异常路径)。"""
    return generated_this_run < config.PER_RUN_COPY_LIMIT


def assert_no_source_leak(source_text: str, payload: str, n: int = 10) -> None:
    """防搬运出口闸(红线):产出 payload 不得逐字搬对标/灵感源 source_text 的 ≥n 连续字符片段。
    爆款只当情报——出稿不得含对标原帖/原标题的连续片段。source 空/过短放行。"""
    src = (source_text or "").strip()
    if len(src) < n or not payload:
        return
    for i in range(len(src) - n + 1):
        frag = src[i:i + n]
        if frag in payload:
            raise GuardError(f"防搬运门:产出含对标源 {n} 字连续片段「{frag}」,拒绝(爆款只当情报,不搬原文)")
