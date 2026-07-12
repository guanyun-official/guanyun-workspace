"""找热点 → 灵感库(系统化热点采集的『落库』一环)。

分工同薄执行器:**『找』热点由 skill(explosive-teardown / qiaohe-amateur-miner)或 agent 负责**,产出
[{标题, 可借鉴, 源链接}];**『落』由本函数收口**——按标题去重(不重复灌)、URL 字段正确包装、只写测试库。
落库后 dispatch.pending_ideas 自动捞出未转化的,draft_one --title-seed 承接出稿(trend_imitate 闭环)。
"""
from __future__ import annotations

from . import bitable, config, feishu_io, guard
from .bitable import InspirationFields as IF


def harvest_trends(items: list[dict], brand: str = "巧荷", write: bool = False) -> dict:
    """把找到的热点/爆款灵感落灵感库。items=[{标题, 可借鉴?, 源链接?}]。
    按标题去重(已在库跳过);write=False 干跑预览、True 落库(过 base 红线闸)。返回 {新增, 去重跳过}。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    existing = {bitable.text(r["fields"].get(IF.TITLE)).strip()
                for r in feishu_io.list_records(IF.TABLE)}
    new: list[str] = []
    dup: list[str] = []
    for it in items:
        title = (it.get("标题") or "").strip()
        if not title:
            continue
        if title in existing:
            dup.append(title)
            continue
        row: dict = {IF.TITLE: title}
        if it.get("可借鉴"):
            row[IF.MERITS] = it["可借鉴"]
        if it.get("源链接"):
            row[IF.LINK] = bitable.url_value(it["源链接"])   # 链接是 URL 字段,须 {link,text} 包
        if write:
            feishu_io.create_record(IF.TABLE, row)
        new.append(title)
        existing.add(title)
    return {"新增": new, "去重跳过": dup}
