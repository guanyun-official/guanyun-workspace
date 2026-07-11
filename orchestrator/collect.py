"""回流采集薄执行器(效果闭环第二半;每周一轮)。

读笔记表「已发」且有「发布链接」的 note → 调 metrics 采集互动数据(内部走 xhs-extract-master
**非登录**采集 skill,零封号不用我方账号)→ 写回笔记表 点赞/收藏/评论/转发(热度分是 formula 自算不写)。
默认 stub 零成本(不写,不造假数据);--real 才真采集。红线:只读采集 + 只写测试库,绝不碰发布。

这就是架构里「薄执行器调 skill 把 Note 推到下一格」的一个动作:采集能力是可替换 skill(换采集源=换 skill),
薄执行器只编排(读 owner→调 skill→写 owner),不含采集实现。复盘用 metrics.aggregate_by_playbook。
"""
from __future__ import annotations

from . import bitable, config, feishu_io, guard, metrics
from .bitable import NoteFields as NF, NoteStatus as NS


def published_notes() -> list[dict]:
    """笔记表里 状态=已发 且有 发布链接 的 note(record dict)。"""
    out = []
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        if bitable.text(f.get(NF.STATUS)) == NS.PUBLISHED and bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            out.append(r)
    return out


def collect_and_writeback(mode: str = "stub", limit: int = 50) -> dict:
    """对每条已发 note 采集互动数据并写回。返回 {采集, 写回}。
    stub 默认返 {} 不写(零成本);--real 走非登录采集。采集失败/空不阻断(下轮重试)。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    notes = published_notes()[:limit]
    updated = 0
    for r in notes:
        url = bitable.text(r["fields"].get(NF.PUBLISH_LINK)).strip()
        vals = metrics.collect(url, mode=mode)   # {NF.LIKED: n, NF.COLLECTED: n, ...};stub→{}
        if vals:
            feishu_io.update_record(NF.TABLE, r["record_id"], vals)
            updated += 1
    return {"采集": len(notes), "写回": updated}
