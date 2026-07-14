"""笔记:**写库的手** + **五道门里的两道**(只写测试库 · 防搬运)。

拆导轨留下的东西。原来 `draft.py` 里那一整套是 harness 在**替模型写稿**:
组 prompt(写作 SOP 抄了第二份)→ 调另一个 LLM 生成 → 判稿子行不行(quality_flags)→
超长了回炉(_fit_to_spec)→ 抄了重写(_rewrite_if_leaked)。全删了。

**因为 agent 自己就是模型。** 它读账号画像(Knowledge)、读 gen_skill 技能(Knowledge)、
读选中素材的画面备注(Observation),**然后自己把稿子写出来**。
harness 不需要"代它去问另一个模型"——那是把驾驶者换成了轨道。

这里只剩:
  · `new()`        —— 建一行笔记(派活占位 / 想法 / 任何状态)。**派什么活是 agent 的判断。**
  · `write_draft()` —— 把 agent 写好的稿落成『草稿待发』(=待人审)。**出口过防搬运门。**
  · `update()`     —— 改字段(状态推进等)。
  · `inflight()`   —— 在途事实(哪些号×模式已经有活/有稿在队列里)。**给 agent 看,它自己去重。**
"""
from __future__ import annotations

from . import accounts, bitable, config, feishu_io, guard
from .bitable import AccountFields as AF, ContentTypeFields as CTF
from .bitable import InspirationFields as IF, KeywordFields as KF
from .bitable import NoteFields as NF, NoteStatus as NS


class DraftPending(RuntimeError):
    """该号该模式已有**待审稿**在队列里,再往上写会把它覆盖掉。宁可拒,也不动运营正在等的东西。"""


def resolve_link(table: str, name_field: str, name: str) -> list[str]:
    """名字 → 该表匹配行的 record_id 列表(账号/内容类型/关键词是 link 字段,飞书要 record_id 不是字符串)。
    按名**服务端过滤**(search_in,不全拉表)。"""
    if not name:
        return []
    return [r["record_id"] for r in feishu_io.search_in(table, name_field, [name])
            if bitable.text(r["fields"].get(name_field)).strip() == name]


class SkillMissing(RuntimeError):
    """模式声明的 gen_skill 装不上 —— **防搬运门会瞎**,必须炸,绝不静默放行。"""


def _gen_skill_of(account: str, content_type: str, brand: str = "巧荷") -> str:
    """这个号的这个模式,**声明的是哪个 gen_skill** —— 从账号 md 推出来,**不问 agent 要**。"""
    acc = accounts.load(account, brand)
    if acc is None or acc.error:
        return ""
    pb = accounts.resolve_playbook(acc.strategy, playbook_id=content_type, content_type=content_type)
    return accounts.gen_skill_of(pb) if pb else ""


def _leak_sources(account: str, content_type: str, brand: str = "巧荷") -> list[str]:
    """防搬运门要比对的**外来文本全集** —— harness **自己去捞**,一个字都不问 agent 要。

    ★红线不能有一个"取决于被监管者是否诚实"的入口★

    老实现里 harness 自己组 prompt,所以它天然知道喂进去了哪些别人的东西。
    现在 agent 自己读技能、自己翻灵感库 —— **它看过什么,harness 不知道**。
    我第一版让它用 `--gen-skill` 申报自己用了哪个技能……**那道门当场就瞎了**:
    它打错一个字、或者干脆不传,门就不会拿那份技能里的**真实帖**去比 —— 而那正是眼前最好抄的东西。
    被监管者自己填的申报表,不是门。

    所以门自己去把它**够得着的**外来文本全捞回来:
      · 灵感库里所有爆款的**标题 + 正文**(它出稿前多半会去翻)
      · 这个号这个模式**声明的** gen_skill 全文(从账号 md 推,不听它说)—— 里面有该号的真实帖 few-shot

    声明了技能却装不上 → **炸**(SkillMissing)。静默跳过 = 门瞎了还假装在守。
    """
    srcs: list[str] = []
    for r in feishu_io.list_records(IF.TABLE):
        f = r["fields"]
        srcs.append(bitable.text(f.get(IF.TITLE)).strip())
        srcs.append(bitable.text(f.get(IF.BODY)).strip())
    gen_skill = _gen_skill_of(account, content_type, brand)
    if gen_skill:
        p = config.WORKSPACE / "skills" / gen_skill / "SKILL.md"
        if not p.exists():
            raise SkillMissing(
                f"「{account}·{content_type}」声明了 gen_skill=「{gen_skill}」,"
                f"但 skills/{gen_skill}/SKILL.md 不存在(没装上?跑 `bash scripts/install_skills.sh`)。\n"
                f"**不能就这么放行**:防搬运门要拿这份技能里的**真实帖**去比对你的稿 —— "
                f"技能不在,门就是瞎的,你逐字抄了那些真实帖也没人拦得住。")
        srcs.append(p.read_text(encoding="utf-8"))
    return [s for s in srcs if s]


def inflight() -> list[dict]:
    """**在途事实**:还没审完/没发完的笔记(待出文案 / 草稿待发 / 已批准 / 待发布)。

    给 agent 看,让它自己判断"这个号这个模式还要不要再派活"。
    ⚠️ 老实现在 harness 里写死了一条规则:**在途就跳过,不重复派**。规则本身不算错,
    但它是**判断**(积压了要不要催审?这个号是不是该换个模式?)——已交回 agent。
    """
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)
    ct_names = feishu_io.name_map(CTF.TABLE, CTF.NAME)
    out = []
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS,
                                 [NS.NEED_COPY, NS.DRAFT_PENDING, NS.APPROVED, NS.TO_PUBLISH]):
        f = r["fields"]
        out.append({
            "id": r["record_id"],
            "标题": bitable.text(f.get(NF.TITLE)),
            "状态": bitable.text(f.get(NF.STATUS)),
            "账号": bitable.link_names(f.get(NF.ACCOUNT), acc_names),   # search 只回 id → 靠 name_map 还原
            "内容类型": bitable.link_names(f.get(NF.CONTENT_TYPE), ct_names),
            "素材数": len(bitable.link_record_ids(f.get(NF.LINKED_MATERIALS))),
            "质检": bitable.text(f.get(NF.QC)),
            "打开": config.record_url(NF.TABLE, r["record_id"]),
        })
    return out


def get(note_id: str) -> dict:
    """**把一条笔记整个读回来**(含正文)—— 写完之后用它自证。

    ★为什么必须有(2026-07-14 数字生命上班第一天点出来的)★
    纪律是"**每个写操作之后,用只读的命令读回来自证**"。可 CLI 里**没有任何动词能读出笔记正文**
    (`board`/`card` 只给标题)。也就是说,`note.draft` —— **整个系统最重要的那次写** ——
    它**无法按纪律自证**。那条纪律在最关键的地方是**一句空话**。

    它的原话:"今天我没出稿所以没踩到,但只要出稿,第 3 条纪律就是空文。"
    """
    from .bitable import ContentTypeFields as CTF
    from .bitable import KeywordFields as KF
    from .bitable import MaterialFields as MF
    r = feishu_io.get_record(NF.TABLE, note_id)
    if not r:
        return {"错": f"没找到这条笔记:{note_id}"}
    f = r["fields"]
    acc_names = feishu_io.name_map(AF.TABLE, AF.NAME)
    ct_names = feishu_io.name_map(CTF.TABLE, CTF.NAME)
    mat_ids = bitable.link_record_ids(f.get(NF.LINKED_MATERIALS))
    kw_ids = bitable.link_record_ids(f.get(NF.KEYWORDS))
    return {
        "id": note_id,
        "标题": bitable.text(f.get(NF.TITLE)),
        "状态": bitable.text(f.get(NF.STATUS)),
        "账号": bitable.link_names(f.get(NF.ACCOUNT), acc_names),
        "内容类型": bitable.link_names(f.get(NF.CONTENT_TYPE), ct_names),
        "方法论": bitable.text(f.get(NF.PLAYBOOK)),
        "文案草稿": bitable.text(f.get(NF.DRAFT)),      # ★正文★ —— 这就是它读不回来的那个东西
        "质检": bitable.text(f.get(NF.QC)),
        "AI声明": bool(f.get(NF.AI_DECLARED)),          # **人勾的**;你写不了这个字段
        "关联素材": [{"id": i, "编号": bitable.text(
            (feishu_io.get_record(MF.TABLE, i) or {"fields": {}})["fields"].get(MF.CODE))}
            for i in mat_ids],
        "标签·关键词": [bitable.text(
            (feishu_io.get_record(KF.TABLE, i) or {"fields": {}})["fields"].get(KF.KEYWORD))
            for i in kw_ids],
        "发布链接": bitable.text(f.get(NF.PUBLISH_LINK)),
        "点赞": f.get(NF.LIKED), "收藏": f.get(NF.COLLECTED),
        "打开": config.record_url(NF.TABLE, note_id),
    }


def _find_inflight(account: str, content_type: str) -> str:
    """该 (账号, 内容类型) 在途的『待出文案』占位 record_id;无则空。

    **必须用 record_id 比对,不能用 text()**:这里读的是 `search` API 的返回,
    而 search 的 link 字段形态是 `{'link_record_ids': [...]}`——**没有 text**
    (list/get 才有 `[{record_ids, text}]`)。用 text 比对 → 永远读出空串 → 永远找不到在途
    → 每次出稿都新建一行 → 运营待审区堆 5 条同号同模式的重复稿。

    撞上『草稿待发』→ **抛 DraftPending,绝不覆盖**:那是运营正等着审的稿,
    在卡片上看到 A、点进 base 变成 B,任何时候都不叫"复用"。
    """
    acc_ids = set(resolve_link(AF.TABLE, AF.NAME, account))
    ct_ids = set(resolve_link(CTF.TABLE, CTF.NAME, content_type))
    if not acc_ids:
        return ""                      # 号都解析不出来,别乱认在途(宁可新建也不改错行)
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.NEED_COPY, NS.DRAFT_PENDING]):
        f = r["fields"]
        if not (acc_ids & set(bitable.link_record_ids(f.get(NF.ACCOUNT)))
                and (not ct_ids or ct_ids & set(bitable.link_record_ids(f.get(NF.CONTENT_TYPE))))):
            continue
        if str(f.get(NF.STATUS) or "") == NS.DRAFT_PENDING:
            raise DraftPending(
                f"「{account}·{content_type}」已经有一条**待审稿**在队列里"
                f"(《{bitable.text(f.get(NF.TITLE))}》)。再写一条会**把它覆盖掉** —— 运营正等着审它。\n"
                f"出路:① 让人先去 base 把那条审掉(批准/暂缓归档);② 换个号或换个模式承接这个选题。")
        return r["record_id"]
    return ""


def new(account: str, content_type: str, title: str = "", status: str = NS.NEED_COPY) -> str:
    """建一行笔记(派活占位『待出文案』/ 想法储备 / …)。返回 record_id。
    **派不派、派给谁、派什么模式 —— 全是 agent 的判断**,这里只负责写下来。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # 红线:任何 IO 之前
    fields: dict = {NF.STATUS: status, NF.TITLE: title or f"[派活]{account}·{content_type}"}
    if acc_ids := resolve_link(AF.TABLE, AF.NAME, account):
        fields[NF.ACCOUNT] = acc_ids
    if ct_ids := resolve_link(CTF.TABLE, CTF.NAME, content_type):
        fields[NF.CONTENT_TYPE] = ct_ids
    return feishu_io.create_record(NF.TABLE, fields)


def write_draft(account: str, content_type: str, title: str, body: str, *,
                material_ids: list[str] | None = None, keywords: list[str] | None = None,
                playbook: str = "", qc: str = "", note_id: str = "", brand: str = "巧荷") -> dict:
    """把 **agent 自己写的稿** 落成『草稿待发』(=待人审)。返回 {note_id, 动作}。

    ★红线★
      1. 只写测试库(assert_base_allowed,走在任何 IO 之前)
      2. **防搬运门**(assert_no_source_leak):产出不得逐字搬任何外来文本 ≥10 连续实义字符。
         比对源由 `_leak_sources()` **自己去捞**(灵感库全部 + 该模式声明的 gen_skill 真实帖),
         **一个字都不问 agent 要** —— 红线不能取决于被监管者是否诚实。
         抄了 → 拒稿 + 告诉它**抄的是哪一句**。**harness 不代它改稿** —— 让它自己用自己的话重写。
         (老实现会自动"回炉重写一次"。那是 harness 替它改作业:门拒了,它自己都不知道自己抄了。)
      3. **绝不自动发布**:止于『草稿待发』,人审。
      4. **绝不代勾 AI 声明**:这里一个字都不碰 AI声明 字段。

    状态机:该号×模式若有『待出文案』占位 → **推进那一行**(一条内容一行,不新建重复);
    若有『草稿待发』→ **抛 DraftPending**(那是人正在审的稿,不许覆盖)。
    """
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)   # ★红线走在任何 IO 之前★
    draft_text = f"{title}\n\n{body}".strip()
    # ★防搬运:守**最终落库的那一份**,比对源 harness 自己捞(见 _leak_sources 的血泪)★
    guard.assert_no_source_leak(_leak_sources(account, content_type, brand), draft_text)

    fields: dict = {
        NF.TITLE: title[:60],
        NF.DRAFT: draft_text,
        NF.STATUS: NS.DRAFT_PENDING,      # 草稿待发=待人审;绝不越过审核门
        NF.QC: qc,                        # agent 自己看出的问题(它想让运营重点看什么)
    }
    if playbook:
        fields[NF.PLAYBOOK] = playbook
    if acc_ids := resolve_link(AF.TABLE, AF.NAME, account):
        fields[NF.ACCOUNT] = acc_ids
    if ct_ids := resolve_link(CTF.TABLE, CTF.NAME, content_type):
        fields[NF.CONTENT_TYPE] = ct_ids
    if material_ids:
        fields[NF.LINKED_MATERIALS] = material_ids
    if keywords:
        # **关键词回程**(架构.md 第五节那个活标本):base 里一直有这个 link 字段,
        # **可从来没有任何东西往里写过** → 反向链接永远 0 → 关键词库『被引用数』永远 0
        # → 「热词排行」视图排一列空数据。**一个承诺"哪些词热"却结构性答不出来的视图。**
        # 那不是代码 bug,是**世界的回程没接上**。现在由 agent 回填——填的是
        # **文案里真正出现的词**,不是"喂进 prompt 的词"(那两者从来不是一回事)。
        kw_ids = [i for w in keywords for i in resolve_link(KF.TABLE, KF.KEYWORD, w)]
        if kw_ids:
            fields[NF.KEYWORDS] = kw_ids
    target = note_id or _find_inflight(account, content_type)   # 撞上待审稿会抛 DraftPending
    if target:
        feishu_io.update_record(NF.TABLE, target, fields)       # 推进:待出文案 → 草稿待发
        return {"note_id": target, "动作": "推进了在途的『待出文案』"}
    return {"note_id": feishu_io.create_record(NF.TABLE, fields), "动作": "新建"}


def update(note_id: str, fields: dict) -> None:
    """改笔记字段(状态推进、挂素材、填质检…)。过 base 红线门。
    ⚠️ **AI声明 和 发布 由人做** —— agent 写这两个字段会被红线拦(见 guard / publish)。"""
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    if NF.AI_DECLARED in fields:
        raise guard.GuardError(
            "AI声明门:**AI 声明只能人勾**(《AI 生成合成内容标识办法》)。\n"
            "机器代勾 = 合规事故。你能做的:如实把素材『来源=AI生成』登记好,"
            "门会在发布前要求人勾;卡片上会给他 ⚠️ 提示。")
    feishu_io.update_record(NF.TABLE, note_id, fields)


def link_materials(note_id: str, material_ids: list[str]) -> None:
    """给笔记挂素材(『关联素材』link 字段,写 record_id 列表)。**挂哪几张是 agent 的判断。**"""
    update(note_id, {NF.LINKED_MATERIALS: material_ids})
