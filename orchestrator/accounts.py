"""Account 定义加载器(候选C:画像+strategy 两文件塌成一个 Account,一处知道存储格式)。

一个账号 = 一个 `brands/{brand}/accounts/{号}.md`:
  ---
  {JSON frontmatter = strategy: cadence/material_needs/autonomy/...}
  ---
  正文 = 画像 prose(发什么/怎么写,喂生成)

消费方各取所需(seam 只此一处):
  planner → load(号).strategy    (结构化,排产)
  llm     → load(号).profile_text(自然语言,注入生成)
用 JSON frontmatter(非 YAML)避免新依赖;stdlib 即可解析。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config


class Account:
    def __init__(self, name: str, strategy: dict, profile_text: str, error: str | None = None):
        self.name = name
        self.strategy = strategy
        self.profile_text = profile_text
        self.error = error  # 非 None=frontmatter 解析失败;problems() 暴露、验收报红,不静默


def _accounts_dir(brand: str) -> Path:
    return config.WORKSPACE / "brands" / brand / "accounts"


def load(name: str, brand: str = "观云") -> Account | None:
    p = _accounts_dir(brand) / f"{name}.md"
    if not p.exists():
        return None
    return _parse(name, p.read_text(encoding="utf-8"))


def load_all(brand: str = "观云") -> dict[str, Account]:
    out = {}
    d = _accounts_dir(brand)
    if not d.exists():
        return out
    for p in d.glob("*.md"):
        if p.name == "README.md":
            continue
        acc = _parse(p.stem, p.read_text(encoding="utf-8"))
        if acc:
            out[acc.name] = acc
    return out


def problems(brand: str = "观云") -> dict[str, str]:
    """{账号名: 错误} for 所有 frontmatter 解析失败的账号(空=全部健康)。

    供验收/监控消费:坏声明必须'有声'——ar_check 断言此为空,防坏 {号}.md 静默少排号。
    """
    return {a.name: a.error for a in load_all(brand).values() if a.error}


def _parse(stem: str, raw: str) -> Account | None:
    strategy, body, error = {}, raw, None
    if raw.lstrip().startswith("---"):
        s = raw.lstrip()
        end = s.find("---", 3)
        if end != -1:
            front = s[3:end].strip()
            body = s[end + 3:].lstrip("\n")
            try:
                strategy = json.loads(front)
            except json.JSONDecodeError as e:
                error = f"frontmatter JSON 解析失败: {e}"
    name = strategy.get("account", stem)
    return Account(name, strategy, body, error)
