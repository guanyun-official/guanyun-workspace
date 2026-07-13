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


def assert_no_source_leak(sources, payload: str, n: int = 10) -> None:
    """防搬运出口闸(红线):产出不得逐字搬**任何一个对标源**的 ≥n 连续实义字符片段。
    sources = 单个字符串 或 字符串列表(每个都比)。归一化后比对(插空格/改标点/换全半角都绕不过)。

    **必须守住"LLM 真正看得见的东西"**(2026-07-14 真跑发现:这道门以前在守错东西)——

    LLM 在 prompt 里**真正看到**的只有:
      · title_seed(标题线索,来自灵感标题)
      · **gen_skill 的 few-shot 真实帖**(技能白纸黑字写着「只学结构、绝不抄原句」
        「出口过防搬运闸」—— 而**那句话从来没人执行**)
    LLM **从来没看到**的:
      · source_text(对标源正文)—— `compose_prompt` 根本不收它,它只喂给这道门

    于是老实现犯了双重错误:
      1. **守着 LLM 没见过的东西**:只比对 source_text/title_seed。正文既然没进 prompt,
         逐字搬它物理上不可能 —— 这份"保护"是空的。
      2. **真能搬的东西不看**:few-shot 里的真实帖**就在 prompt 里**,LLM 一眼就能照抄。
         真跑实证:把 few-shot 的真实帖标题逐字搬进产出 → **直接过门,一个字都没查**。
      3. 我还一度加过"声称蹭爆款却拿不出正文 → 拒绝出稿"—— **在防一个不存在的风险**
         (正文没进 prompt),同时把整条爆款模仿链路焊死(而正文在非登录下**根本抓不到**:
         小红书详情页对非登录只吐 452 字节空壳)。已撤。

    现在:调用方把**所有进了 prompt 的文本**都传进来(标题线索 + 技能 few-shot),门逐个比。
    守 LLM 真正看得见的东西 —— 这才是"防搬运"三个字的意思。
    """
    if isinstance(sources, str):
        sources = [sources]
    pay = _norm(payload)
    if not pay:
        return
    for s in sources:
        src = _norm(s or "")
        if len(src) < n:
            continue                      # 太短的源不产生保护,也不误伤(如两三字的标题线索)
        for i in range(len(src) - n + 1):
            frag = src[i:i + n]
            if frag in pay:
                raise GuardError(
                    f"防搬运门:产出含对标源 {n} 字连续片段「{frag}」,拒绝"
                    "(爆款/真实帖只当情报,**只学结构、绝不抄原句**)")
