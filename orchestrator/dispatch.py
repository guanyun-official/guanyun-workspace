"""轻调度器(#8):读账号声明,按 cadence 算今天每号该出哪些模式的活 → 派到『待出文案』占位待填。

**绝不自动发布、绝不代勾 AI 声明**——只把活派到『待出文案』,后续 draft_one 出稿→草稿待发→人审人发。
一号多模式:每号每个 playbook 各派一条活。已有『待出文案/草稿待发』的号×模式跳过(不重复堆活)。

sourcing 决定这活『素材怎么来』(不冲突,只是第一步不同,下游出稿→审→发→回流一致):
- shoot_then_drip:从已拍素材池挑着出稿(ootd/图文)
- curated:等新品/文物到位再策展出稿(官号)
- trend_imitate:先跑爆款雷达找对标爆款→反推要拍什么→提醒拍→再出稿(爆款驱动)
"""
from __future__ import annotations

from . import accounts, bitable, config, feishu_io, guard, lock
from .bitable import NoteFields as NF, NoteStatus as NS, AccountFields as AF, AutoSched, InspirationFields as IF

# sourcing → 备料动作提示(trend_imitate 复用已装的爆款拆解技能,不另造)
SOURCING_HINT = {
    "shoot_then_drip": "从已拍素材池挑素材直接出稿",
    "curated": "等新品/文物到位再策展出稿",
    "trend_imitate": "先跑爆款雷达(explosive-teardown / qiaohe-amateur-miner)找对标爆款→反推要拍什么→提醒拍→再出稿",
    "trend_insert": "蹭热点插队:抓当天爆款→反推选题→急稿(注:插队优先级排序未实现,见 ADR-0008;当前与常规稿同池)",
}


def _should_dispatch(sched: str, posts_per_day) -> bool:
    """base「自动排产」+ md cadence 决定今天派不派:
    暂停=停(覆盖md);开启=强制派(覆盖md,即使 md<1);跟随workspace/空=按 md(posts_per_day≥1)。"""
    if sched == AutoSched.PAUSED:
        return False
    if sched == AutoSched.FORCE_ON:
        return True
    return (posts_per_day if posts_per_day is not None else 1) >= 1


def daily_assignments(brand: str = "巧荷") -> list[dict]:
    """今天派活清单:每号(base「自动排产」≠暂停 且 cadence.posts_per_day≥1)× 其每个模式 → 一条活。
    读 base 账号表「自动排产」运营开关(不写库)。返回 [{account, content_type, gen_skill, material_needs, sourcing, sourcing_hint}]。"""
    # base 侧运营开关(唯一真相):读账号表「自动排产」——团队在 base 点,谁接手(dedicated agent)都读得到
    sched = {
        bitable.text(r["fields"].get(AF.NAME)).strip(): bitable.text(r["fields"].get(AutoSched.FIELD)).strip()
        for r in feishu_io.list_records(AF.TABLE)
    }
    out: list[dict] = []
    for name, acc in sorted(accounts.load_all(brand).items()):
        if acc.error:
            continue
        cad = acc.strategy.get("cadence") or {}
        if not _should_dispatch(sched.get(name, AutoSched.FOLLOW_WS), cad.get("posts_per_day", 1)):
            continue                                  # 暂停=停 / 开启=强制派 / 跟随workspace=按 md cadence
        sourcing = acc.strategy.get("sourcing", "shoot_then_drip")
        for pb in acc.playbooks():
            out.append({
                "account": name,
                "content_type": pb.get("content_type") or pb.get("id") or "",
                "gen_skill": accounts.gen_skill_of(pb),
                "material_needs": pb.get("material_needs") or [],
                "sourcing": sourcing,
                "sourcing_hint": SOURCING_HINT.get(sourcing, sourcing),
            })
    return out


def pending_ideas(brand: str = "巧荷") -> list[dict]:
    """灵感库里『还没转化为笔记』的爆款灵感(=爆款模仿 trend_imitate 的原料):标题+可借鉴优点+爆款源链接。
    连上需求/灵感→出稿的前置一环:员工采集的爆款进灵感库,这里捞出未转化的待出稿(出稿用 --title-seed 承接)。"""
    out = []
    for r in feishu_io.list_records(IF.TABLE):
        f = r["fields"]
        if bitable.text(f.get(IF.CONVERTED)).strip():
            continue                                          # 已转化→跳过
        title = bitable.text(f.get(IF.TITLE)).strip()
        if not title or title == "（无标题）":
            continue                                          # 无效灵感跳过
        out.append({"record_id": r["record_id"], "标题": title,
                    "可借鉴": bitable.text(f.get(IF.MERITS)).strip(),
                    "文案": bitable.text(f.get(IF.BODY)).strip(),   # 防搬运源正文:出稿传 draft_one(source_text=)
                    "爆款源": bitable.text(f.get(IF.LINK)).strip()})
    return out


def run_day(brand: str = "巧荷", llm_mode: str = "stub", write: bool = False) -> list[dict]:
    """跑一天(人只管头尾的『中间』一条龙):排期(daily_assignments,尊重 base 自动排产)
    → 每条活 出文案(generate_draft)+ 挂素材(create_draft_note 内含 select_materials)→ 推进『草稿待发』。
    **一条命令产出"今天每号要发什么(草稿+素材,待人审)"**,人打开 base 就能审。
    - write=False 干跑:只算今天的活,不写库;write=True 落『草稿待发』。
    - llm_mode=real 出真文案(≈2元/条,走 llm.run_prompt=画像+skill few-shot+配方);stub 零成本占位验证接线。
    红线不变:只推到『草稿待发』,**绝不自动发布、绝不代勾 AI 声明**。
    注:run_day 是**批量从零出稿**(画像+skill 原创),不传 source_text,故防搬运门对它 no-op(本就无对标源可搬)。
    **蹭爆款(trend_imitate)走 draft_one --source-text 传灵感库正文**,防搬运门才比对得到爆款正文——不要用 run_day 蹭稿。"""
    from . import draft
    assigns = daily_assignments(brand)
    if not write:                                        # 干跑:不写库,不加锁
        return [{"account": a["account"], "content_type": a["content_type"],
                 "gen_skill": a["gen_skill"], "material_needs": a["material_needs"],
                 "status": "(干跑)"} for a in assigns]
    out: list[dict] = []
    with lock.write_lock():                              # 并发锁(ADR-0009):防两个自动化写进程并发重复派活
        for a in assigns:
            entry = {"account": a["account"], "content_type": a["content_type"],
                     "gen_skill": a["gen_skill"], "material_needs": a["material_needs"]}
            try:
                r = draft.generate_draft(a["account"], brand, llm_mode=llm_mode,
                                         content_type=a["content_type"])
                rid = draft.create_draft_note(r)   # upsert 待出文案→草稿待发 + 挂货对板素材
                entry.update(note_id=rid, title=r["title"], status=NS.DRAFT_PENDING)
                if r.get("quality_flags"):
                    entry["质检"] = r["quality_flags"]   # #42 出稿即评:问题顶给人重点看(不阻塞)
            except Exception as e:  # noqa: BLE001  单号失败不拖垮整天,记下继续
                entry.update(status="✗失败", error=str(e)[:120])
            out.append(entry)
    return out


def mark_idea_converted(idea_id: str, note_id: str) -> None:
    """灵感转化为笔记后回填灵感库,闭合 trend_imitate 环(灵感→出稿→回填)。
    『转化为笔记』是 **link 字段**,写 record_id 列表不是字符串——实测真跑才暴露的坑,codify 防复发。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    feishu_io.update_record(IF.TABLE, idea_id, {IF.CONVERTED: [note_id]})


def runway_alerts(brand: str = "巧荷") -> list[dict]:
    """素材余量催拍(消费账号 md 的 runway_alert_days):可用素材 ÷ 日发量 ≈ 剩余天数;
    < 阈值 → 催拍该号补拍。可用素材走 draft.select_materials(赛道过滤)。粗估提醒用,非精确排产。"""
    from .draft import select_materials, _resolve_link
    out = []
    for name, acc in sorted(accounts.load_all(brand).items()):
        if acc.error:
            continue
        thr = acc.strategy.get("runway_alert_days")
        if not thr:
            continue
        ppd = max(1, (acc.strategy.get("cadence") or {}).get("posts_per_day", 1))
        needs = sorted({t for pb in acc.playbooks() for t in (pb.get("material_needs") or [])})
        acc_ids = _resolve_link(AF.TABLE, AF.NAME, name)
        avail = len(select_materials(needs, acc_ids[0] if acc_ids else "", limit=9999))
        runway = round(avail / ppd, 1)
        if runway < thr:
            out.append({"account": name, "avail": avail, "runway_days": runway, "threshold": thr})
    return out


def _open_slots() -> set:
    """已有『待出文案/草稿待发』在途的 (账号, 内容类型),用于去重不重复派活。
    状态∈开态 服务端过滤(规模M2,不全拉笔记表);search 已保证状态。
    **账号/内容类型是 link 字段——search 只回 id 无 text**,必须靠 name_map 还原成名再比对,
    否则去重键全变 ('','') → daily_assignments 的真名永不命中 → 每天重复派活(dogfood 实测坑)。"""
    from .bitable import ContentTypeFields as CTF
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)
    ct_names = feishu_io.name_map(CTF.TABLE, CTF.NAME)
    slots = set()
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.NEED_COPY, NS.DRAFT_PENDING]):
        f = r["fields"]
        slots.add((bitable.link_names(f.get(NF.ACCOUNT), acc_names),
                   bitable.link_names(f.get(NF.CONTENT_TYPE), ct_names)))
    return slots


def dispatch(brand: str = "巧荷", write: bool = False) -> list[dict]:
    """派活:今天每号每模式的活落成『待出文案』占位(write=True 才写测试库)。
    已在途的号×模式跳过(去重)。绝不自动发布、绝不代勾 AI 声明。返回本次实际派的活(含 note_id/skipped)。"""
    assigns = daily_assignments(brand)
    if not write:
        return assigns
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    from .draft import _resolve_link
    from .bitable import AccountFields as AF, ContentTypeFields as CTF
    with lock.write_lock():                            # 并发锁(ADR-0009):在途去重是读-改-写 TOCTOU,加锁防并发重复派活
        in_flight = _open_slots()
        for a in assigns:
            if (a["account"], a["content_type"]) in in_flight:
                a["skipped"] = "已在途"                 # 去重:不重复堆活
                continue
            fields = {NF.STATUS: NS.NEED_COPY, NF.TITLE: f"[派活]{a['account']}·{a['content_type']}"}
            acc_ids = _resolve_link(AF.TABLE, AF.NAME, a["account"])
            ct_ids = _resolve_link(CTF.TABLE, CTF.NAME, a["content_type"])
            if acc_ids:
                fields[NF.ACCOUNT] = acc_ids
            if ct_ids:
                fields[NF.CONTENT_TYPE] = ct_ids
            a["note_id"] = feishu_io.create_record(NF.TABLE, fields)  # 状态=待出文案,等 draft_one 出稿
    return assigns
