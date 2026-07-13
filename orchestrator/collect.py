"""回流采集薄执行器(效果闭环第二半;每周一轮)。

读笔记表「已发」且有「发布链接」的 note → 调 metrics 采集互动数据(内部走 xhs-extract-master
**非登录**采集 skill,零封号不用我方账号)→ 写回笔记表 点赞/收藏/评论/转发(热度分是 formula 自算不写)。
默认 stub 零成本(不写,不造假数据);--real 才真采集。红线:只读采集 + 只写测试库,绝不碰发布。

这就是架构里「薄执行器调 skill 把 Note 推到下一格」的一个动作:采集能力是可替换 skill(换采集源=换 skill),
薄执行器只编排(读 owner→调 skill→写 owner),不含采集实现。复盘用 metrics.aggregate_by_playbook。
"""
from __future__ import annotations

from datetime import date, timedelta

from . import bitable, config, feishu_io, guard, metrics
from .bitable import NoteFields as NF, NoteStatus as NS


def _link(v) -> str:
    """发布链接(url 字段)→ **真链接**:dict 取 link(不是 text!否则拿到描述文字采集失败),字符串原样。
    实测发现:collect 曾用 bitable.text 取链接,url 字段 text 优先→拿到标题而非 URL,真采集必挂。"""
    if isinstance(v, dict):
        return str(v.get("link") or v.get("text") or "").strip()
    return bitable.text(v).strip()


def harvestable_notes(refresh_days: int | None = None) -> list[dict]:
    """可回流的 note:状态=已发(首采)或 已回流(刷新热度),且有发布链接。
    **冷热分离(规模M4)**:已回流是累积态(每帖终身停这),无限重刷=硬墙。分两路:
    - 首采:状态=已发——采到即转已回流,是过渡态、本身只一个采集周期的量,全取(无日期条件,不漏新帖);
    - 刷新:状态=已回流 且 实际发布日≥近 refresh_days 天——老帖热度已定不再重刷(服务端日期窗,实测真跑)。
    老已回流帖(超窗/无发布日)自然沉降出热集,不再随历史线性膨胀。"""
    refresh_days = config.COLLECT_REFRESH_DAYS if refresh_days is None else refresh_days
    since = str(bitable.day_start_ms(date.today() - timedelta(days=refresh_days)))
    fresh = feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.PUBLISHED])            # 首采:过渡态,小
    refresh = feishu_io.search_records(NF.TABLE, [                              # 刷新:仅近窗已回流
        {"field_name": NF.STATUS, "operator": "is", "value": [NS.LOOPED_BACK]},
        {"field_name": NF.PUBLISHED_AT, "operator": "isGreater", "value": ["ExactDate", since]}],
        conjunction="and")
    return [r for r in fresh + refresh if _link(r["fields"].get(NF.PUBLISH_LINK))]



def collect_and_writeback(mode: str = "stub", limit: int = 50) -> dict:
    """对每条可回流 note 采集互动数据并写回;**已发采集成功后推进→已回流**(状态机闭环,复盘据此有数据)。
    stub 默认返 {} 不写(零成本);--real 走非登录采集。采集失败/空不阻断、不推进(下轮重试)。返回 {采集, 写回}。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    notes = harvestable_notes()[:limit]
    updated = 0
    for r in notes:
        url = _link(r["fields"].get(NF.PUBLISH_LINK))   # 取真链接(dict.link),不是 text
        vals = metrics.collect(url, mode=mode)   # {NF.LIKED: n, NF.COLLECTED: n, ...};stub→{}
        if not vals:
            continue                              # 采集失败/空:不写、不推进,下轮重试
        if bitable.text(r["fields"].get(NF.STATUS)) == NS.PUBLISHED:
            vals = {**vals, NF.STATUS: NS.LOOPED_BACK}   # 已发→已回流(采到数据才推进状态机)
        feishu_io.update_record(NF.TABLE, r["record_id"], vals)
        updated += 1
    return {"采集": len(notes), "写回": updated}
