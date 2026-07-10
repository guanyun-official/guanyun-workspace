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


def pick_playbook(acc) -> dict:
    """A 阶段一号一模式:取该号第一套 playbook;无则报错(坏声明不静默漏号)。"""
    pbs = acc.playbooks()
    if not pbs:
        raise ValueError(f"账号「{acc.name}」无 playbook 声明,无法生成")
    return pbs[0]


def compose_prompt(acc, pb: dict, skill_text: str, title_seed: str = "") -> str:
    """把账号画像 + 该模式配方 + gen_skill 的真实帖 few-shot 拼成生成 prompt(生成的唯一注入口)。"""
    profile = (acc.profile_text or "")[:1200]
    fewshot = (skill_text or "")[:1500]
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
    parts.append("格式:第一行标题(≤20字),空行,正文(≤1000字,分段,可用少量 emoji),最后一行 3-5 个#标签。")
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
                   title_seed: str = "") -> dict:
    """读声明 → 加载 gen_skill few-shot → 组稿 → 生成 → 组一条待审笔记字段。**不写库**(纯计算)。"""
    acc = accounts.load(account_name, brand)
    if acc is None:
        raise ValueError(f"账号声明不存在:brands/{brand}/accounts/{account_name}.md")
    if acc.error:
        raise ValueError(f"账号「{account_name}」声明解析失败:{acc.error}")
    pb = pick_playbook(acc)
    gen_skill = accounts.gen_skill_of(pb)
    skill_text = load_gen_skill(gen_skill)
    prompt = compose_prompt(acc, pb, skill_text, title_seed)
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
        "gen_skill": gen_skill,
        "skill_loaded": bool(skill_text),
        "content_type": ctype,
        "title": title,
        "draft_text": draft_text,
        "cost": cost,
        "prompt": prompt,
        "note_fields": note_fields,
    }


def create_draft_note(result: dict) -> str:
    """把生成结果写成笔记表一行(状态=草稿待发)。先过 base 红线闸(只许测试库);返回 record_id。"""
    from . import feishu_io
    guard.assert_base_allowed(config.BASE_TOKEN, config.TEST_MODE)  # 红线:TEST_MODE 下只许写测试 Base
    return feishu_io.create_record(NF.TABLE, result["note_fields"])
