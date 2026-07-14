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
from .bitable import AccountFields as AF, NoteFields as NF, NoteStatus as NS


class SkillMissing(RuntimeError):
    """模式声明的 gen_skill 装不上。宁可炸,也不让 LLM 在零技能下裸写(message 面向告警可读)。"""


def load_gen_skill(name: str) -> str:
    """加载 gen_skill 的 SKILL.md 正文(含该号真实帖 few-shot)。

    **只查 `skills/`(install_skills.sh 按 skills.lock.json 装出来的 symlink)——技能唯一真源 = qiaohe-skill 仓。**
    原来是 `local-skills/` → `skills/` 两处查、local 优先(2026-07-14 归一前):巧荷特化技能一半住 workspace
    的 local-skills、一半住技能仓,同类资产两个家;更坑的是**技能仓一旦出现同名技能就会被 local 静默盖住**
    (跑的技能 ≠ 锁记录/装进来的那份),而 installed_drift 只比远程 HEAD,这种遮蔽一个字都不报。
    归一后只有一个查找路径,遮蔽从根上不存在(skills_lock.shadowed_skills 留作回归哨兵,防有人再把它加回来)。

    **报了名字却找不到人 = 炸,不静默返回 ""**(2026-07-14 人眼审抓到):
    老实现文件不存在就悄悄给 "" → `compose_prompt(skill_text="")` → **LLM 在零技能、零 few-shot 下裸写**,
    而系统一声不吭。改个技能名、打错一个字、install_skills 漏装一个,都会让
    "每个模式都有专门技能写文案"这句话当场变成谎话,**且没有任何人会发现**——
    产出照样有,只是悄悄退化成通用口水文。这正是"人想起来方便的逻辑"的标本:
    `if p.exists() else ""` 写的时候觉得"稳",落实下来就是一个永不作声的黑洞。

    没声明 gen_skill(name="")→ 返 "" 合法(该模式本就不挂技能);声明了却装不上 → **炸在出稿前**。
    """
    if not name:
        return ""
    p = config.WORKSPACE / "skills" / name / "SKILL.md"
    if not p.exists():
        raise SkillMissing(
            f"模式声明了 gen_skill=「{name}」,但 skills/{name}/SKILL.md 不存在——"
            f"技能没装上(跑 bash scripts/install_skills.sh)或名字写错了。"
            f"**不能就这么裸写**:没技能=没 few-shot=没风格,产出会退化成通用口水文")
    return p.read_text(encoding="utf-8")


def _fit_to_spec(draft_text: str, pb: dict, prompt: str) -> tuple[str, float]:
    """**篇幅超规格 → 让它按规格改一次**(2026-07-14 探针真跑抓到:出稿 148 字,技能规格 100-140)。

    病根还是那个形状:prompt 里已经写了「【篇幅硬要求】必须 100-140 字」,`quality_flags` 也已经会
    标记超长 —— 于是系统觉得自己"做完了"。**可没有任何人去修它**:LLM 不听话,稿子照样落库,
    QC 旗子一插,锅甩给运营 —— 让他自己去删那 8 个字。**把 prompt 里的一句话当成了执行。**

    现在:超了就带着"你写了 N 字,砍到 lo-hi"回炉一次(ARK lite,一次几厘钱)。
    改完仍超 → **不再硬掰**,让 quality_flags 插旗、卡片上 ⚠️ 给人看(诚实兜底,不假装修好了)。
    只砍不足则不管:太短是内容不够,硬凑只会灌水,那才是真该让人看见的。
    """
    if not (pb and isinstance(pb.get("body_len"), (list, tuple)) and len(pb["body_len"]) == 2):
        return draft_text, 0.0
    lo, hi = int(pb["body_len"][0]), int(pb["body_len"][1])
    n = len(body_text(draft_text))
    if n <= hi:
        return draft_text, 0.0
    fixed, cost = llm.run_prompt(
        f"{prompt}\n\n——————\n你刚才写的稿子是:\n{draft_text}\n\n"
        f"**它的正文有 {n} 字,超了硬规格({lo}-{hi} 字),念出来会超时。**\n"
        f"请**只做删减**:保留标题、#标签、分层结构和全部真实画面细节,把正文压到 {lo}-{hi} 字。"
        f"删虚词、删重复的意象、删可有可无的修饰句;**不许换主题、不许新编画面、不许改标题**。\n"
        f"直接输出改好的完整稿(格式与刚才一致),不要解释。")
    return (fixed, cost) if len(body_text(fixed)) <= hi else (draft_text, cost)


def load_clothes(clothes_code: str, brand: str = "巧荷") -> str:
    """加载知识库里某件真实衣服的 know-how(款式/面料/工艺/卖点/形制/文物出处/纹样)。
    官号品牌新作/需具体产品的模式按此写**真实产品**,不编造。knowledge_base/衣服/{编号}.md;无则空串。
    编号只认干净标识(含 / \\ .. 的一律拒,防路径穿越读到知识库外的文件)。"""
    if not clothes_code or any(c in clothes_code for c in ("/", "\\", "..")):
        return ""
    p = config.WORKSPACE / "brands" / brand / "knowledge_base" / "衣服" / f"{clothes_code}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pick_playbook(acc, content_type: str = "") -> dict:
    """取该号 playbook:content_type 给定→**复用 accounts.resolve_playbook**(id 优先、同类取最高权重,
    统一选择语义,不再第二套 first-match);否则第一套。无 playbook / 指定内容类型不存在 → 报错(不静默漏)。"""
    pbs = acc.playbooks()
    if not pbs:
        raise ValueError(f"账号「{acc.name}」无 playbook 声明,无法生成")
    if content_type:
        pb = accounts.resolve_playbook(acc.strategy, playbook_id=content_type, content_type=content_type)
        if pb is None:
            raise ValueError(f"账号「{acc.name}」无内容类型「{content_type}」的 playbook(现有:"
                             f"{[pb.get('content_type') or pb.get('id') for pb in pbs]})")
        return pb
    return pbs[0]


def load_keywords(brand: str = "巧荷", limit: int = 18) -> list[str]:
    """关键词库里启用的关键词(选题/SEO 池;曾是哑数据没喂回生成)。启用状态≠停用 且有词(飞书实际枚举=启用/停用)。"""
    from . import bitable, feishu_io
    from .bitable import KeywordFields as KF
    out = []
    for r in feishu_io.list_records(KF.TABLE):
        f = r["fields"]
        kw = bitable.text(f.get(KF.KEYWORD)).strip()
        if kw and bitable.text(f.get(KF.ENABLED)).strip() != KF.DISABLED:
            out.append(kw)
    return out[:limit]


def compose_prompt(acc, pb: dict, skill_text: str, title_seed: str = "", clothes_text: str = "",
                   keywords: list | None = None, material_text: str = "") -> str:
    """把账号画像 + 该模式配方 + gen_skill few-shot + **本条要配的真实素材画面** + (可选)衣服 know-how 拼成 prompt。

    **material_text 是文案的事实底座**(dogfood 2026-07-14 补):gen_skill 要求写「面料质感」又要求
    「看不出的留白、严禁编造」——"看不出的"预设了作者看得见画面。原来 prompt 里**没有素材**(素材是生成
    完才挑的),LLM 眼前空白却被要求写质感 → 只能编。喂了 material_facts 后,文案是**配**这些画面写的。
    clothes_text 给定=另有知识库真身可依(官号品牌新作);两者都没有才退回"别写具体断言、留白"。"""
    profile = (acc.profile_text or "")[:1200]
    fewshot = (skill_text or "")[:4000]  # 放宽:整份 gen_skill 配方(标题+逐字稿等)进 prompt,不截尾
    ctype = pb.get("content_type") or pb.get("id") or ""
    recipe = ";".join(
        f"{label}={pb[k]}"
        for k, label in (("focus", "切面"), ("title_formula", "标题公式"), ("body_formula", "正文公式"))
        if pb.get(k)
    )
    parts = [
        "为巧荷(传统文化服装品牌,非遗面料复原/改良传统服饰)写一篇小红书笔记文案。",
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
    if material_text:
        # 事实底座:这条稿**配的就是这些已选定的真实画面**(豆包 vision 打的标)。技能第3层要写「面料质感」、
        # 又说「看不出的留白」——看得见画面,这两条才不打架:写画面里看得出的(颜色/光泽/垂坠/场景/光线)。
        parts.append("【本条要配的真实素材画面(已选定,发布时就是配这些图/视频)】\n" + material_text[:1200] +
                     "\n**文案必须配着这些画面写**:颜色/光泽/质感/场景/光线**只写画面里看得出的**;"
                     "画面里看不出的(具体面料成分、克重、朝代形制、非遗工序)**一律留白,严禁编造**——"
                     "宁可少写一层,也不许写出与画面对不上的东西(货不对板)。")
    if clothes_text:
        parts.append("【本条要展示的真实衣服(朝代/形制/工艺/纹样/面料/款式**严格以此为准,不得编造**)】\n"
                     + clothes_text[:1500])
    if not material_text and not clothes_text:
        parts.append("【无素材、也未绑衣服=没有任何事实来源】**严禁编造**具体产品名/朝代/形制/工艺/面料质感"
                     "(别凭空说'宋制褙子'、别说'料子很轻/垂坠感好'——你没见过这件衣服)——只写该号通用调性、留白。")
    body_len = pb.get("body_len") if isinstance(pb.get("body_len"), (list, tuple)) else None
    if body_len:
        parts.append(f"【篇幅硬要求】正文/逐字稿**必须 {body_len[0]}-{body_len[1]} 字**(不含标题和#标签)。"
                     "少于下限=念不满时长=不合格,别写三句就收;这是硬指标,先数够字数再谈意境。")
    parts.append("篇幅与结构**严格以上面 gen_skill 的规定为准**(要不要正文/逐字稿、分几层,一律 gen_skill 说了算)。")
    # **输出契约**(dogfood 2026-07-14 真跑逼出来的):gen_skill 的『交出什么』写的是给**人**的完整交付
    # (标题+逐字稿+建议素材+剪辑要点),越听话的模型越照单全交 → 执行器把整段塞进『文案草稿』字段 →
    # 运营从 base 复制就发,把「【视频剪辑要点】前4s定格…」发到小红书上。所以这里把输出契约焊死:
    # **本次只要可发布的成稿本身**,制作说明一律不要(要剪辑要点另走 video-editing)。
    parts.append("【输出契约·只输出要发布的成稿】第一行标题(≤20字),空行,正文/逐字稿,最后一行 3-5 个 #标签。"
                 "**绝对不要**输出:剪辑要点/分镜/运镜/景别/BGM/建议素材、`(27s逐字稿)`这类标注、任何解释——"
                 "这些是给剪辑看的,会被人当文案直接发出去。整段输出即为要发的内容,多一个字都是事故。")
    if keywords:
        parts.append(f"【本品牌关键词池(选题/SEO 参考)】贴合本条内容就自然带一两个,"
                     f"**别硬堆/别凑、调性优先**(唯美短稿不贴就别塞):{'、'.join(keywords)}")
    parts.append("只输出成稿文本,不要解释、不要读文件。")
    return "\n".join(parts)


def _stub_draft(acc, pb: dict, gen_skill: str, skill_loaded: bool, title_seed: str) -> str:
    ctype = pb.get("content_type") or pb.get("id") or ""
    tag = ("|画像✓" if acc.profile_text else "") + ("|few-shot✓" if skill_loaded else "") + f"|技能:{gen_skill}"
    head = title_seed or f"{ctype}·待人审草稿"
    return (f"{head}\n\n[stub 占位草稿|{ctype}|{acc.name}{tag}] "
            "——由 --llm real 生成正式稿(walking skeleton 结构验证用,不可发)。")


# 制作说明(给剪辑/拍摄看的),**绝不能混进要发布的文案**——运营从 base 复制『文案草稿』就发,
# 混进去就等于把「【视频剪辑要点】前4s定格…」发到小红书上。真跑实证(2026-07-14,豆包 lite):
# gen_skill 的『交出什么』要求"标题+逐字稿+建议素材+剪辑要点"(那是给**人**的完整交付定义),
# 越听话的模型越照做 → 执行器却把 LLM 整段输出原样塞进『文案草稿』字段 → 事故。
_PRODUCTION_MARKERS = ("剪辑要点", "分镜", "建议素材", "逐字稿）", "逐字稿)", "运镜", "BGM", "转场", "景别")


def body_text(draft_text: str) -> str:
    """剥掉标题行和 #标签行 → **真正要念/要读的正文**。篇幅是按它算的(算上标题标签会虚高)。"""
    lines = [ln.strip() for ln in (draft_text or "").splitlines() if ln.strip()]
    return "".join(ln for ln in lines[1:] if not ln.startswith("#"))


def quality_flags(draft_text: str, pb: dict | None = None, material_count: int | None = None) -> list[str]:
    """出稿即评轻量闸(#42 evaluator):对生成草稿做客观质检,返回问题标记(空列表=通过)。
    **不阻塞**(仍进草稿待发人审),把问题顶给人重点看——真正的把关在人审,这里只替人先扫一眼。

    **重写过一次(dogfood 2026-07-14,用户戳破)**:原来只检"标题>20字 / 全文>1000字"——那是**小红书的
    平台上限**,而我们所有模式都是短稿:4 条真稿实测标题最长 14 字、全文最长 195 字,**5 倍余量,永远撞不到**。
    于是 4 条真稿跑下来 **flag 一条都没响**,却把两个真缺陷全放过去了:
      ① 豆包 mini 出的稿正文才 56 字(技能要求 100-140 字)——**篇幅不达技能规格,没人拦**;
      ② 豆包 lite 把【视频剪辑要点】混进了要发的文案——**运营复制就发出去了,没人拦**。
    根因:每个模式的真规格只写在 SKILL.md 散文里,机器读不到,执行器只好去守一道够不着的天花板。
    现在按 **playbook 的 body_len(抄自技能自己的字数规定)** 检下限,并拦制作说明混入。
    """
    flags: list[str] = []
    t = (draft_text or "").strip()
    if not t:
        return ["空稿"]
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]

    # ⓪ **零素材 = 这条稿发不出去**(小红书图文/视频都必须有图/视频)。
    # 真跑实证(2026-07-14 全真实测):官号「品牌新作展示」绑了 --clothes GY-001,而 #36 货对板规则是
    # "只选标了该衣服的素材,否则**宁可 0 条不挂错图**"——素材库里没有任何素材标了 GY-001 → 选出 0 条 →
    # 一条**没有任何图的稿**落进『草稿待发』,而质检当时说「✅ 无问题」。运营拿到手根本发不了。
    # 规则本身没错(不挂错图),错在**没人把"这稿是废的"喊出来**。
    if material_count == 0:
        flags.append("零素材:一张图/视频都没挂,小红书发不出去——去素材表给这件衣服标上素材,或改用别的模式")

    # ① 制作说明混进要发的文案(真事故:运营从 base 复制就发)
    hit = [m for m in _PRODUCTION_MARKERS if m in t]
    if hit:
        flags.append(f"混入制作说明「{'/'.join(hit[:3])}」——这些是给剪辑看的,别发出去")

    # ② 篇幅按**本模式技能的规格**检(没规格就不瞎检;规格来自 playbook.body_len,抄自 SKILL.md)
    lo, hi = 0, 0
    if pb and isinstance(pb.get("body_len"), (list, tuple)) and len(pb["body_len"]) == 2:
        lo, hi = int(pb["body_len"][0]), int(pb["body_len"][1])
    if lo or hi:
        n = len(body_text(t))
        if n < lo:
            flags.append(f"正文{n}字 < 技能要求{lo}-{hi}字(短了,逐字稿念不满时长)")
        elif hi and n > hi:
            flags.append(f"正文{n}字 > 技能要求{lo}-{hi}字(长了,念超时)")

    # ③ 平台硬上限(小红书):当前模式都是短稿够不到,留作兜底——万一哪天模型跑飞才响
    if lines and len(lines[0]) > 20:
        flags.append(f"标题{len(lines[0])}字>20(小红书硬上限)")
    if len(t) > 1000:
        flags.append(f"全文{len(t)}字>1000(小红书硬上限)")

    if "stub" in t.lower() or "占位" in t:
        flags.append("含占位/stub(疑似未真生成)")
    if "#" not in t:
        flags.append("无#标签")
    if len(lines) > 3 and len(set(lines)) < len(lines) * 0.6:
        flags.append("多行重复(疑似生成异常)")
    return flags


def _split_title(draft_text: str, fallback: str) -> str:
    """草稿首行非空即标题(real 模式 prompt 要求第一行是标题);全空则用 fallback。"""
    for line in draft_text.splitlines():
        if line.strip():
            return line.strip()[:60]
    return fallback


def generate_draft(account_name: str, brand: str = "巧荷", llm_mode: str = "stub",
                   title_seed: str = "", clothes: str = "", content_type: str = "",
                   source_text: str = "", material_rows: list[dict] | None = None) -> dict:
    """读声明 → 加载 gen_skill few-shot(+可选真实衣服 know-how)→ 组稿 → 生成 → 组一条待审笔记字段。
    clothes=知识库衣服编号(如 GY-001):绑定后按真实产品写、防编造(官号品牌新作应绑)。
    content_type=指定模式(一号多模式时选哪个 playbook;空=第一套)。
    source_text=**对标源完整正文**(蹭爆款出稿时传灵感『文案』)——防搬运门比对它(不再只看标题),
    出稿逐字搬 ≥10 连续实义字符即拒(ADR-0009 P0:红线名不副实的修复)。**不写库**(纯计算)。"""
    acc = accounts.load(account_name, brand)
    if acc is None:
        raise ValueError(f"账号声明不存在:brands/{brand}/accounts/{account_name}.md")
    if acc.error:
        raise ValueError(f"账号「{account_name}」声明解析失败:{acc.error}")
    pb = pick_playbook(acc, content_type)
    gen_skill = accounts.gen_skill_of(pb)
    skill_text = load_gen_skill(gen_skill)
    clothes_text = load_clothes(clothes, brand)
    keywords = load_keywords(brand) if llm_mode == "real" else []  # 关键词只在真跑注入(stub 保持离线不触网)
    # **先挑素材,再配文**(dogfood 2026-07-14 修的顺序 bug):原来是先生成、后挑素材(create_draft_note 里),
    # 于是 prompt 里没有素材 → LLM 没见过要配的画面,却被 gen_skill 要求写「面料质感」→ 只能编 → 货不对板。
    # 选定的这批就是发布时真配的这批(create_draft_note 复用 material_ids,绝不重选,否则图文又错开)。
    #
    # **只有真生成才读库取素材**:stub 出的是占位文本,配什么图无所谓;这样单测/verify 保持离线快跑,
    # 不会 32 个调用点齐刷刷打真库(网络抖一下就红=假红)。stub 不带 material_ids → create_draft_note
    # 走老路自己选(行为不变)。material_rows 可显式注入(IO 与逻辑分离,同 `_material_hits` 纯谓词的路子)。
    if material_rows is None and llm_mode == "real":
        acc_ids = _resolve_link(AF.TABLE, AF.NAME, account_name)
        material_rows = select_material_rows(pb.get("material_needs") or [],
                                             acc_ids[0] if acc_ids else "", clothes=clothes)
    mat_rows = material_rows
    prompt = compose_prompt(acc, pb, skill_text, title_seed, clothes_text, keywords=keywords,
                            material_text=material_facts(mat_rows or []))   # stub 未取素材→无事实底座→走禁编造分支
    if llm_mode == "real":
        draft_text, cost = llm.run_prompt(prompt)
        # 防搬运出口闸(红线):**把所有进了 prompt 的文本都交给门**(2026-07-14 真跑修的方向性错误)。
        # 门必须守"LLM 真正看得见的东西":
        #   · title_seed —— 灵感标题(它在 prompt 的「标题线索」里)
        #   · **skill_text —— gen_skill 的 few-shot 真实帖**,就在 prompt 里,LLM 一眼能照抄。
        #     技能白纸黑字写着「只学结构、绝不抄原句」「出口过防搬运闸」——**而那句话从来没人执行**。
        #     真跑实证:把 few-shot 的真实帖逐字搬进产出 → **直接过门,一个字都没查**。
        #   · source_text —— 对标源正文(若调用方拿得到)。注意它**不进 prompt**,
        #     所以逐字搬它物理上不可能;传进来是纯保护、不产生风险。
        draft_text, cost2 = _fit_to_spec(draft_text, pb, prompt)
        cost += cost2
        # 门守的是**最终落库的那一份**。回炉改写用的 prompt 里同样带着 few-shot 真帖,
        # 改写时照样能抄 —— 所以门必须放在 _fit_to_spec **之后**,不是之前。
        guard.assert_no_source_leak([source_text, title_seed, skill_text], draft_text)
    else:
        draft_text, cost = _stub_draft(acc, pb, gen_skill, bool(skill_text), title_seed), 0.0
    ctype = pb.get("content_type") or pb.get("id") or ""
    title = _split_title(draft_text, title_seed or f"{ctype}·草稿")
    flags = quality_flags(draft_text, pb, None if mat_rows is None else len(mat_rows))
    note_fields = {
        NF.TITLE: title,
        NF.ACCOUNT: account_name,
        NF.CONTENT_TYPE: ctype,
        NF.PLAYBOOK: pb.get("id") or "",
        NF.DRAFT: draft_text,
        NF.STATUS: NS.DRAFT_PENDING,  # 草稿待发=待人审;绝不越过审核门,绝不代勾 AI 声明
        # **质检必须落库**:算出来不写库 = 运营在 base/卡片上都看不见 = 等于没检。
        # 真实代价(2026-07-14 运营视角实测):官号两条零素材废稿(小红书没图发不了)静静躺在
        # 待审区,卡片上一个字的提示都没有——人得点进去才发现是废稿。
        NF.QC: "；".join(flags) if flags else "",
    }
    return {
        "account": account_name,
        "playbook_id": pb.get("id") or "",
        "material_needs": pb.get("material_needs") or [],   # #32 选素材的 key(类型 vocab)
        "gen_skill": gen_skill,
        "skill_loaded": bool(skill_text),
        "clothes": clothes,
        "clothes_grounded": bool(clothes_text),   # 是否绑定了真实衣服 know-how(官号应为 True 防编造)
        # **文案是配着这批素材写的**(不是写完再挑图)→ create_draft_note 直接挂这批,绝不重选,
        # 否则发布时配的图和文案里写的画面对不上(货不对板)。
        # stub 未取素材(mat_rows=None)→ 不给 material_ids,create_draft_note 走老路自己选(行为不变)。
        **({"material_ids": [r["record_id"] for r in mat_rows],
            "material_grounded": bool(mat_rows)} if mat_rows is not None else {}),
        "content_type": ctype,
        "title": title,
        "draft_text": draft_text,
        "cost": cost,
        "prompt": prompt,
        # 按**本模式技能自己的规格**质检(playbook.body_len)+ 零素材(发不出去)——不再守那道够不着的平台天花板。
        # 同一份 flags 已写进 note_fields[质检] 落库 → 运营在 base 和今日卡片上都看得见。
        "quality_flags": flags,
        "note_fields": note_fields,
    }


def _resolve_link(table: str, name_field: str, name: str) -> list[str]:
    """把名字解析成该表匹配行的 record_id 列表——账号/内容类型是 link 字段,飞书要 record_id 不是字符串。
    规模M3:按名 **服务端过滤**(search_in,不全拉表);保留内存 strip 比对(等价严格 + 兜底空格/mock)。"""
    from . import bitable, feishu_io
    if not name:
        return []
    return [r["record_id"] for r in feishu_io.search_in(table, name_field, [name])
            if bitable.text(r["fields"].get(name_field)).strip() == name]


def _material_hits(records: list[dict], material_needs: list[str], account_rec_id: str = "",
                   limit: int = 3, clothes: str = "", content: str = "") -> list[str]:
    """#32 选素材的**纯过滤谓词**(零 IO,records 由调用点注入)→ 命中 record_id(≤limit)。
    这里是全仓分支最密、最易错的一段(6 条过滤 + 排序),抽成纯函数直测(不必 mock list_records):
      ① 类型 ∈ material_needs ② 拍摄状态=已拍 ③ 赛道投影(显式标别号排除、未标可用)
      ④ #36 货对板(clothes 给定:只选编号/备注标了该衣服的,否则宁可 0 条不挂错图)
      ⑤ #38 内容寻址(content 给定:按备注内容标签如'逆光'选)⑥ #36 少用优先(被引次数升序,素材分散防撞图)。
    空 material_needs / 无候选 → [](不炸)。"""
    from . import bitable
    from .bitable import MaterialFields as MF, MaterialStatus as MS
    needs = set(material_needs or [])
    if not needs:
        return []
    cands: list[dict] = []
    for m in records:
        f = m["fields"]
        if bitable.text(f.get(MF.TYPE)) not in needs:
            continue
        if bitable.text(f.get(MF.SHOT_STATUS)) != MS.SHOT:
            continue
        accs = bitable.link_record_ids(f.get(MF.ACCOUNTS))
        if account_rec_id and accs and account_rec_id not in accs:
            continue                       # 显式标了别号=排除;没标=可用
        if clothes and clothes not in (bitable.text(f.get(MF.CODE)) + "|" + bitable.text(f.get(MF.NOTE))):
            continue                       # #36 品牌新作:只选标了该衣服的素材,否则货不对板
        if content and content not in (bitable.text(f.get(MF.CODE)) + "|" + bitable.text(f.get(MF.NOTE))):
            continue                       # #38 内容寻址:按备注里的内容标签(场景/调性/衣服)选,如'逆光'
        cands.append(m)
    # #36 少用优先:按被引用次数升序(stable,同分保持原序)→ 素材天然分散,减少跨号/跨条撞图
    # 整条 fields 传进去:真被引用次数要**数反向链接**,formula『被引用次数』在活库里是空公式恒为 0。
    cands.sort(key=lambda m: _cited_count(m["fields"]))
    return [m["record_id"] for m in _spread_by_scene(cands, limit)]


def _scene_key(fields: dict) -> str:
    """画面指纹:豆包 vision 标(『备注』)的前 24 字。同一组连拍的备注几乎逐字相同,指纹就撞上。"""
    from . import bitable
    from .bitable import MaterialFields as MF
    return bitable.text(fields.get(MF.NOTE)).strip()[:24]


def _spread_by_scene(cands: list[dict], limit: int) -> list[dict]:
    """**一条笔记里的几张图,画面别重样**(2026-07-14 运营视角实测)。

    真跑出的一条图文稿挂了 3 张图,vision 标是:
      「粉色上衣、白色纱裙、坐大理石楼梯旁、暖光、手触脸颊」
      「粉色上衣、白色纱裙、坐大理石楼梯旁、暖光、手触脸颊」  ← 逐字一样
      「粉色上衣、白色纱裙、坐大理石楼梯旁、暖光、手比V」     ← 还是一样
    ——同一组连拍被整组选中。运营一眼看出来:"3 张图长得一样,发出去像凑数。"
    选材原来只看『类型 + 少用优先』,**完全不看画面是不是重样**。

    做法:先每个画面指纹各取一张(优先铺开场景),不够 limit 再回头补同指纹的
    (库存不足时宁可重样也别少给图——少给图就发不出去,那是更硬的伤)。
    """
    first, rest, seen = [], [], set()
    for m in cands:
        k = _scene_key(m["fields"])
        if k and k in seen:
            rest.append(m)                # 同一组连拍,先放一边
        else:
            seen.add(k)
            first.append(m)
    return (first + rest)[:limit]         # 画面各异的优先;不够再用同场景的补齐


def select_material_rows(material_needs: list[str], account_rec_id: str = "", limit: int = 3,
                         clothes: str = "", content: str = "") -> list[dict]:
    """#32 选素材,返回**完整行**(不只 record_id)——出稿要拿它们的 vision 标签(『备注』)当**事实底座**。
    类型∈material_needs 服务端过滤(不全表拉,规模M2)→ 交纯谓词 `_material_hits` 决策,保持其排序。"""
    from . import feishu_io
    from .bitable import MaterialFields as MF
    rows = feishu_io.search_in(MF.TABLE, MF.TYPE, material_needs)   # 类型∈needs 下推
    hit_ids = _material_hits(rows, material_needs, account_rec_id, limit, clothes, content)
    by_id = {r["record_id"]: r for r in rows}
    return [by_id[i] for i in hit_ids if i in by_id]                # 保 _material_hits 的少用优先序


def select_materials(material_needs: list[str], account_rec_id: str = "", limit: int = 3,
                     clothes: str = "", content: str = "") -> list[str]:
    """同上,只要 record_id(向后兼容的薄壳)。"""
    return [r["record_id"] for r in
            select_material_rows(material_needs, account_rec_id, limit, clothes, content)]


def material_facts(rows: list[dict]) -> str:
    """选中素材的**真实画面事实**(豆包 vision 打的『备注』+ 类型)→ 喂进出稿 prompt 当事实底座。

    **为什么必须有(dogfood 2026-07-14 真跑实证)**:gen_skill `writing-ootd-caption` 的视频四层结构
    第 3 层白纸黑字要求写「面料质感(面料名+通感,解显胖顾虑)」,同一份技能又要求「**看不出的**面料/工艺
    留白,严禁编造」——"看不出的"这三个字的前提是**作者看得见画面**。可执行器原来是**先生成、后挑素材**
    (compose_prompt 里根本没有素材),LLM 眼前一片空白却被要求写面料质感 → 两条要求直接冲突,它只能编:
    真跑出的稿写「料子很轻,上身几乎没有重量,垂下来是顺的」,而真素材是「浅粉色带细闪的汉服衣身特写,
    红棕色木质场景」——文案和画面是两回事,货不对板。

    修法不是加禁令(禁令早在技能里了,再加只会和第3层对撞),是**给它眼睛**:先挑素材→事实进 prompt→再配文。
    副产品:**不需要注册衣服**(用户本来就不注册,拍了就配文发)——vision 标签就是这件衣服的真相。"""
    from . import bitable
    from .bitable import MaterialFields as MF
    lines = []
    for r in rows:
        f = r.get("fields", {})
        note = bitable.text(f.get(MF.NOTE)).strip()      # 豆包看图打的画面标
        typ = bitable.text(f.get(MF.TYPE)).strip()
        if note:
            lines.append(f"· [{typ or '素材'}] {note}")
    return "\n".join(lines)


def _cited_count(fields: dict) -> int:
    """这条素材被多少篇笔记引用过 → `#36 少用优先` 的排序依据(分散选材,防撞图)。

    **数反向链接,不信 formula**(dogfood 2026-07-14 真跑抓的死机制):
    旧实现读『被引用次数』formula 字段——**它恒返回 0**(COUNTA/COUNT 对 DuplexLink 在飞书算不出来;
    真库实证:ST-260702-001 反向链接已挂 4 篇笔记,formula 仍报 0;282 条素材里 13 条被真引用过的全报错)。
    后果:所有素材 cited 全 0 → 排序 stable → **永远返回表序前 3 条** → 133 条上身图只用前 3 条,
    3 个号同一天出稿全撞同一批图。"少用优先防撞图"这个机制**整个是死的**,而绿门永远抓不到
    (它测的是排序逻辑,不是数据源)。该 formula 字段已从测试库删除(既坏又冗余)。

    现在数反向 link:link 是真实数据,不依赖飞书公式引擎。
    """
    from . import bitable
    from .bitable import MaterialFields as MF
    return len(bitable.link_record_ids(fields.get(MF.BACKLINK)))


def _find_inflight_note(account_name: str, content_type_name: str) -> str:
    """找该 (账号, 内容类型) 在途的 Note(待出文案/草稿待发)record_id;无则空。
    出稿据此**推进**派活的『待出文案』为『草稿待发』(状态机一条内容一行),不新建重复行。

    **必须用 record_id 比对,不能用 text()**(dogfood 2026-07-14,从运营卡片上看出来的):
    这里读的是 `search` API 的返回,而 search 的 link 字段形态是 `{'link_record_ids': [...]}`——**没有 text**
    (list/get 才有 `[{record_ids, text}]`)。原来用 `bitable.text(f.get(NF.ACCOUNT))` 比对账号名 →
    永远读出空串 → 永远不等于账号名 → **在途笔记永远找不到 → 每次出稿都新建一行**。
    后果直接砸在人脸上:运营今日卡片的待审区堆了 **5 条同号同模式的重复稿**(全是"粉纱+光"),
    人打开第一反应是"我审哪条?"。绿门/exit 0 全过——只有真去看那张卡片才发现。
    (同一形态 bug 上轮修过 cockpit/dispatch/publish,唯独漏了这里。)
    """
    from . import bitable, feishu_io
    from .bitable import AccountFields as AF, ContentTypeFields as CTF
    acc_ids = set(_resolve_link(AF.TABLE, AF.NAME, account_name))
    ct_ids = set(_resolve_link(CTF.TABLE, CTF.NAME, content_type_name))
    if not acc_ids:                      # 号都解析不出来,别乱认在途(宁可新建也不改错行)
        return ""
    # 状态∈开态 服务端过滤(规模M2,不全拉笔记表);search 已保证状态,只余按号×模式内存筛
    for r in feishu_io.search_in(NF.TABLE, NF.STATUS, [NS.NEED_COPY, NS.DRAFT_PENDING]):
        f = r["fields"]
        if (acc_ids & set(bitable.link_record_ids(f.get(NF.ACCOUNT)))
                and (not ct_ids or ct_ids & set(bitable.link_record_ids(f.get(NF.CONTENT_TYPE))))):
            return r["record_id"]
    return ""


def create_draft_note(result: dict) -> str:
    """把生成结果写成笔记表『草稿待发』一行,返回 record_id。先过 base 红线闸(只许测试库)。
    **状态机推进/去重**:该号×模式已有在途 Note(派活占位『待出文案』或旧『草稿待发』)→ 推进/刷新那一行
    (一条内容一行,不新建重复);无则新建。账号/内容类型 link 名字→record_id;挂不上不写该 link(不炸)。
    #32:按 material_needs 选素材挂『关联素材』(文案+素材=完整可发包)。"""
    from . import feishu_io
    from .bitable import AccountFields as AF, ContentTypeFields as CTF
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:TEST_MODE 下只许写测试 Base
    fields = dict(result["note_fields"])
    account_name = fields.get(NF.ACCOUNT, "")           # 解析成 record_id 前先留名字(用于查在途)
    content_type_name = fields.get(NF.CONTENT_TYPE, "")
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
    # **复用出稿时选定的那批素材**(文案就是配它们写的);老结果无 material_ids 才回退现选(向后兼容)。
    # 绝不重选:重选可能挑出另一批(少用优先序会随被引次数变)→ 配的图和文案写的画面对不上,货不对板。
    mat_ids = result.get("material_ids")
    if mat_ids is None:
        mat_ids = select_materials(result.get("material_needs") or [], acc_ids[0] if acc_ids else "",
                                   clothes=result.get("clothes", ""))  # #36 品牌新作按衣服选素材,货对板
    from . import processing
    decide, execute = processing.default_hooks() if processing.processing_enabled() else (None, None)
    mat_ids = processing.maybe_process(mat_ids, account=account_name, mode=content_type_name,
                                       clothes=result.get("clothes", ""),
                                       decide=decide, execute=execute)  # M3 gated 加工步(默认关=原样返回;开=拼图等真加工)
    if mat_ids:
        fields[NF.LINKED_MATERIALS] = mat_ids   # #32 完整包:选定(或加工后)素材挂关联素材
    existing = _find_inflight_note(account_name, content_type_name)
    if existing:
        feishu_io.update_record(NF.TABLE, existing, fields)  # 推进:待出文案→草稿待发 / 刷新旧草稿(不新建重复)
        return existing
    return feishu_io.create_record(NF.TABLE, fields)
