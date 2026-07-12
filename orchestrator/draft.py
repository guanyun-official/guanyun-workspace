"""薄执行器(第一目标 A 的 walking skeleton):给一个号即时产一条待审草稿。

流程(每步只调已验证原语,不走重引擎 / 不排产 / 不建视图):
  accounts.load(号)               读账号声明 + 画像
  → 取该号 playbook 的 gen_skill,load_gen_skill 加载其 SKILL.md(真实帖 few-shot)  ← 补『gen_skill 只是标签』缺口
  → compose_prompt(画像 + few-shot + 配方)
  → 生成(stub 默认零成本 / real 走 llm.run_prompt 预算帽)
  → 组一条笔记字段(状态=草稿待发,待人审)
  → create_draft_note:过 base 红线闸 → feishu_io 写笔记表一行 → 返回 record_id

红线:只在测试库写(guard.assert_base_allowed);发布与 AI 声明是人手,本执行器只推到「草稿待发」,
绝不代勾 AI 声明、绝不自动发布。
"""
from __future__ import annotations

from . import accounts, config, guard, llm
from .bitable import NoteFields as NF, NoteStatus as NS


def load_gen_skill(name: str) -> str:
    """加载 gen_skill 的 SKILL.md 正文(含该号真实帖 few-shot)。
    先 local-skills/<name>(号/模式特化),再 skills/<name>(装好的通用能力);都无则空串。"""
    if not name:
        return ""
    for base in (config.WORKSPACE / "local-skills", config.WORKSPACE / "skills"):
        p = base / name / "SKILL.md"
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def load_clothes(clothes_code: str, brand: str = "观云") -> str:
    """加载知识库里某件真实衣服的 know-how(款式/面料/工艺/卖点/形制/文物出处/纹样)。
    官号品牌新作/需具体产品的模式按此写**真实产品**,不编造。knowledge_base/衣服/{编号}.md;无则空串。
    编号只认干净标识(含 / \\ .. 的一律拒,防路径穿越读到知识库外的文件)。"""
    if not clothes_code or any(c in clothes_code for c in ("/", "\\", "..")):
        return ""
    p = config.WORKSPACE / "brands" / brand / "knowledge_base" / "衣服" / f"{clothes_code}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pick_playbook(acc, content_type: str = "") -> dict:
    """取该号 playbook:content_type 给定→按内容类型选(**一号多模式**);否则第一套。
    无 playbook / 指定内容类型不存在 → 报错(坏声明/选错模式不静默漏)。"""
    pbs = acc.playbooks()
    if not pbs:
        raise ValueError(f"账号「{acc.name}」无 playbook 声明,无法生成")
    if content_type:
        for pb in pbs:
            if (pb.get("content_type") or pb.get("id") or "") == content_type:
                return pb
        raise ValueError(f"账号「{acc.name}」无内容类型「{content_type}」的 playbook(现有:"
                         f"{[pb.get('content_type') or pb.get('id') for pb in pbs]})")
    return pbs[0]


def compose_prompt(acc, pb: dict, skill_text: str, title_seed: str = "", clothes_text: str = "") -> str:
    """把账号画像 + 该模式配方 + gen_skill few-shot + (可选)真实衣服 know-how 拼成生成 prompt。
    clothes_text 给定=写真实产品的事实源(防编造);没给=禁止编造具体产品/朝代/工艺。"""
    profile = (acc.profile_text or "")[:1200]
    fewshot = (skill_text or "")[:4000]  # 放宽:整份 gen_skill 配方(标题+逐字稿等)进 prompt,不截尾
    ctype = pb.get("content_type") or pb.get("id") or ""
    recipe = ";".join(
        f"{label}={pb[k]}"
        for k, label in (("focus", "切面"), ("title_formula", "标题公式"), ("body_formula", "正文公式"))
        if pb.get(k)
    )
    parts = [
        "为观云(传统文化服装品牌,非遗面料复原/改良传统服饰)写一篇小红书笔记文案。",
        f"账号:{acc.name} 内容类型:{ctype}",
    ]
    if title_seed:
        parts.append(f"标题线索:{title_seed}")
    if recipe:
        parts.append(f"【本条方法论配方(按此写)】{recipe}")
    if profile:
        parts.append(f"【本账号画像(务必贴合其既有风格)】\n{profile}")
    if fewshot:
        parts.append(f"【生成技能与真实帖 few-shot(照此调性/形制,勿抄原文)】\n{fewshot}")
    if clothes_text:
        parts.append("【本条要展示的真实衣服(朝代/形制/工艺/纹样/面料/款式**严格以此为准,不得编造**)】\n"
                     + clothes_text[:1500])
    else:
        parts.append("【未绑定具体衣服】**严禁编造**不存在的具体产品名/朝代/形制/工艺(如凭空说'宋制褙子'、"
                     "展开讲某面料是几经绞/哪道非遗工序)——没有事实来源就别写具体产品/朝代断言,只写该号通用调性、留白。")
    parts.append("篇幅与结构**严格以上面 gen_skill 的规定为准**(标题多长、要不要正文/逐字稿、多少字或多少秒,"
                 "一律 gen_skill 说了算,别自作主张压短或拉长)。小红书统一外壳:第一行标题(≤20字),空行,"
                 "正文/逐字稿,最后一行 3-5 个 #标签(全文≤1000字)。")
    parts.append("只输出成稿文本,不要解释、不要读文件。")
    return "\n".join(parts)


def _stub_draft(acc, pb: dict, gen_skill: str, skill_loaded: bool, title_seed: str) -> str:
    ctype = pb.get("content_type") or pb.get("id") or ""
    tag = ("|画像✓" if acc.profile_text else "") + ("|few-shot✓" if skill_loaded else "") + f"|技能:{gen_skill}"
    head = title_seed or f"{ctype}·待人审草稿"
    return (f"{head}\n\n[stub 占位草稿|{ctype}|{acc.name}{tag}] "
            "——由 --llm real 生成正式稿(walking skeleton 结构验证用,不可发)。")


def _split_title(draft_text: str, fallback: str) -> str:
    """草稿首行非空即标题(real 模式 prompt 要求第一行是标题);全空则用 fallback。"""
    for line in draft_text.splitlines():
        if line.strip():
            return line.strip()[:60]
    return fallback


def generate_draft(account_name: str, brand: str = "观云", llm_mode: str = "stub",
                   title_seed: str = "", clothes: str = "", content_type: str = "") -> dict:
    """读声明 → 加载 gen_skill few-shot(+可选真实衣服 know-how)→ 组稿 → 生成 → 组一条待审笔记字段。
    clothes=知识库衣服编号(如 GY-001):绑定后按真实产品写、防编造(官号品牌新作应绑)。
    content_type=指定模式(一号多模式时选哪个 playbook;空=第一套)。**不写库**(纯计算)。"""
    acc = accounts.load(account_name, brand)
    if acc is None:
        raise ValueError(f"账号声明不存在:brands/{brand}/accounts/{account_name}.md")
    if acc.error:
        raise ValueError(f"账号「{account_name}」声明解析失败:{acc.error}")
    pb = pick_playbook(acc, content_type)
    gen_skill = accounts.gen_skill_of(pb)
    skill_text = load_gen_skill(gen_skill)
    clothes_text = load_clothes(clothes, brand)
    prompt = compose_prompt(acc, pb, skill_text, title_seed, clothes_text)
    if llm_mode == "real":
        draft_text, cost = llm.run_prompt(prompt)
    else:
        draft_text, cost = _stub_draft(acc, pb, gen_skill, bool(skill_text), title_seed), 0.0
    ctype = pb.get("content_type") or pb.get("id") or ""
    title = _split_title(draft_text, title_seed or f"{ctype}·草稿")
    note_fields = {
        NF.TITLE: title,
        NF.ACCOUNT: account_name,
        NF.CONTENT_TYPE: ctype,
        NF.PLAYBOOK: pb.get("id") or "",
        NF.DRAFT: draft_text,
        NF.STATUS: NS.DRAFT_PENDING,  # 草稿待发=待人审;绝不越过审核门,绝不代勾 AI 声明
    }
    return {
        "account": account_name,
        "playbook_id": pb.get("id") or "",
        "material_needs": pb.get("material_needs") or [],   # #32 选素材的 key(类型 vocab)
        "gen_skill": gen_skill,
        "skill_loaded": bool(skill_text),
        "clothes": clothes,
        "clothes_grounded": bool(clothes_text),   # 是否绑定了真实衣服 know-how(官号应为 True 防编造)
        "content_type": ctype,
        "title": title,
        "draft_text": draft_text,
        "cost": cost,
        "prompt": prompt,
        "note_fields": note_fields,
    }


def _resolve_link(table: str, name_field: str, name: str) -> list[str]:
    """把名字解析成该表匹配行的 record_id 列表——账号/内容类型是 link 字段,飞书要 record_id 不是字符串。"""
    from . import bitable, feishu_io
    if not name:
        return []
    return [r["record_id"] for r in feishu_io.list_records(table)
            if bitable.text(r["fields"].get(name_field)).strip() == name]


def select_materials(material_needs: list[str], account_rec_id: str = "", limit: int = 3,
                     clothes: str = "", content: str = "") -> list[str]:
    """#32 选素材:素材表里 类型 ∈ material_needs + 拍摄状态=已拍 +(适用账号空 或 含该号)的候选 record_id(≤limit)。
    赛道投影:显式标了别号的素材排除,没标(未归赛道)的可用。空 material_needs / 无候选 → [](不炸)。

    #36 clothes(衣服编号)给定=**品牌新作货对板闸**:只选『编号/备注里标了该衣服』的素材——
    防官号文案绑某衣服、素材却是另一件的『货不对板=对读者等于编造』。标不上就宁可 0 条(不挂错图)。"""
    from . import bitable, feishu_io
    from .bitable import MaterialFields as MF, MaterialStatus as MS
    needs = set(material_needs or [])
    if not needs:
        return []
    cands: list[dict] = []
    for m in feishu_io.list_records(MF.TABLE):
        f = m["fields"]
        if bitable.text(f.get(MF.TYPE)) not in needs:
            continue
        if bitable.text(f.get(MF.SHOT_STATUS)) != MS.SHOT:
            continue
        accs = bitable.Record(m).link_ids(MF.ACCOUNTS)
        if account_rec_id and accs and account_rec_id not in accs:
            continue                       # 显式标了别号=排除;没标=可用
        if clothes and clothes not in (bitable.text(f.get(MF.CODE)) + "|" + bitable.text(f.get(MF.NOTE))):
            continue                       # #36 品牌新作:只选标了该衣服的素材,否则货不对板
        if content and content not in (bitable.text(f.get(MF.CODE)) + "|" + bitable.text(f.get(MF.NOTE))):
            continue                       # #38 内容寻址:按备注里的内容标签(场景/调性/衣服)选,如'逆光'
        cands.append(m)
    # #36 少用优先:按被引用次数升序(stable,同分保持原序)→ 素材天然分散,减少跨号/跨条撞图
    cands.sort(key=lambda m: _cited_count(m["fields"].get(MF.CITED)))
    return [m["record_id"] for m in cands[:limit]]


def _cited_count(v) -> int:
    """被引用次数(formula 字段,可能 int/str/list/dict/None)→ int,坏值当 0(不炸,当没被引用)。"""
    if isinstance(v, list):
        v = v[0] if v else 0
    if isinstance(v, dict):
        v = v.get("value") or v.get("text") or 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def create_draft_note(result: dict) -> str:
    """把生成结果写成笔记表一行(状态=草稿待发)。先过 base 红线闸(只许测试库);返回 record_id。
    账号/内容类型是 link 字段:名字→record_id 后再写;挂不上就不写该 link(不因孤儿名炸写)。
    #32:按 material_needs 选素材,挂进「关联素材」——从「半个包(纯文案)」升到「完整可发包(文案+素材)」。"""
    from . import feishu_io
    from .bitable import AccountFields as AF, ContentTypeFields as CTF
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:TEST_MODE 下只许写测试 Base
    fields = dict(result["note_fields"])
    acc_ids = _resolve_link(AF.TABLE, AF.NAME, fields.get(NF.ACCOUNT, ""))
    if acc_ids:
        fields[NF.ACCOUNT] = acc_ids
    else:
        fields.pop(NF.ACCOUNT, None)
    ct_ids = _resolve_link(CTF.TABLE, CTF.NAME, fields.get(NF.CONTENT_TYPE, ""))
    if ct_ids:
        fields[NF.CONTENT_TYPE] = ct_ids
    else:
        fields.pop(NF.CONTENT_TYPE, None)
    mat_ids = select_materials(result.get("material_needs") or [], acc_ids[0] if acc_ids else "",
                               clothes=result.get("clothes", ""))  # #36 品牌新作按衣服选素材,货对板
    if mat_ids:
        fields[NF.LINKED_MATERIALS] = mat_ids   # #32 完整包:选定素材挂关联素材
    return feishu_io.create_record(NF.TABLE, fields)
