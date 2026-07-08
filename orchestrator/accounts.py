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
    def __init__(self, name: str, strategy: dict, profile_text: str):
        self.name = name
        self.strategy = strategy
        self.profile_text = profile_text


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


def _parse(stem: str, raw: str) -> Account | None:
    strategy, body = {}, raw
    if raw.lstrip().startswith("---"):
        s = raw.lstrip()
        end = s.find("---", 3)
        if end != -1:
            front = s[3:end].strip()
            body = s[end + 3:].lstrip("\n")
            try:
                strategy = json.loads(front)
            except json.JSONDecodeError:
                strategy = {}
    name = strategy.get("account", stem)
    return Account(name, strategy, body)
