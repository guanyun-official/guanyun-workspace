"""LLM 步(唯一花钱的地方):文案生成。stub 模式零成本占位;real 模式 claude -p 预算帽硬限。
推进器自身零 LLM——本模块只被 engine 在 GEN_COPY 动作里调用。
"""
from __future__ import annotations

import json
import subprocess

from . import config

USD_CNY = 7.2


def gen_copy(note_fields: dict, mode: str = "stub") -> tuple[str, float]:
    """返回 (文案草稿, 成本_元)。mode: stub|real。"""
    title = note_fields.get("标题") or note_fields.get("排期编号", "")
    ctype = note_fields.get("内容类型", "")
    if mode != "real":
        return (f"[stub 占位文案|{ctype}] {title}——由 --llm real 生成正式稿。", 0.0)

    prompt = (
        f"你在观云内容工作区(已挂载技能)。为笔记「{title}」(内容类型:{ctype})写小红书文案草稿:"
        f"标题≤20字+正文≤1000字+3-5标签。品牌调性按 brands/观云;方法按 skills/write-xiaohongshu 与 "
        f"skills/guanyun-OOTD-text(如适用)。只输出成稿文本,不要解释。"
    )
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "6",
         "--max-budget-usd", str(config.PER_RUN_BUDGET_USD)],
        capture_output=True, text=True, timeout=600, cwd=str(config.WORKSPACE),
    )
    d = json.loads(r.stdout[r.stdout.find("{"):])
    text = (d.get("result") or "").strip()
    cost = round(float(d.get("total_cost_usd") or 0) * USD_CNY, 3)
    if not text:
        raise RuntimeError(f"claude -p 空结果: {r.stdout[:200]}")
    return (text, cost)
