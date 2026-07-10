"""LLM 步(唯一花钱的地方):文案生成。stub 模式零成本占位;real 模式 claude -p 预算帽硬限。
推进器自身零 LLM——本模块只被 engine 在 GEN_COPY 动作里调用。
"""
from __future__ import annotations

import json
import subprocess

from . import bitable, config  # 候选A:字段取文本走统一 adapter
from .bitable import NoteFields as NF

USD_CNY = 7.2


def _text_of(v) -> str:
    return bitable.text(v)


def _load_account(account: str, brand: str = "观云"):
    """统一 Account 定义(画像 prose + strategy)。缺则 None(降级通用)。"""
    if not account:
        return None
    from . import accounts
    return accounts.load(account, brand)


def _playbook_recipe(pb: dict | None) -> str:
    """把 playbook 声明的可注入配方拼成一行(切面/标题·正文公式;缺则空)——G10:方法论驱动生成。"""
    if not pb:
        return ""
    bits = []
    if pb.get("focus"):
        bits.append(f"切面={pb['focus']}")
    if pb.get("title_formula"):
        bits.append(f"标题公式={pb['title_formula']}")
    if pb.get("body_formula"):
        bits.append(f"正文公式={pb['body_formula']}")
    return ";".join(bits)


def run_prompt(prompt: str) -> tuple[str, float]:
    """跑一次 claude -p(零工具直出,预算帽硬限),返回 (成稿文本, 成本_元)。
    薄执行器(draft.py)与 gen_copy 共用的 real 生成底座;stub 占位由调用方自处理,不进本函数。"""
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "2",
         "--max-budget-usd", str(config.PER_RUN_BUDGET_USD), "--allowedTools", ""],
        capture_output=True, text=True, timeout=600, cwd=str(config.WORKSPACE),
    )
    d = json.loads(r.stdout[r.stdout.find("{"):])
    text = (d.get("result") or "").strip()
    cost = round(float(d.get("total_cost_usd") or 0) * USD_CNY, 3)
    if not text:
        raise RuntimeError(f"claude -p 空结果: {r.stdout[:200]}")
    return (text, cost)


def gen_copy(note_fields: dict, mode: str = "stub") -> tuple[str, float, str]:
    """返回 (文案草稿, 成本_元, 生成技能)。mode: stub|real。
    生成按该条所属 playbook 配方(G10),并解析该方法论的生成技能 gen_skill(G13)。"""
    from . import accounts
    title = _text_of(note_fields.get(NF.TITLE)) or _text_of(note_fields.get(NF.CODE))
    ctype = _text_of(note_fields.get(NF.CONTENT_TYPE))
    account = _text_of(note_fields.get(NF.ACCOUNT))
    acc = _load_account(account)
    profile = acc.profile_text[:1200] if acc else ""      # 每号风格注入(缺则降级)
    # G10/G11:解析所属方法论——笔记显式「方法论」字段优先,否则按内容类型猜
    pb = accounts.resolve_playbook(acc.strategy, _text_of(note_fields.get(NF.PLAYBOOK)), ctype) if acc else None
    pb_id = pb.get("id") if pb else ""
    gen_skill = accounts.gen_skill_of(pb)                 # G13:该方法论用哪个技能产笔记
    recipe = _playbook_recipe(pb)
    if mode != "real":
        tag = ("|画像✓" if profile else "") + (f"|方法论:{pb_id}" if pb_id else "") + f"|技能:{gen_skill}"
        return (f"[stub 占位文案|{ctype}|{account}{tag}] {title}——由 --llm real 生成正式稿。", 0.0, gen_skill)

    hint = _text_of(note_fields.get(NF.STORYBOARD))[:300]
    # 提示词自带品牌要点(P6演练教训:让 headless 去翻仓库会烧穿预算帽),零工具直出
    prompt = (
        f"为观云(传统文化服装品牌,非遗面料复原/改良传统服饰)写一篇小红书笔记文案。\n"
        f"笔记:「{title}」 内容类型:{ctype} 账号:{account}\n"
        f"{'线索:' + hint if hint else ''}\n"
        + (f"【本条方法论配方(按此写)】{recipe}\n" if recipe else "")
        + (f"【本账号画像(务必贴合其既有风格)】\n{profile}\n" if profile else
           "调性:清冷、唯美、克制,不硬广;考据有据(文物对照:钩子→出处稀缺→形制工艺考据→非遗升华;ootd:意境起笔→文化→版型面料→场景)。\n")
        + f"格式:第一行标题(≤20字),空行,正文(≤1000字,分段,可用少量 emoji),最后一行 3-5 个#标签。\n"
        f"只输出成稿文本,不要解释、不要读文件。"
    )
    text, cost = run_prompt(prompt)  # 共用 real 生成底座(见上 run_prompt)
    return (text, cost, gen_skill)
