"""轻调度器(#8):读账号声明,按 cadence 算今天每号该出哪些模式的活 → 派到『待出文案』占位待填。

**绝不自动发布、绝不代勾 AI 声明**——只把活派到『待出文案』,后续 draft_one 出稿→草稿待发→人审人发。
一号多模式:每号每个 playbook 各派一条活。已有『待出文案/草稿待发』的号×模式跳过(不重复堆活)。

sourcing 决定这活『素材怎么来』(不冲突,只是第一步不同,下游出稿→审→发→回流一致):
- shoot_then_drip:从已拍素材池挑着出稿(ootd/图文)
- curated:等新品/文物到位再策展出稿(官号)
- trend_imitate:先跑爆款雷达找对标爆款→反推要拍什么→提醒拍→再出稿(爆款驱动)
"""
from __future__ import annotations

from . import accounts, bitable, config, feishu_io, guard
from .bitable import NoteFields as NF, NoteStatus as NS

# sourcing → 备料动作提示(trend_imitate 复用已装的爆款拆解技能,不另造)
SOURCING_HINT = {
    "shoot_then_drip": "从已拍素材池挑素材直接出稿",
    "curated": "等新品/文物到位再策展出稿",
    "trend_imitate": "先跑爆款雷达(explosive-teardown / qiaohe-amateur-miner)找对标爆款→反推要拍什么→提醒拍→再出稿",
}


def daily_assignments(brand: str = "观云") -> list[dict]:
    """今天派活清单:每号(cadence.posts_per_day≥1)× 其每个模式 → 一条活。纯计算不写库。
    返回 [{account, content_type, gen_skill, material_needs, sourcing, sourcing_hint}]。"""
    out: list[dict] = []
    for name, acc in sorted(accounts.load_all(brand).items()):
        if acc.error:
            continue
        cad = acc.strategy.get("cadence") or {}
        if cad.get("posts_per_day", 1) < 1:
            continue                                  # 暂停/不发的号跳过
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


def pending_ideas(brand: str = "观云") -> list[dict]:
    """灵感库里『还没转化为笔记』的爆款灵感(=爆款模仿 trend_imitate 的原料):标题+可借鉴优点+爆款源链接。
    连上需求/灵感→出稿的前置一环:员工采集的爆款进灵感库,这里捞出未转化的待出稿(出稿用 --title-seed 承接)。"""
    out = []
    for r in feishu_io.list_records("灵感库"):
        f = r["fields"]
        if bitable.text(f.get("转化为笔记")).strip():
            continue                                          # 已转化→跳过
        title = bitable.text(f.get("标题")).strip()
        if not title or title == "（无标题）":
            continue                                          # 无效灵感跳过
        out.append({"record_id": r["record_id"], "标题": title,
                    "可借鉴": bitable.text(f.get("优点")).strip(),
                    "爆款源": bitable.text(f.get("链接")).strip()})
    return out


def mark_idea_converted(idea_id: str, note_id: str) -> None:
    """灵感转化为笔记后回填灵感库,闭合 trend_imitate 环(灵感→出稿→回填)。
    『转化为笔记』是 **link 字段**,写 record_id 列表不是字符串——实测真跑才暴露的坑,codify 防复发。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    feishu_io.update_record("灵感库", idea_id, {"转化为笔记": [note_id]})


def _open_slots() -> set:
    """已有『待出文案/草稿待发』在途的 (账号, 内容类型),用于去重不重复派活。"""
    open_status = {NS.NEED_COPY, NS.DRAFT_PENDING}
    slots = set()
    for r in feishu_io.list_records(NF.TABLE):
        f = r["fields"]
        if bitable.text(f.get(NF.STATUS)) in open_status:
            slots.add((bitable.text(f.get(NF.ACCOUNT)), bitable.text(f.get(NF.CONTENT_TYPE))))
    return slots


def dispatch(brand: str = "观云", write: bool = False) -> list[dict]:
    """派活:今天每号每模式的活落成『待出文案』占位(write=True 才写测试库)。
    已在途的号×模式跳过(去重)。绝不自动发布、绝不代勾 AI 声明。返回本次实际派的活(含 note_id/skipped)。"""
    assigns = daily_assignments(brand)
    if not write:
        return assigns
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:只写测试库
    from .draft import _resolve_link
    from .bitable import AccountFields as AF, ContentTypeFields as CTF
    in_flight = _open_slots()
    for a in assigns:
        if (a["account"], a["content_type"]) in in_flight:
            a["skipped"] = "已在途"                     # 去重:不重复堆活
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
