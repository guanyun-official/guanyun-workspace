"""LLM 步(唯一花钱的地方):real 文案生成底座。stub 占位由调用方(draft.py)自处理零成本;
real 走 claude -p 预算帽硬限。大刀阔斧后重引擎已删,gen_copy(旧生成路径)随之删——
薄执行器 draft.py 自己组稿(画像+gen_skill few-shot+配方)后调本模块的 run_prompt。
"""
from __future__ import annotations

import json
import subprocess

from . import config

USD_CNY = 7.2


def run_prompt(prompt: str) -> tuple[str, float]:
    """跑一次 claude -p(零工具直出,预算帽硬限),返回 (成稿文本, 成本_元)。薄执行器 real 生成底座。"""
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
