"""LLM 步(唯一花钱的地方):real 文案生成底座。stub 占位由调用方(draft.py)自处理零成本。

**底座换过一次(dogfood 2026-07-14,真跑逼出来的)**:
原走 `claude -p`。真跑实测一条 200 字小红书文案 **2~3 元**,查下来贵得莫名——做了个对照实验:
让 `claude -p` 只回"测试成本"四个字,`cache_creation_input_tokens=32766`、花 **1.48 元**。
即 **claude -p 每次调用都吞 ~33K token 的 Claude Code 系统提示/工具定义**(哪怕 --allowedTools ""),
出稿成本 95% 以上付给了 CLI 的系统提示,**与文案长短、与模型档次几乎无关**(Opus 3.0 元 / Sonnet 2.16 元
/ 四个字 1.48 元)。所以"月预算超 3.6 倍"根本不是真墙,是底座选错了。

现在直连 ARK(豆包,与看图同一把 key):prompt 就是 prompt,token 就是 token。
"""
from __future__ import annotations

import json
import subprocess

from . import ark, config

USD_CNY = 7.2


def run_prompt(prompt: str, model: str = "") -> tuple[str, float]:
    """跑一次生成,返回 (成稿文本, 成本_元)。薄执行器 real 生成底座。

    backend=ark(默认):直连火山方舟,成本 = usage.total_tokens × DRAFT_COST_PER_1K_CNY(真实用量,不拍脑袋)。
    backend=claude_cli:旧路径,留着**只为对比文案质量**——它贵在 33K 系统提示 overhead,不该做常规底座。
    """
    if config.DRAFT_BACKEND == "claude_cli":
        return _claude_cli(prompt, model)
    text, tokens = ark.chat(prompt, model or config.DRAFT_MODEL)
    return (text, round(tokens / 1000 * config.DRAFT_COST_PER_1K_CNY, 4))


def _claude_cli(prompt: str, model: str = "") -> tuple[str, float]:
    """旧底座:claude -p(零工具直出,预算帽硬限)。**每调一次白吞 ~33K token 系统提示**——贵在这,不在文案。
    保留仅供质量对比(GY_DRAFT_BACKEND=claude_cli),别拿它当常规出稿底座。"""
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "2",
         "--model", model or "sonnet",
         "--max-budget-usd", str(config.PER_RUN_BUDGET_USD), "--allowedTools", ""],
        capture_output=True, text=True, timeout=600, cwd=str(config.WORKSPACE),
    )
    d = json.loads(r.stdout[r.stdout.find("{"):])
    text = (d.get("result") or "").strip()
    cost = round(float(d.get("total_cost_usd") or 0) * USD_CNY, 3)
    if not text:
        raise RuntimeError(f"claude -p 空结果: {r.stdout[:200]}")
    return (text, cost)
