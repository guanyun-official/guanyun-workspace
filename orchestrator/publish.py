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
from .bitable import AccountFields as AF, NoteFields as NF, NoteStatus as NS, MaterialFields as MF


def _mat_info(r: dict) -> dict:
    f = r["fields"]
    return {"source": bitable.text(f.get(MF.SOURCE)), "code": bitable.text(f.get(MF.CODE)),
            "type": bitable.text(f.get(MF.TYPE)), "note": bitable.text(f.get(MF.NOTE)),
            "link": bitable.text(f.get(MF.LINK))}


def _material_index(record_ids: list | None = None) -> dict:
    """素材 record_id → {来源,编号,类型,备注,链接}。
    **record_ids 给定 = 只按 id 取那几条**(get_record,不全表扫,规模M4:只取笔记真引用的素材);
    None = 全表(小规模/兜底)。"""
    if record_ids is not None:
        idx = {}
        for rid in dict.fromkeys(record_ids):        # 去重保序
            r = feishu_io.get_record(MF.TABLE, rid)
            if r:
                idx[rid] = _mat_info(r)
        return idx
    return {r["record_id"]: _mat_info(r) for r in feishu_io.list_records(MF.TABLE)}


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
    approved = feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.APPROVED])   # 已批准 服务端过滤
    linked = [rid for r in approved
              for rid in bitable.link_record_ids(r["fields"].get(NF.LINKED_MATERIALS))]
    idx = _material_index(linked)   # 只取被批准笔记引用的素材(规模M4,不全拉素材表)
    # **控量门装在这儿**(2026-07-14 运营视角实测):`guard.assert_publish_quota` 造好了却是**死码**——
    # 全仓没有任何一处调用它,cockpit 的注释甚至自认"曾是死码,这里给人看",只在卡片上事后预警。
    # 后果:系统可以无限往『待发布』堆稿,运营卡片上真出现「排队待发 4 条 = 占用 4/3」——**已经超了**。
    # 红线名不副实=门造好了没装在门框上。这里是**系统自己**推进状态的唯一入口(人在 base 手动改状态
    # 拦不住,那是人的自由),所以门必须装在这:超额就不推进,把稿留在『已批准』,并告诉人为什么。
    load = _account_load()   # 按**账号 record_id** 计额度(record_id 才是真身份;查名字要全表拉账号表)
    out: list[dict] = []
    for r in approved:
        f = r["fields"]
        mats = note_materials(f, idx)                                # 取素材清单(编号/来源/可开链接)
        sources = [m["source"] for m in mats]
        ai_req = guard.ai_declaration_required(sources)
        declared = bool(f.get(NF.AI_DECLARED))
        acc_ids = bitable.link_record_ids(f.get(NF.ACCOUNT))
        used = max((load.get(a, 0) for a in acc_ids), default=0)
        entry = {"note_id": r["record_id"], "title": bitable.text(f.get(NF.TITLE)),
                 "account_ids": acc_ids,       # 显示名由调用方(publish_ready/卡片)按需还原,这里不查表
                 "ai_required": ai_req, "declared": declared, "advanced": False, "materials": mats}
        try:
            # 三道门,顺序是"先看能不能发,再看该不该发":
            guard.assert_has_material(len(mats), bitable.text(f.get(NF.TITLE)))  # 零素材=物理发不了
            guard.assert_ai_declared(f, ai_required=ai_req)   # 实拍免勾 / 含AI未勾→抛
            guard.assert_publish_quota(used)                  # 控量红线:该号今日额度已满→不推进
            entry["verdict"] = "可发·无需AI声明(全实拍)" if not ai_req else "可发·已勾AI声明"
            if write:
                feishu_io.update_record(NF.TABLE, r["record_id"], {NF.STATUS: NS.TO_PUBLISH})
                entry["advanced"] = True
                for a in acc_ids:
                    load[a] = load.get(a, 0) + 1              # 本轮刚占的额度也算上(别一次批爆)
        except guard.GuardError as e:
            entry["verdict"] = f"⚠️{e}"                       # AI声明未勾 / 控量已满——都说清是哪道门
        out.append(entry)
    return out


def _account_load() -> dict[str, int]:
    """每个账号(**按 record_id**)当前已占的今日额度 = 今日已发 + 已在『待发布』排队(都占额度,防超发)。

    按 record_id 不按名字:record_id 是 link 字段里现成的真身份,**查名字得全表拉账号表**(规模基准:
    review_approved 必须零全表扫)。名字只是给人看的,由调用方按需还原。
    冷热分离:只拉今日已发(服务端日期窗)+ 待发布(在途,小),绝不整拉笔记表。"""
    from datetime import date
    day0 = str(bitable.day_start_ms(date.today()))
    load: dict[str, int] = {}
    rows = feishu_io.search_records(NF.TABLE, [
        {"field_name": NF.STATUS, "operator": "is", "value": [NS.PUBLISHED]},
        {"field_name": NF.PUBLISHED_AT, "operator": "isGreater", "value": ["ExactDate", day0]}],
        conjunction="and")
    rows += feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.TO_PUBLISH])
    for r in rows:
        for a in bitable.link_record_ids(r["fields"].get(NF.ACCOUNT)):
            load[a] = load.get(a, 0) + 1
    return load


# ── 聊天/卡片交互的『动作函数』(ADR-0005):按钮点一下的、聊天填字的,都收口到这里 ──
# 服务器 agent 的 webhook 只把"卡片按钮点击/聊天消息"接到这几个函数,不重写逻辑。人点=人审(红线不违)。

def approve(note_id: str, write: bool = False) -> dict:
    """人点『批准』(卡片按钮):草稿待发→已批准。人点=人审(机器绝不自审)。write 才落库。
    返回 {ok, title?, reason?}。之后 review_approved 判 AI声明→待发布。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    r = feishu_io.get_record(NF.TABLE, note_id)   # 规模M4:按id取单条,不全扫笔记表
    if not r:
        return {"ok": False, "reason": "没找到该笔记"}
    f = r["fields"]
    st = bitable.text(f.get(NF.STATUS)).strip()
    if st != NS.DRAFT_PENDING:
        return {"ok": False, "reason": f"不是草稿待发(当前:{st or '空'}),不批准"}
    if write:
        feishu_io.update_record(NF.TABLE, note_id, {NF.STATUS: NS.APPROVED})
    return {"ok": True, "title": bitable.text(f.get(NF.TITLE)), "advanced": write}


def fill_publish_link(note_key: str, url: str, write: bool = False) -> dict:
    """认领发布链接(聊天里发链接/卡片):按 record_id 或标题/账号片段 匹配**一条**『待发布 或 已发缺链接』的笔记
    → 写发布链接 + 标已发。**多条/零条命中→返候选让人指定,绝不瞎猜**(防写错笔记)。write 才落库。
    返回 {ok, title?, url?, matched, candidates?}。这样回流采集才抓得到该帖数据。"""
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    from .bitable import AccountFields as AF
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)    # 账号是 link 字段:search 只回 id,还原成名才能按账号名匹配
    cands = []
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.TO_PUBLISH, NS.PUBLISHED]):   # 待发布/已发 过滤(规模M2)
        f = r["fields"]
        st = bitable.text(f.get(NF.STATUS)).strip()
        if st not in (NS.TO_PUBLISH, NS.PUBLISHED):
            continue
        if st == NS.PUBLISHED and bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            continue                                                     # 已填链接的跳过
        title = bitable.text(f.get(NF.TITLE))
        acc = bitable.link_names(f.get(NF.ACCOUNT), acc_names)   # link 字段:search 回 id→还原名再匹配
        if note_key == r["record_id"] or (note_key and (note_key in title or note_key in acc)):
            cands.append((r["record_id"], title))
    if len(cands) != 1:
        return {"ok": False, "matched": len(cands), "candidates": [t for _, t in cands]}
    rid, title = cands[0]
    if write:
        import time
        # 认领链接=人确认此刻已发→同时补写『实际发布日』:控量『今日已发』/回流采集/效果归因都靠它,
        # 此前只 sim 写、真发从不写→字段常年空、今日已发计数恒为 0(ADR-0009 收尾修)
        feishu_io.update_record(NF.TABLE, rid,
                                {NF.PUBLISH_LINK: bitable.url_value(url), NF.STATUS: NS.PUBLISHED,
                                 NF.PUBLISHED_AT: int(time.time() * 1000)})
    return {"ok": True, "title": title, "url": url, "matched": 1, "done": write}
