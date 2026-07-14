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
        "文案草稿": bitable.text(f.get(NF.DRAFT)),        # ★正文★ —— 运营改的、最终发的就是它
        "原始生成稿": bitable.text(f.get(NF.ORIGINAL)),    # agent 出稿那一刻的原文
        # **人改过吗** —— 两者不一样,就说明运营动过手。**他改的每一处,都是技能该怎么改的答案。**
        "人改过": (bitable.text(f.get(NF.ORIGINAL)).strip() != bitable.text(f.get(NF.DRAFT)).strip()
                   and bool(bitable.text(f.get(NF.ORIGINAL)).strip())),
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
            # ★门的本意★:**不许覆盖人正在审的那一行**。
            # 它**不是**"每号只准排一条待审稿"(队列该多深是 agent 的判断,不是我的规则)。
            #
            # ⚠️ 老实现给的两条出路**都不成立**(2026-07-14 数字生命当场指出来):
            #   ①"让人先审掉" —— **它不能替人审**,这条路它走不了
            #   ②"换个号"     —— **选题不该换号**,那是让它为了绕门去做错的事
            # 而**真正的出路它没说**:`--note-id` 指定另起/推进哪一行。
            # **拦住 ≠ 说清楚。给不出真出路的门,等于把人堵死在墙里。**
            raise DraftPending(
                f"「{account}·{content_type}」已经有一条**待审稿**在队列里"
                f"(《{bitable.text(f.get(NF.TITLE))}》,id={r['record_id']})。\n"
                f"直接写会**把它覆盖掉** —— 运营在卡片上看到 A,点进 base 变成 B。**那不叫复用。**\n\n"
                f"**这道门拦的只是『覆盖』,不是『再排一条』** —— 队列该多深是你的判断。出路:\n"
                f"  ① **想再排一条**(不覆盖那条):先 `note.new --account {account} "
                f"--content-type {content_type}` 建一行,拿到新 id,再 `note.draft --note-id <新id> …`\n"
                f"  ② **想改那条**(比如运营退回了、你要重写):`note.draft --note-id {r['record_id']} …`\n"
                f"  ③ 觉得队列已经够深、不该再堆 —— 那就别写。**那也是你的判断。**")
        return r["record_id"]
    return ""


def _assert_materials_exist(material_ids: list[str]) -> None:
    """挂上去的素材 id **必须真的存在** —— 不存在就当场拒,绝不静默挂个空的。

    ★这是零素材门的地基,而它曾经是漏的★(2026-07-14 数字生命上班第二天撞到)

    它给 `note.draft --materials` 传了两个**自己编的** record id(只查了一个,另两个想当然)。
    **飞书照单全收,一声不吭。** 真跑复现:连 `recFAKE111111` 这种明显是假的都能挂上去。

    后果不是"少了两张图",是**base 在骗人**:
      · 笔记的『关联素材』字段里**明晃晃挂着 3 条**,运营在 base 里看到"有素材"
      · 点开一看 —— **空的**。那两条 record 根本不存在
      · 而零素材门数的是"**能解析出来的**"素材数 —— 它以为有 1 条,于是放行
      · **一条实际上发不出去的稿,就这么进了『待发布』**

    "静默接受不存在的引用"和它昨天抓到的"静默吞掉不认识的键",是**同一族病**:
    **静默 = 往真库灌残数据,而且没有任何人会发现。**
    (它的原话:"响的能自己发现,静默的会把脏数据写进真库 —— 静默那个毒得多。")
    """
    from .bitable import MaterialFields as MF
    missing = [i for i in material_ids if not feishu_io.get_record(MF.TABLE, i)]
    if missing:
        raise ValueError(
            f"这些素材 record_id **在素材表里根本不存在**:{missing}\n"
            f"飞书会照单收下 —— 笔记在 base 里看起来「挂着素材」,点开却是空的。**人面上就成了谎话。**\n"
            f"出路:用 `material.list` 把真的 id 查出来(别凭记忆编),再挂。")


def new(account: str, content_type: str, title: str = "", status: str = NS.NEED_COPY) -> str:
    """建一行笔记(派活占位『待出文案』/ 想法储备 / …)。返回 record_id。
    **派不派、派给谁、派什么模式 —— 全是 agent 的判断**,这里只负责写下来。

    ⚠️ **状态同样过白名单** —— 否则它能直接**建一行『已发』**,绕开整条状态机和三道门。"""
    _assert_status_allowed(status)
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
        NF.DRAFT: draft_text,             # 运营改的、最终发的就是它
        NF.ORIGINAL: draft_text,          # ★同时留一份原文,之后不动★
        # 两者的差 = **人改了什么** = 这个系统里最值钱的信号(直接告诉技能该怎么改)。
        # 老实现只有一个字段:人一改,原文就没了;agent 一重出稿,人的修改就没了。**信号一落地就被抹掉。**
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
        _assert_materials_exist(material_ids)   # ★不存在的 id 当场拒,绝不静默挂个空的★
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


# ★agent 能写的状态,**焊死成白名单**★(2026-07-14 架构审查真跑复现的红线洞)
#
# 老实现只拦 AI声明。真跑一试:
#     note.update <id> --set 状态=已批准   → **放行**(它自己批自己的稿)
#     note.update <id> --set 状态=待发布   → **放行**(绕开零素材/AI声明/控量三道门)
#     note.update <id> --set 状态=已发     → **放行**(「绝不自动发布」当场变成空文)
#
# 而 `cli.py` 开头白纸黑字写着"**故意没有** approve / publish 动词" ——
# **可 `--set 状态=` 就是那两个动词。** 门造好了,没装在门框上。
#
# 这几个状态**不归 agent**:
#   · 已批准 —— **人在 base 里审**(人和 agent 看同一张表,不搞两套真源)
#   · 待发布 —— 只许走 `publish.advance`(那里有零素材/AI声明/控量三道门)
#   · 已发   —— **人的动作**(红线:绝不自动发布)
#   · 已回流 —— 只许走 `note.metrics`(真采到数才推;没数就推 = 假装采过)
_AGENT_MAY_SET = frozenset({NS.IDEA, NS.NEED_SHOOT, NS.NEED_COPY, NS.DRAFT_PENDING, NS.ON_HOLD})
_WHY_NOT = {
    NS.APPROVED: "『已批准』是**人在 base 里审**的结果 —— 给你这个动作,人审就成了摆设。",
    NS.TO_PUBLISH: "『待发布』只许走 `publish.advance` —— 那里有零素材/AI声明/控量三道门。"
                   "直接改状态 = 绕开三道红线。",
    NS.PUBLISHED: "**绝不自动发布**(红线)。发布是人的动作,系统止于『待发布』。",
    NS.LOOPED_BACK: "『已回流』只许走 `note.metrics`(真采到数才推)—— 没数就推,等于假装采过。",
}


def _assert_status_allowed(status: str) -> None:
    """★状态门★:agent 写不了『已批准』『待发布』『已发』『已回流』。"""
    st = str(status or "").strip()
    if st and st not in _AGENT_MAY_SET:
        raise guard.GuardError(
            f"状态门:**你写不了『{st}』。**\n{_WHY_NOT.get(st, '这个状态不归 agent。')}\n"
            f"你能写的状态只有:{'、'.join(sorted(_AGENT_MAY_SET))}")


def update(note_id: str, fields: dict) -> None:
    """改笔记字段(挂素材、填质检、退回…)。**过两道红线门。**

    ★门一:AI 声明只能人勾★(《AI 生成合成内容标识办法》)
    ★门二:状态白名单★ —— 『已批准』『待发布』『已发』『已回流』**你写不了**
    """
    if NF.AI_DECLARED in fields:
        raise guard.GuardError(
            "AI声明门:**AI 声明只能人勾**(《AI 生成合成内容标识办法》)。\n"
            "机器代勾 = 合规事故。你能做的:如实把素材『来源=AI生成』登记好,"
            "门会在发布前要求人勾;卡片上会给他 ⚠️ 提示。")
    _assert_status_allowed(fields.get(NF.STATUS, ""))
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    feishu_io.update_record(NF.TABLE, note_id, fields)


def write_metrics(note_id: str, liked=None, collected=None, comments=None, shared=None) -> dict:
    """**把你抓到的回流数写回世界** + 推状态机(已发 → 已回流)。

    ★harness 在回流这件事上只干这一件事★

    「去小红书把数抓回来」是**你的操作**(你有 `xhs-extract-master` / `xhs-collector` 两个技能);
    「这个数可不可信」是**你的判断**。harness 不替你爬,也不替你信。

    老实现有个 `collect` 动词:harness 自己去爬、自己决定用哪个采集器、**抓到什么就写什么**。
    那是个小导轨 —— 而且它踩过雷:采集器把**读不到的赞数静默变成 0**,
    0 是个合法值,会被写进库、被周报当真数据算"哪类内容更有效"。

    **所以:没抓到的,就别传。** 不传的字段**一个字都不写**(不是写 0)。
    真跑实证:一条笔记 `收藏 1495 / 评论 35`,而**赞抓不到** —— 那就只写收藏和评论。
    **「没抓到」和「真的是 0」是两件完全不同的事。**

    只要有一个数写进去了,状态就从『已发』推到『已回流』(状态机闭环)。
    """
    vals = {k: v for k, v in ((NF.LIKED, liked), (NF.COLLECTED, collected),
                              (NF.COMMENTS, comments), (NF.SHARED, shared)) if v is not None}
    if not vals:
        raise ValueError(
            "一个数都没给 —— **那就别写**。\n"
            "没抓到就是没抓到:写 0 进去,周报会拿它当真的算(真栽过)。\n"
            "出路:先用技能真抓一次(`skills/xhs-extract-master/scripts/xhs note --url ...` 或 "
            "`node skills/xhs-collector/scripts/collect.mjs note <url>`),**抓到几个传几个**。")
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)
    r = feishu_io.get_record(NF.TABLE, note_id)
    if not r:
        raise ValueError(f"没找到这条笔记:{note_id}")
    if bitable.text(r["fields"].get(NF.STATUS)).strip() == NS.PUBLISHED:
        vals[NF.STATUS] = NS.LOOPED_BACK      # 已发 → 已回流(采到数据才推状态机)
    feishu_io.update_record(NF.TABLE, note_id, vals)
    return {"写回": note_id, "写了这几个数": {k: v for k, v in vals.items() if k != NF.STATUS},
            "没写的(你没给,就是没抓到)": [k for k, v in
                                          ((NF.LIKED, liked), (NF.COLLECTED, collected),
                                           (NF.COMMENTS, comments), (NF.SHARED, shared)) if v is None],
            "自证": f"python3 -m orchestrator note.get {note_id}"}


def link_materials(note_id: str, material_ids: list[str]) -> None:
    """给笔记挂素材(『关联素材』link 字段,写 record_id 列表)。**挂哪几张是 agent 的判断。**
    但 **id 必须真的存在** —— 飞书连 `recFAKE111111` 都照收(见 `_assert_materials_exist`)。"""
    _assert_materials_exist(material_ids)
    update(note_id, {NF.LINKED_MATERIALS: material_ids})
