"""今日驾驶舱(顺手:人/接手 agent 一条命令看完今日,不用挨个敲 run_day/publish_ready/shot_list)。

聚合人只管头尾要看的四件事(纯读,不写库、不触 LLM):
- 待审:草稿待发的笔记(你点批准)
- 待发:待发布的笔记 + 每条『用哪张素材+可开链接』(你手机发)
- 待回填链接:已发但还没贴发布链接的(不贴回流采集抓不到数据)
- 要补拍:库存见底的拍摄需求(你按需拍)
"""
from __future__ import annotations

from . import bitable, feishu_io, publish, shotlist
from .bitable import NoteFields as NF, NoteStatus as NS


def today_panel(brand: str = "观云") -> dict:
    """今日面板:一次读全笔记表+素材,分出 待审/待发/待回填链接/要补拍。纯读。"""
    idx = publish._material_index()
    pend_review: list[dict] = []
    to_publish: list[dict] = []
    need_link: list[dict] = []
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        title = bitable.text(f.get(NF.TITLE))
        acc = bitable.text(f.get(NF.ACCOUNT))
        if st == NS.DRAFT_PENDING:
            pend_review.append({"title": title, "account": acc})
        elif st == NS.TO_PUBLISH:
            mats = publish.note_materials(f, idx)
            to_publish.append({"title": title, "account": acc,
                               "materials": [{"code": m["code"], "link": m["取用链接"]} for m in mats]})
        elif st == NS.PUBLISHED and not bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            need_link.append({"title": title, "account": acc})
    return {"待审": pend_review, "待发": to_publish,
            "待回填链接": need_link, "要补拍": shotlist.shot_needs(brand)}
