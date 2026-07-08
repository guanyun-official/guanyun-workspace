"""LLM 步(唯一花钱的地方):文案生成。stub 模式零成本占位;real 模式 claude -p 预算帽硬限。
推进器自身零 LLM——本模块只被 engine 在 GEN_COPY 动作里调用。
"""
from __future__ import annotations

import json
import subprocess

from . import bitable, config  # 候选A:字段取文本走统一 adapter

USD_CNY = 7.2


def _text_of(v) -> str:
    return bitable.text(v)


def _account_profile(account: str, brand: str = "观云") -> str:
    """加载账号画像 prose(候选C:统一 Account 定义的正文,不含 frontmatter)注入生成。缺则空(降级通用)。"""
    if not account:
        return ""
    from . import accounts
    acc = accounts.load(account, brand)
    return acc.profile_text[:1200] if acc else ""


def gen_copy(note_fields: dict, mode: str = "stub") -> tuple[str, float]:
    """返回 (文案草稿, 成本_元)。mode: stub|real。"""
    title = _text_of(note_fields.get("标题")) or _text_of(note_fields.get("排期编号"))
    ctype = _text_of(note_fields.get("内容类型"))
    account = _text_of(note_fields.get("账号(自动)"))
    profile = _account_profile(account)  # 每号风格注入(缺则降级)
    if mode != "real":
        tag = f"|画像✓" if profile else ""
        return (f"[stub 占位文案|{ctype}|{account}{tag}] {title}——由 --llm real 生成正式稿。", 0.0)

    hint = _text_of(note_fields.get("脚本·分镜"))[:300]
    # 提示词自带品牌要点(P6演练教训:让 headless 去翻仓库会烧穿预算帽),零工具直出
    prompt = (
        f"为观云(传统文化服装品牌,非遗面料复原/改良传统服饰)写一篇小红书笔记文案。\n"
        f"笔记:「{title}」 内容类型:{ctype} 账号:{account}\n"
        f"{'线索:' + hint if hint else ''}\n"
        + (f"【本账号画像(务必贴合其既有风格)】\n{profile}\n" if profile else
           "调性:清冷、唯美、克制,不硬广;考据有据(文物对照:钩子→出处稀缺→形制工艺考据→非遗升华;ootd:意境起笔→文化→版型面料→场景)。\n")
        + f"格式:第一行标题(≤20字),空行,正文(≤1000字,分段,可用少量 emoji),最后一行 3-5 个#标签。\n"
        f"只输出成稿文本,不要解释、不要读文件。"
    )
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
