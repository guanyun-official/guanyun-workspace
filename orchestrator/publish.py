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
    # ★『链接』是 url 字段:`{"link": "https://pan.baidu.com/s/…?pwd=", "text": "2026-07-02 175609.heic"}`★
    # `bitable.text()` 对 dict 是 **text 优先** → 拿回来的是**文件名,不是能点的链接**。
    # 而它一路喂进 `take_link()`:文件名不以 `baidupan:` 开头 → **原样返回** → 运营卡片上
    # 「🖼 ST-260702-004 → 2026-07-02 175621.heic」。他点不开,也不知道在网盘哪个目录。
    # **能开的链接一直躺在库里,只是被 text 挡住了。**(又一次「算了却没给人看」。)
    # 所以这里给 take_link 的是**耐久指针**(它本来就是为这个造的:用时 mint,人拿不到过期链),
    # 库里那条 href 只当兜底。
    return {"source": bitable.text(f.get(MF.SOURCE)), "code": bitable.text(f.get(MF.CODE)),
            "type": bitable.text(f.get(MF.TYPE)), "note": bitable.text(f.get(MF.NOTE)),
            "link": bitable.text(f.get(MF.REL_PATH)) or bitable.url(f.get(MF.LINK))}


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


# ★这里**故意没有** `approve()`★
# 审批是**人在 base 里做的**(人和 agent 看同一张表,不搞两套真源)。
# 留一个 `approve()` 函数 = 给红线留了个后门:CLI 里没这个动词,可 `import` 就能调。
# (2026-07-14 架构审查抓到。)

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
        # 此前只 sim 写、真发从不写→字段常年空、今日已发计数恒为 0(「上量前重构」 收尾修)
        feishu_io.update_record(NF.TABLE, rid,
                                {NF.PUBLISH_LINK: bitable.url_value(url), NF.STATUS: NS.PUBLISHED,
                                 NF.PUBLISHED_AT: int(time.time() * 1000)})
    return {"ok": True, "title": title, "url": url, "matched": 1, "done": write}


def stamp_published_at(write: bool = False) -> list[dict]:
    """**自愈:给『已发但没有实际发布日』的稿补上发布日**(控量红线的命根子)。

    2026-07-14 走运营流程真跑发现的事故:运营在 base 里**只有两个手柄**——改『状态』、填『发布链接』。
    而『实际发布日』**他做不了**(base 里没人告诉他要填,也没有自动化)。于是他照着卡片发完一条:
        状态=已发 ✓   发布链接=填了 ✓   实际发布日=**空**
        → 控量『今日已发』算成 0(他明明发了一条)
        → **单号日发上限形同虚设,可以无限发** —— 红线破了。
    而全仓唯一会写这个字段的 `fill_publish_link()` **生产零调用**(它是卡片按钮的动作函数,webhook 未接)
    —— 运营根本够不着它。卡片上那句"发完把链接发我认领"里的**那个"我"不存在**。

    **系统不该依赖人去做一件他做不到的事。** 状态翻成『已发』本身就是信号:他说"我发了"。
    所以系统自己把日期补上(补的是**发现时**的时间;运营当天发当天改状态,这就是对的。
    若他补录旧帖,日期会偏——那种情况少,且卡片会把补过的列出来让他核)。
    **入口只有一个:人敲 `publish.stamp --write`**(或运营自己在 base 里填『实际发布日』)。幂等。
    ⚠️ 没有任何东西在自动跑它 —— 今日卡片上也绝不承诺『系统自动补』(那句假话已删)。
    """
    import time
    if write:
        guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:只写测试库
    out: list[dict] = []
    now = int(time.time() * 1000)
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.PUBLISHED]):
        f = r["fields"]
        if f.get(NF.PUBLISHED_AT):
            continue                                          # 已有日期,不动(幂等)
        if not bitable.text(f.get(NF.PUBLISH_LINK)).strip():
            continue                                          # 连链接都没有 → 不是"刚发完",别瞎补
        out.append({"note_id": r["record_id"], "title": bitable.text(f.get(NF.TITLE)),
                    "stamped": write})
        if write:
            feishu_io.update_record(NF.TABLE, r["record_id"], {NF.PUBLISHED_AT: now})
    return out
