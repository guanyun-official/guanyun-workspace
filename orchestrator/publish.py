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


def review_approved(brand: str = "观云", write: bool = False) -> list[dict]:
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
