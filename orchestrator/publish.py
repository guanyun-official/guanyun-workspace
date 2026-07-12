"""发布就绪(发布步的『AI 声明判定 + 组包』一环,**不自动发布**)。

对每条『已批准』笔记:按它挂的素材『来源』自动判 AI 声明要不要勾——
- 全实拍(含 AI 剪辑但没合成新画面)→ 法规无需 AI 标识,判『可发·无需声明』,write 时推进『待发布』(人手发);
- 含 AI 合成素材 且 已勾 AI声明 → 判『可发·已勾』,write 时推进『待发布』;
- 含 AI 合成素材 但 未勾 → 判『⚠️需先勾 AI声明』,留在『已批准』不推进。

红线:**绝不自动发布**(只到『待发布』,不碰 待发布→已发)、**绝不代勾 AI 声明**(只读素材来源事实 + 读人是否已勾)。
这把用户规则落地:实拍内容不必每条手动确认,AI 合成内容一条都跑不掉。
"""
from __future__ import annotations

from . import bitable, config, feishu_io, guard, netpan
from .bitable import NoteFields as NF, NoteStatus as NS, MaterialFields as MF


def _material_index() -> dict:
    """素材 record_id → {来源, 编号, 类型, 链接(耐久指针)}。一次读全,避免逐笔记重复拉素材表。"""
    return {r["record_id"]: {"source": bitable.text(r["fields"].get(MF.SOURCE)),
                             "code": bitable.text(r["fields"].get(MF.CODE)),
                             "type": bitable.text(r["fields"].get(MF.TYPE)),
                             "note": bitable.text(r["fields"].get(MF.NOTE)),
                             "link": bitable.text(r["fields"].get(MF.LINK))}
            for r in feishu_io.list_records(MF.TABLE)}


def note_materials(note_fields: dict, idx: dict) -> list[dict]:
    """一条笔记『用哪些素材』的取用清单(答"待发布不知道用哪张"):
    每条给 编号/类型/来源/段备注 + **可开链接**(网盘指针→用时 mint 分享链接,本地原样)。"""
    out = []
    for rid in bitable.link_record_ids(note_fields.get(NF.LINKED_MATERIALS)):
        m = idx.get(rid)
        if not m:
            continue
        out.append({"code": m["code"], "type": m["type"], "source": m["source"],
                    "note": m["note"], "取用链接": netpan.take_link(m["link"]) if m["link"] else ""})
    return out


def review_approved(brand: str = "巧荷", write: bool = False) -> list[dict]:
    """遍历『已批准』笔记,按素材来源判 AI 声明,给出处置(write=True 才推进『待发布』)。
    返回 [{note_id, title, ai_required, declared, verdict, advanced}]。write 前过 base 红线闸(只写测试库)。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    idx = _material_index()
    out: list[dict] = []
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        if bitable.text(f.get(NF.STATUS)) != NS.APPROVED:
            continue
        mats = note_materials(f, idx)                                # 取素材清单(编号/来源/可开链接)
        sources = [m["source"] for m in mats]
        ai_req = guard.ai_declaration_required(sources)
        declared = bool(f.get(NF.AI_DECLARED))
        entry = {"note_id": r["record_id"], "title": bitable.text(f.get(NF.TITLE)),
                 "ai_required": ai_req, "declared": declared, "advanced": False, "materials": mats}
        try:
            guard.assert_ai_declared(f, ai_required=ai_req)   # 实拍免勾 / 含AI未勾→抛
            entry["verdict"] = "可发·无需AI声明(全实拍)" if not ai_req else "可发·已勾AI声明"
            if write:
                feishu_io.update_record(NF.TABLE, r["record_id"], {NF.STATUS: NS.TO_PUBLISH})
                entry["advanced"] = True
        except guard.GuardError:
            entry["verdict"] = "⚠️需先勾AI声明(含AI合成素材)"
        out.append(entry)
    return out


# ── 聊天/卡片交互的『动作函数』(ADR-0005):按钮点一下的、聊天填字的,都收口到这里 ──
# 服务器 agent 的 webhook 只把"卡片按钮点击/聊天消息"接到这几个函数,不重写逻辑。人点=人审(红线不违)。

def approve(note_id: str, write: bool = False) -> dict:
    """人点『批准』(卡片按钮):草稿待发→已批准。人点=人审(机器绝不自审)。write 才落库。
    返回 {ok, title?, reason?}。之后 review_approved 判 AI声明→待发布。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    for r in feishu_io.list_records(NF.TABLE):
        if r["record_id"] != note_id:
            continue
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        if st != NS.DRAFT_PENDING:
            return {"ok": False, "reason": f"不是草稿待发(当前:{st or '空'}),不批准"}
        if write:
            feishu_io.update_record(NF.TABLE, note_id, {NF.STATUS: NS.APPROVED})
        return {"ok": True, "title": bitable.text(f.get(NF.TITLE)), "advanced": write}
    return {"ok": False, "reason": "没找到该笔记"}


def fill_publish_link(note_key: str, url: str, write: bool = False) -> dict:
    """认领发布链接(聊天里发链接/卡片):按 record_id 或标题/账号片段 匹配**一条**『待发布 或 已发缺链接』的笔记
    → 写发布链接 + 标已发。**多条/零条命中→返候选让人指定,绝不瞎猜**(防写错笔记)。write 才落库。
    返回 {ok, title?, url?, matched, candidates?}。这样回流采集才抓得到该帖数据。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    cands = []
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        if st not in (NS.TO_PUBLISH, NS.PUBLISHED):
            continue
        if st == NS.PUBLISHED and bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            continue                                                     # 已填链接的跳过
        title = bitable.text(f.get(NF.TITLE))
        acc = bitable.text(f.get(NF.ACCOUNT))
        if note_key == r["record_id"] or (note_key and (note_key in title or note_key in acc)):
            cands.append((r["record_id"], title))
    if len(cands) != 1:
        return {"ok": False, "matched": len(cands), "candidates": [t for _, t in cands]}
    rid, title = cands[0]
    if write:
        feishu_io.update_record(NF.TABLE, rid,
                                {NF.PUBLISH_LINK: bitable.url_value(url), NF.STATUS: NS.PUBLISHED})
    return {"ok": True, "title": title, "url": url, "matched": 1, "done": write}
